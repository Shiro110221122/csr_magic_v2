"""AI 对话报名 Agent — 意图识别、信息提取、回复生成

移植自 CSR01 server.js，适配 magic 架构：
- 对话是活动特定的（已知 activity + user），无需从对话提取用户身份
- 按活动模板类型（CHECKIN/BASIC/DONATION/VOLUNTEER/CUSTOM）动态调整对话深度
- 动作结果返回给 Java 后端，由后端调用 ParticipationService 写库
"""

import json
import logging
import re
from typing import Optional

import httpx

from config import DASHSCOPE_API_KEY

logger = logging.getLogger(__name__)

DASHSCOPE_API = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_MODEL = "qwen-turbo"


async def _call_qwen(messages: list[dict]) -> str:
    """调用通义千问 API，返回模型回复文本"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            DASHSCOPE_API,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
            },
            json={
                "model": QWEN_MODEL,
                "messages": messages,
                "max_tokens": 1024,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(data["error"]["message"])
        usage = data.get("usage", {})
        logger.info(
            "Token usage — prompt: %s, completion: %s, total: %s",
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            usage.get("total_tokens", "?"),
        )
        return data["choices"][0]["message"]["content"]


def _fmt_history(history: list[dict]) -> str:
    return "\n".join(f"{h['role']}: {h['content']}" for h in history)


# ── 模板类型对应的必填字段 ─────────────────────────────────────────────────────

_TEMPLATE_FIELDS: dict[str, list[str]] = {
    "CHECKIN": [],          # 签到，直接确认
    "BASIC": [],            # 基础，可选备注
    "DONATION": ["amount"], # 捐赠，必须填金额
    "VOLUNTEER": ["volunteerHours"],  # 志愿者，必须填时长
    "CUSTOM": [],           # 自定义，按 formSchema 字段
}

_TEMPLATE_OPENER: dict[str, str] = {
    "CHECKIN": "你好！我来帮你完成签到，一键确认即可。确认参加吗？",
    "BASIC": "你好！需要留下参与备注吗？直接输入内容，或回复「跳过」。",
    "DONATION": "你好！我来帮你完成捐赠报名，请告诉我你计划捐赠多少金额（单位：元）？",
    "VOLUNTEER": "你好！请告诉我你计划参与的服务时长（如：3小时）。",
    "CUSTOM": "你好！我来帮你完成报名，请根据提示填写信息。",
}


# ── 意图识别 ──────────────────────────────────────────────────────────────────

async def detect_intent(message: str, history: list[dict]) -> dict:
    """识别用户消息的意图，返回 {intent, confidence}"""
    messages = [
        {
            "role": "system",
            "content": f"""你是 CSR 活动报名对话助手的意图识别模块。分析用户消息，返回 JSON。

意图分类：
- "signup"       — 用户明确想要报名/参加当前活动
- "withdraw"     — 用户想取消/退出当前活动的报名
- "query"        — 用户询问活动信息、报名状态
- "confirm"      — 用户确认摘要，同意提交报名（关键词：确认、好的、是的、对、OK、提交）
- "modify"       — 用户想修改已填信息
- "general_chat" — 其他一般性对话

只返回 JSON：{{"intent": "意图", "confidence": 0.9}}
不要其他文字。

对话历史：
{_fmt_history(history)}""",
        },
        {"role": "user", "content": f"当前消息：{message}"},
    ]
    reply = await _call_qwen(messages)
    try:
        m = re.search(r"\{[\s\S]*\}", reply)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return {"intent": "general_chat", "confidence": 0.1}


# ── 字段提取 ──────────────────────────────────────────────────────────────────

async def extract_form_data(
    message: str,
    history: list[dict],
    template_type: str,
    form_schema: list[dict],
) -> dict:
    """从对话中提取报名所需字段，返回 {fieldName: value, ...}，未知字段填 null"""

    # 构建字段描述
    if form_schema:
        field_desc = "\n".join(
            f"- {f.get('fieldName')}: {f.get('label', '')} ({f.get('fieldType', 'TEXT')})"
            f"{', 必填' if f.get('required') else ', 选填'}"
            for f in form_schema
        )
    else:
        field_desc = _get_default_field_desc(template_type)

    messages = [
        {
            "role": "system",
            "content": f"""从对话中提取活动报名字段，返回 JSON，未知字段填 null。

活动类型：{template_type}
需要收集的字段：
{field_desc}

规则：
1. notes/备注字段，用户说「跳过」则填空字符串 ""
2. amount 必须是数字
3. volunteerHours 必须是数字（小时）
4. 只返回 JSON，不要其他文字

对话历史：
{_fmt_history(history)}""",
        },
        {"role": "user", "content": f"当前消息：{message}"},
    ]
    reply = await _call_qwen(messages)
    try:
        m = re.search(r"\{[\s\S]*\}", reply)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return {}


def _get_default_field_desc(template_type: str) -> str:
    mapping = {
        "CHECKIN": "（无需额外字段，直接确认即可）",
        "BASIC": "- notes: 参与备注 (TEXT, 选填)",
        "DONATION": "- amount: 捐赠金额，单位元 (NUMBER, 必填)\n- notes: 留言 (TEXT, 选填)",
        "VOLUNTEER": "- volunteerHours: 计划志愿时长，单位小时 (NUMBER, 必填)\n- notes: 备注 (TEXT, 选填)",
        "CUSTOM": "（无预设字段）",
    }
    return mapping.get(template_type, "（无预设字段）")


# ── 确认摘要生成 ───────────────────────────────────────────────────────────────

def _build_summary(activity_name: str, user_name: str, form_data: dict, template_type: str) -> str:
    lines = [f"我将为你完成以下报名，请确认：", f"• 活动：《{activity_name}》"]
    if template_type == "DONATION" and form_data.get("amount"):
        lines.append(f"• 捐赠金额：{form_data['amount']} 元")
    if template_type == "VOLUNTEER" and form_data.get("volunteerHours"):
        lines.append(f"• 志愿时长：{form_data['volunteerHours']} 小时")
    if form_data.get("notes"):
        lines.append(f"• 备注：{form_data['notes']}")
    lines.append("\n回复「确认」提交，或告诉我需要修改的内容。")
    return "\n".join(lines)


# ── 追问生成 ──────────────────────────────────────────────────────────────────

async def generate_followup(
    missing_fields: list[str],
    activity_name: str,
    template_type: str,
    history: list[dict],
) -> str:
    """对缺失字段生成自然的追问"""
    field_labels = {
        "amount": "捐赠金额（元）",
        "volunteerHours": "计划志愿时长（小时）",
        "notes": "参与备注（可跳过）",
    }
    missing_desc = "、".join(field_labels.get(f, f) for f in missing_fields)

    messages = [
        {
            "role": "system",
            "content": """你是活动报名助手，语气简洁自然。
根据缺失信息生成一个追问，每次只问一个问题。
活动名称原样使用，不要翻译。只返回追问内容，不要其他文字。""",
        },
        {
            "role": "user",
            "content": (
                f"对话历史：\n{_fmt_history(history)}\n\n"
                f"用户想报名「{activity_name}」，还缺少：{missing_desc}。"
                f"请生成追问。"
            ),
        },
    ]
    return await _call_qwen(messages)


# ── 成功/失败回复生成 ──────────────────────────────────────────────────────────

async def generate_result_reply(scenario: str, context: dict) -> str:
    """生成报名/取消操作结果的自然语言回复"""
    prompts = {
        "signup_success": (
            "你是活动报名助手，语气简洁自然。"
            "告知用户报名成功，提及活动名称。"
            "最后补充 2-3 条实用注意事项，换行分隔，不要编号。"
            "只返回回复内容。"
        ),
        "signup_duplicate": (
            "你是活动报名助手。告知用户已报名过该活动，无需重复操作。只返回回复内容。"
        ),
        "signup_failure": (
            "你是活动报名助手。告知报名失败，提示用户稍后重试或联系管理员。只返回回复内容。"
        ),
        "withdraw_success": (
            "你是活动报名助手。告知取消报名成功，提及活动名称。只返回回复内容。"
        ),
        "withdraw_failure": (
            "你是活动报名助手。告知取消失败（可能已不在待审核状态），提示用户联系管理员。只返回回复内容。"
        ),
    }
    system = prompts.get(scenario, prompts["signup_failure"])
    user_msg = json.dumps(context, ensure_ascii=False)
    return await _call_qwen([
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ])


# ── 主对话函数 ────────────────────────────────────────────────────────────────

async def process_global_chat(
    message: str,
    history: list[dict],
    activities: list[dict],
    user: dict,
    my_participations: list[dict],
) -> dict:
    """
    全局对话入口（不绑定特定活动），模拟 CSR01 的对话模式。

    activities: [{id, name, templateType, status, ...}, ...]
    my_participations: [{id, activityId, activityName, state}, ...]
    返回: {reply, action, activity_id, participation_id, form_data}
    """
    # 不可再报名的活动 ID：PENDING（审批中）、RE_SUBMITTED（重新审批中）、APPROVED（已通过）均排除
    # REJECTED（已驳回）允许重新报名，不排除
    unavailable_activity_ids = {
        p["activityId"] for p in my_participations
        if p["state"] in ("PENDING", "RE_SUBMITTED", "APPROVED")
    }

    # 全量活动列表（用于意图识别）
    activity_list_text = "\n".join(
        f"- ID:{a['id']} 《{a['name']}》 类型:{a.get('templateType','BASIC')} 状态:{a.get('status','UPCOMING')}"
        for a in activities
    ) or "（暂无活动）"

    # 可报名的活动列表（排除审批中和已通过的，仿照 CSR01 generateFollowUpQuestion 逻辑）
    available_activities = [a for a in activities if a["id"] not in unavailable_activity_ids]
    available_activity_text = "\n".join(
        f"- ID:{a['id']} 《{a['name']}》 类型:{a.get('templateType','BASIC')} 状态:{a.get('status','UPCOMING')}"
        for a in available_activities
    ) or "（暂无可报名的活动）"
    logger.info("Available activities for user (excluding pending/approved): %s",
                [a["name"] for a in available_activities])

    # 状态说明映射
    _state_label = {
        "PENDING": "待审核（可取消）",
        "APPROVED": "已通过（不可取消，如需退出请联系管理员）",
        "REJECTED": "已驳回",
        "RE_SUBMITTED": "重新提交待审核（可取消）",
    }
    my_reg_text = "\n".join(
        f"- 报名ID:{p['id']} 《{p['activityName']}》 {_state_label.get(p['state'], p['state'])}"
        for p in my_participations
    ) or "（暂无报名记录）"

    # 仅 PENDING/RE_SUBMITTED 可取消
    cancelable_participations = [p for p in my_participations if p["state"] in ("PENDING", "RE_SUBMITTED")]
    cancelable_text = "\n".join(
        f"- 报名ID:{p['id']} 《{p['activityName']}》"
        for p in cancelable_participations
    ) or "（暂无可取消的报名）"

    # ── 第一步：意图识别 ──────────────────────────────────────────────────────
    conversation_history = _fmt_history(history)
    intent_messages = [
        {
            "role": "system",
            "content": f"""你是一个专业的中文意图识别助手。请仔细分析用户消息的真实意图，理解语义而非仅仅匹配关键词。

用户消息：{message}

意图分类规则：
1. "register" - 用户明确表达想要报名、参加、注册某个活动
   关键词：报名、注册、register、sign up、参加、想要参加、我要报名
   注意：如果上一轮对话是在收集报名信息（助手在询问活动名称或其他字段），用户的回复也属于 register

2. "withdraw" - 用户想要删除或取消已有的报名
   关键词：删除、取消、delete、cancel、remove、取消报名、不参加了

3. "query_activities" - 用户询问有哪些活动、活动信息、推荐活动
   关键词：活动、有什么活动、推荐活动、查看活动、活动列表、介绍一下

4. "query_registrations" - 用户询问自己的报名情况
   关键词：我报了哪些、报名情况、我的报名、报名记录

5. "general_chat" - 其他一般性对话

重要判断原则：
- 优先理解用户的真实意图和上下文
- "帮我推荐一个活动" 是询问活动，应识别为 query_activities
- "报名参加X活动"、"帮我报名"、"我要参加X" 应识别为 register
- 分析完整句子和对话历史，不要被部分词汇误导
- is_query: 仅当 intent 为 register 但用户实际是在查询报名记录时为 true，其他情况为 false

返回JSON格式：
{{"intent": "意图类型", "confidence": 0.9, "is_query": false}}

只返回JSON，不要其他文字。""",
        },
        {
            "role": "user",
            "content": f"对话历史：\n{conversation_history}\n\n当前消息：{message}",
        },
    ]
    intent_raw = await _call_qwen(intent_messages)
    logger.info("Raw AI reply for intent detection: %s", intent_raw)
    try:
        m = re.search(r"\{[\s\S]*\}", intent_raw)
        intent_result = json.loads(m.group()) if m else {}
    except Exception:
        intent_result = {}
    intent = intent_result.get("intent", "general_chat")
    confidence = intent_result.get("confidence", 0.0)
    is_query = intent_result.get("is_query", False)
    logger.info("AI detected intent: %s", intent_result)
    # register + is_query=true 表示用户在查询报名记录，重定向
    if intent == "register" and is_query:
        intent = "query_registrations"
    logger.info("Final detected intent: %s with confidence: %s", intent, confidence)

    # ── 查询活动 ───────────────────────────────────────────────────────────────
    if intent == "query_activities":
        logger.info("AI detected query_activities action")
        reply = await _call_qwen([
            {
                "role": "system",
                "content": f"""你是 CSR 活动助手，说话像朋友帮忙那样自然温暖，不要用"您"，用"你"。
根据用户问题介绍活动，活动名称原样使用，不要翻译，不要展示 ID。
【重要】可报名的活动只有以下这些（用户已报名的不在此列）：
{available_activity_text}
只能从这个列表里介绍，不能提及其他任何活动。只返回回复内容，不要其他文字。""",
            },
            {"role": "user", "content": message},
        ])
        return {"reply": reply, "action": None}

    # ── 查询我的报名 ───────────────────────────────────────────────────────────
    if intent == "query_registrations":
        logger.info("AI detected query_registrations action")
        reply = await _call_qwen([
            {
                "role": "system",
                "content": f"""你是 CSR 活动助手，语气亲切自然。
用户询问自己的报名情况，以下是他们的报名记录：
{my_reg_text}
只返回回复内容，不要其他文字。""",
            },
            {"role": "user", "content": message},
        ])
        return {"reply": reply, "action": None}

    # ── 取消报名 ───────────────────────────────────────────────────────────────
    if intent == "withdraw":
        logger.info("AI detected withdraw action")

        if not my_participations:
            logger.info("Withdraw: user has no registrations")
            return {"reply": "你目前没有任何报名记录，无需取消。", "action": None}

        if not cancelable_participations:
            logger.info("Withdraw: no cancelable registrations (all APPROVED/REJECTED)")
            reply = await _call_qwen([
                {
                    "role": "system",
                    "content": f"""你是活动助手，说话自然亲切，用"你"不用"您"。
用户想取消报名，但他们的报名都已审核通过或已驳回，系统不支持直接取消。
请告知用户情况，已通过的报名如需退出请联系管理员。
用户的报名记录：
{my_reg_text}
只返回回复内容，不要其他文字。""",
                },
                {"role": "user", "content": message},
            ])
            return {"reply": reply, "action": None}

        # 只有一条可取消记录 → 直接取消，不需要用户确认
        if len(cancelable_participations) == 1:
            pid = cancelable_participations[0]["id"]
            activity_name = cancelable_participations[0]["activityName"]
            logger.info("Withdraw: single cancelable record, directly canceling participation_id=%s", pid)
            return {"reply": "好的，正在为你取消报名…", "action": "withdraw", "participation_id": pid}

        # 多条记录：从对话历史+当前消息提取目标
        extract = await _call_qwen([
            {
                "role": "system",
                "content": f"""从对话中判断用户想取消哪条报名，返回 JSON。
字段：participation_id（必须从下方"可取消的报名ID"中取，找不到或不确定填 null，禁止填写活动ID）

【可取消的报名记录】：
{cancelable_text}

对话历史：
{_fmt_history(history)}

规则：
- participation_id 只能是上方可取消记录中的"报名ID"数字
- 用户明确说了活动名称或指代词（"第一个"、"就是这个"结合历史上下文能确定），则填对应 ID
- 不确定就填 null

只返回 JSON，不要其他文字。""",
            },
            {"role": "user", "content": f"当前消息：{message}"},
        ])
        logger.info("Qwen withdraw extraction reply: %s", extract)
        try:
            m = re.search(r"\{[\s\S]*\}", extract)
            info = json.loads(m.group()) if m else {}
        except Exception:
            info = {}
        logger.info("Extracted withdraw info: %s", info)

        pid = info.get("participation_id")
        if pid is not None:
            try:
                pid = int(pid)
            except (ValueError, TypeError):
                pid = None

        valid_pids = {p["id"] for p in cancelable_participations}
        if pid not in valid_pids:
            if pid is not None:
                logger.warning("Withdraw: invalid participation_id=%s (valid: %s), showing list", pid, valid_pids)
            pid = None

        if pid:
            logger.info("Withdraw: resolved participation_id=%s", pid)
            return {"reply": "好的，正在为你取消报名…", "action": "withdraw", "participation_id": pid}

        # 无法确定目标，列出让用户选
        logger.info("Withdraw: multiple records, showing list")
        reply = await _call_qwen([
            {
                "role": "system",
                "content": f"""你是活动助手，说话自然亲切，用"你"不用"您"。
用户想取消报名，请列出可以取消的报名记录，询问要取消哪个。
活动名称原样使用，不要翻译，不要展示报名ID。
【可取消的报名记录】：
{cancelable_text}
只返回回复内容，不要其他文字。""",
            },
            {"role": "user", "content": f"对话历史：\n{_fmt_history(history)}\n\n当前消息：{message}"},
        ])
        return {"reply": reply, "action": None}

    # ── 报名 ───────────────────────────────────────────────────────────────────
    if intent == "register" or _is_collecting(history):
        logger.info("AI detected register action")

        if not available_activities:
            logger.info("Register: no available activities, short-circuiting without LLM call")
            return {"reply": "抱歉，目前没有可报名的活动，请稍后再来看看～", "action": None}

        extract = await _call_qwen([
            {
                "role": "system",
                "content": f"""从对话中提取报名信息，返回 JSON。
字段：
- activity_id: 从可报名活动列表中语义匹配到的 ID，找不到填 null
- activity_name: 对应的活动名称
- form_data: 额外字段（如 amount/volunteerHours/notes），没有填 {{}}

【重要】可报名的活动只有以下这些（用户已报名的不在此列），只能从中匹配：
{available_activity_text}

对话历史：
{_fmt_history(history)}

只返回 JSON，不要其他文字。""",
            },
            {"role": "user", "content": f"当前消息：{message}"},
        ])
        logger.info("Qwen registration extraction reply: %s", extract)
        try:
            m = re.search(r"\{[\s\S]*\}", extract)
            info = json.loads(m.group()) if m else {}
        except Exception:
            info = {}
        logger.info("Extracted registration info: %s", info)

        aid = info.get("activity_id")
        if aid is not None:
            try:
                aid = int(aid)
            except (ValueError, TypeError):
                aid = None
        activity_name = info.get("activity_name", "")
        form_data = info.get("form_data") or {}

        if not aid:
            logger.info("Register: missing activity_id, asking user")
            reply = await _call_qwen([
                {
                    "role": "system",
                    "content": f"""你是活动助手，说话像朋友帮忙那样自然温暖，不要用"您"，用"你"。
用户想报名但没说清楚是哪个活动，简短介绍可选活动并询问，每次只问一个问题。
活动名称原样使用，不要翻译，不要展示 ID。
【重要】可报名的活动只有以下这些（用户已报名的不在此列）：
{available_activity_text}
只能从这个列表里推荐，不能提及其他任何活动。只返回回复内容，不要其他文字。""",
                },
                {"role": "user", "content": message},
            ])
            return {"reply": reply, "action": None}

        # 检查是否需要更多字段
        matched = next((a for a in activities if a["id"] == aid), None)
        template = matched.get("templateType", "BASIC") if matched else "BASIC"
        missing = _find_missing_fields(form_data, template, [])
        logger.info("Register: activity_id=%s template=%s missing_fields=%s", aid, template, missing)

        if missing:
            logger.info("Register: missing fields %s, asking user", missing)
            followup = await generate_followup(missing, activity_name, template, history)
            return {"reply": followup, "action": None}

        # 所有信息齐全，直接提交
        return {"reply": "好的，正在为你报名…", "action": "signup", "activity_id": aid, "form_data": form_data}

    # ── 一般对话 ───────────────────────────────────────────────────────────────
    reply = await _call_qwen([
        {
            "role": "system",
            "content": f"""你是 CSR 活动助手，语气亲切自然。
可以帮助用户查询活动、报名、取消报名。
当前活动：
{activity_list_text}
只返回回复内容。""",
        },
        {"role": "user", "content": message},
    ])
    return {"reply": reply, "action": None}


def _extract_activity_id_from_history(history: list[dict], activities: list[dict]) -> int | None:
    """从历史摘要消息里提取活动 ID"""
    for h in reversed(history):
        if h.get("role") == "assistant" and "回复「确认」提交" in h.get("content", ""):
            content = h["content"]
            for a in activities:
                if a["name"] in content:
                    return a["id"]
    return None


async def process_chat_message(
    message: str,
    history: list[dict],
    activity: dict,
    user: dict,
) -> dict:
    """
    处理一条用户消息，返回：
    {
        "reply": str,
        "action": "signup" | "withdraw" | null,
        "form_data": dict | null,   # action=signup 时携带
    }

    Args:
        message:  当前用户消息
        history:  [{role, content}, ...]
        activity: {id, name, templateType, formSchema, allowFamily}
        user:     {id, displayName, email}
    """
    activity_name = activity.get("name", "")
    template_type = activity.get("templateType", "BASIC")
    form_schema = activity.get("formSchema") or []

    intent_result = await detect_intent(message, history)
    intent = intent_result.get("intent", "general_chat")

    logger.info("intent=%s activity=%s user=%s", intent, activity_name, user.get("displayName"))

    # ── 取消报名 ──────────────────────────────────────────────────────────────
    if intent == "withdraw":
        reply = await _call_qwen([
            {
                "role": "system",
                "content": "你是活动报名助手。用户想取消报名，请确认是否要取消。语气自然简洁。只返回回复内容。",
            },
            {
                "role": "user",
                "content": f"用户想取消「{activity_name}」的报名，请让用户确认。",
            },
        ])
        return {"reply": reply, "action": "withdraw_confirm", "form_data": None}

    if intent == "confirm" and _last_action_was_withdraw(history):
        return {"reply": "好的，已收到取消请求。", "action": "withdraw", "form_data": None}

    # ── 报名确认（用户回复「确认」提交摘要） ────────────────────────────────────
    if intent == "confirm" and _has_pending_summary(history):
        form_data = _extract_form_data_from_history(history)
        return {"reply": "正在提交报名…", "action": "signup", "form_data": form_data}

    # ── 报名流程 ──────────────────────────────────────────────────────────────
    if intent in ("signup", "confirm", "modify") or _is_collecting(history):

        # CHECKIN — 直接开场白确认，用户再说「确认」即提交
        if template_type == "CHECKIN" and not history:
            return {
                "reply": _TEMPLATE_OPENER["CHECKIN"],
                "action": None,
                "form_data": None,
            }

        if template_type == "CHECKIN" and intent == "confirm":
            return {"reply": "正在提交报名…", "action": "signup", "form_data": {}}

        # 提取当前已有字段
        form_data = await extract_form_data(message, history, template_type, form_schema)
        missing = _find_missing_fields(form_data, template_type, form_schema)

        if not missing:
            # 所有字段齐全 → 展示摘要
            summary = _build_summary(activity_name, user.get("displayName", ""), form_data, template_type)
            return {"reply": summary, "action": None, "form_data": form_data}

        # 有缺失字段 → 追问，若是首次进入则用模板开场白
        if not history and template_type in _TEMPLATE_OPENER:
            return {
                "reply": _TEMPLATE_OPENER.get(template_type, _TEMPLATE_OPENER["BASIC"]),
                "action": None,
                "form_data": None,
            }

        followup = await generate_followup(missing, activity_name, template_type, history)
        return {"reply": followup, "action": None, "form_data": None}

    # ── 查询 / 一般对话 ────────────────────────────────────────────────────────
    context_text = (
        f"活动名称：{activity_name}\n"
        f"活动类型：{template_type}\n"
        f"当前用户：{user.get('displayName', '未知')}\n"
    )
    reply = await _call_qwen([
        {
            "role": "system",
            "content": (
                f"你是 CSR 活动助手，帮助用户了解和报名活动。\n\n"
                f"当前活动信息：\n{context_text}\n"
                "请根据用户问题回答，并适时引导用户报名。只返回回复内容。"
            ),
        },
        {"role": "user", "content": message},
    ])
    return {"reply": reply, "action": None, "form_data": None}


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _find_missing_fields(
    form_data: dict,
    template_type: str,
    form_schema: list[dict],
) -> list[str]:
    """返回还未填写的必填字段列表"""
    if form_schema:
        required = [f["fieldName"] for f in form_schema if f.get("required")]
        return [f for f in required if not form_data.get(f)]

    # 默认必填字段
    required_map = {
        "DONATION": ["amount"],
        "VOLUNTEER": ["volunteerHours"],
    }
    required = required_map.get(template_type, [])
    return [f for f in required if not form_data.get(f)]


def _has_pending_summary(history: list[dict]) -> bool:
    """检查历史里是否有待确认的摘要"""
    for h in reversed(history):
        if h.get("role") == "assistant" and "回复「确认」提交" in h.get("content", ""):
            return True
    return False


def _last_action_was_withdraw(history: list[dict]) -> bool:
    """检查最近一条助手消息是否是取消确认"""
    for h in reversed(history):
        if h.get("role") == "assistant":
            content = h.get("content", "")
            return "取消" in content and "确认" in content
    return False


def _is_collecting(history: list[dict]) -> bool:
    """检查是否正在进行报名信息收集流程"""
    for h in reversed(history):
        if h.get("role") == "assistant":
            content = h.get("content", "")
            # 助手上一条是追问或摘要 → 仍在流程中
            if any(kw in content for kw in ["请告诉我", "请问", "金额", "时长", "确认"]):
                return True
            break
    return False


def _extract_form_data_from_history(history: list[dict]) -> dict:
    """从历史消息里的最后一条摘要中反向解析 form_data"""
    for h in reversed(history):
        if h.get("role") == "assistant" and "回复「确认」提交" in h.get("content", ""):
            data: dict = {}
            content = h["content"]
            # 捐赠金额
            m = re.search(r"捐赠金额：(\d+(?:\.\d+)?)", content)
            if m:
                data["amount"] = float(m.group(1))
            # 志愿时长
            m = re.search(r"志愿时长：(\d+(?:\.\d+)?)", content)
            if m:
                data["volunteerHours"] = float(m.group(1))
            # 备注
            m = re.search(r"备注：(.+)", content)
            if m:
                data["notes"] = m.group(1).strip()
            return data
    return {}

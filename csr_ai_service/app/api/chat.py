"""AI 对话报名 API 路由"""

import logging
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field
from typing import Optional

from app.agents.chat_agent import process_chat_message, generate_result_reply, process_global_chat
from config import API_AUTH_TOKEN
from models import ApiResponseModel

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_api_key(x_api_key: str = Header(None, alias="X-Api-Key")) -> None:
    if API_AUTH_TOKEN and x_api_key != API_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="无效的 API 密钥")


# ── 请求/响应模型 ─────────────────────────────────────────────────────────────

class ChatHistoryItem(BaseModel):
    role: str
    content: str


class ActivityInfo(BaseModel):
    id: int
    name: str
    templateType: str = "BASIC"
    formSchema: Optional[list[dict]] = None
    allowFamily: bool = False


class UserInfo(BaseModel):
    id: int
    displayName: str
    email: Optional[str] = None


class ChatMessageRequest(BaseModel):
    message: str = Field(..., description="用户当前消息")
    history: list[ChatHistoryItem] = Field(default_factory=list, description="对话历史")
    activity: ActivityInfo = Field(..., description="当前活动信息")
    user: UserInfo = Field(..., description="当前登录用户")


class ChatMessageResponse(BaseModel):
    reply: str
    action: Optional[str] = None   # "signup" | "withdraw" | "withdraw_confirm" | null
    formData: Optional[dict] = None


# ── 通知结果回复端点（后端写库后回调，生成自然语言告知用户）──────────────────────

class SignupResultRequest(BaseModel):
    scenario: str   # "signup_success" | "signup_duplicate" | "signup_failure" | "withdraw_success" | "withdraw_failure"
    activityName: str
    userName: Optional[str] = None


# ── 路由 ──────────────────────────────────────────────────────────────────────

@router.post("/message", dependencies=[Depends(verify_api_key)])
async def chat_message(request: ChatMessageRequest) -> ApiResponseModel:
    """
    处理一条对话消息，返回 AI 回复和可选的动作指令。

    action 说明：
    - null            — 纯对话，前端仅展示 reply
    - "signup"        — 后端应调用 ParticipationService.signup()，formData 随附
    - "withdraw"      — 后端应调用 ParticipationService.withdraw()
    - "withdraw_confirm" — AI 正在向用户确认取消意图，前端仅展示 reply
    """
    logger.info(
        "收到对话消息: user=%s activity=%s message=%s",
        request.user.displayName,
        request.activity.name,
        request.message[:50],
    )
    try:
        result = await process_chat_message(
            message=request.message,
            history=[h.model_dump() for h in request.history],
            activity=request.activity.model_dump(),
            user=request.user.model_dump(),
        )
        return ApiResponseModel(
            code=200,
            message="success",
            data=ChatMessageResponse(
                reply=result["reply"],
                action=result.get("action"),
                formData=result.get("form_data"),
            ).model_dump(exclude_none=True),
        )
    except Exception as e:
        logger.error("对话处理失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class GlobalChatRequest(BaseModel):
    message: str
    history: list[ChatHistoryItem] = Field(default_factory=list)
    activities: list[dict] = Field(default_factory=list)
    user: UserInfo
    my_participations: list[dict] = Field(default_factory=list)


class GlobalChatResponse(BaseModel):
    reply: str
    action: Optional[str] = None
    activity_id: Optional[int] = None
    participation_id: Optional[int] = None
    form_data: Optional[dict] = None


@router.post("/global", dependencies=[Depends(verify_api_key)])
async def global_chat(request: GlobalChatRequest) -> ApiResponseModel:
    logger.info("全局对话: user=%s message=%s", request.user.displayName, request.message[:50])
    try:
        result = await process_global_chat(
            message=request.message,
            history=[h.model_dump() for h in request.history],
            activities=request.activities,
            user=request.user.model_dump(),
            my_participations=request.my_participations,
        )
        return ApiResponseModel(
            code=200,
            message="success",
            data=GlobalChatResponse(**result).model_dump(exclude_none=True),
        )
    except Exception as e:
        logger.error("全局对话处理失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/result-reply", dependencies=[Depends(verify_api_key)])
async def signup_result_reply(request: SignupResultRequest) -> ApiResponseModel:
    """
    后端完成报名/取消操作后，调用此端点生成自然语言结果回复。
    """
    try:
        reply = await generate_result_reply(
            scenario=request.scenario,
            context={"activityName": request.activityName, "userName": request.userName},
        )
        return ApiResponseModel(code=200, message="success", data={"reply": reply})
    except Exception as e:
        logger.error("结果回复生成失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Send, Loader2, MessageSquare } from 'lucide-react';
import { activityApi } from '../services/activityApi';
import { chatApi, type ChatHistoryItem } from '../services/chatApi';
import { useAuthStore } from '../stores/authStore';
import type { ActivityDetail } from '../types/participation';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

const TEMPLATE_OPENERS: Record<string, string[]> = {
  CHECKIN:   ['📋 有哪些活动可以参加？', '✅ 确认参加'],
  BASIC:     ['📋 介绍一下这个活动', '✅ 我要报名', '❌ 取消我的报名'],
  DONATION:  ['💰 我要捐赠报名', '📋 活动详情', '❌ 取消我的报名'],
  VOLUNTEER: ['🤝 我要报名志愿者', '📋 活动详情', '❌ 取消我的报名'],
  CUSTOM:    ['📋 介绍一下这个活动', '✅ 我要报名', '❌ 取消我的报名'],
};

export default function ChatRegistrationPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);

  const [activity, setActivity] = useState<ActivityDetail | null>(null);
  const [loadingActivity, setLoadingActivity] = useState(true);

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // 加载活动基本信息
  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const res = await activityApi.getById(Number(id));
        setActivity(res.data.data);
      } catch {
        // 加载失败则回退
        navigate(`/activities/${id}`, { replace: true });
      } finally {
        setLoadingActivity(false);
      }
    })();
  }, [id, navigate]);

  // 新消息时滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sending || !activity) return;

      const userMsg: Message = { role: 'user', content: trimmed };
      setMessages((prev) => [...prev, userMsg]);
      setInput('');
      setSending(true);

      // 构造历史（不含刚刚加的用户消息）
      const historyForApi: ChatHistoryItem[] = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      try {
        const res = await chatApi.sendMessage(activity.id, {
          message: trimmed,
          history: historyForApi,
        });
        const reply = res.data.data?.reply ?? '抱歉，未能获取回复。';
        setMessages((prev) => [...prev, { role: 'assistant', content: reply }]);
      } catch {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: '网络错误，请稍后重试。' },
        ]);
      } finally {
        setSending(false);
        inputRef.current?.focus();
      }
    },
    [activity, messages, sending]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  if (loadingActivity) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <Loader2 className="w-8 h-8 animate-spin text-green-500" />
      </div>
    );
  }

  const quickReplies = activity
    ? (TEMPLATE_OPENERS[activity.templateType] ?? TEMPLATE_OPENERS.BASIC)
    : [];

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* 顶部导航栏 */}
      <header className="flex items-center gap-3 px-4 py-3 bg-white border-b border-gray-200 shadow-sm">
        <button
          onClick={() => navigate(`/activities/${id}`)}
          className="p-1 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-2 min-w-0">
          <MessageSquare className="w-5 h-5 text-green-500 shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-gray-900 truncate">
              {activity?.name ?? 'AI 对话报名'}
            </p>
            <p className="text-xs text-gray-400">
              你好，{user?.displayName ?? '用户'}
            </p>
          </div>
        </div>
      </header>

      {/* 消息区域 */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.length === 0 ? (
          /* 欢迎占位 */
          <div className="flex flex-col items-center justify-center h-full pb-16 gap-6">
            <div className="bg-white border border-green-100 rounded-2xl p-6 max-w-sm w-full text-center shadow-sm">
              <div className="text-4xl mb-3">🌿</div>
              <h2 className="text-base font-bold text-gray-800 mb-1">
                {activity?.name}
              </h2>
              <p className="text-sm text-gray-500 leading-relaxed">
                通过 AI 对话完成报名，随时输入问题或点击下方快捷选项开始。
              </p>
            </div>

            {/* 快捷选项 */}
            <div className="grid grid-cols-1 gap-2 w-full max-w-sm">
              {quickReplies?.map((text) => (
                <button
                  key={text}
                  onClick={() => sendMessage(text)}
                  className="text-left px-4 py-3 rounded-xl bg-white border border-gray-200 hover:border-green-400 hover:bg-green-50 text-sm text-gray-700 transition-colors shadow-sm"
                >
                  {text}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center text-green-600 text-xs font-bold shrink-0 mr-2 mt-1">
                    AI
                  </div>
                )}
                <div
                  className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap shadow-sm ${
                    msg.role === 'user'
                      ? 'bg-green-500 text-white rounded-br-sm'
                      : 'bg-white text-gray-800 border border-gray-100 rounded-bl-sm'
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))}

            {/* 发送中动画气泡 */}
            {sending && (
              <div className="flex justify-start">
                <div className="w-8 h-8 rounded-full bg-green-100 flex items-center justify-center text-green-600 text-xs font-bold shrink-0 mr-2 mt-1">
                  AI
                </div>
                <div className="bg-white border border-gray-100 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
                  <span className="flex gap-1">
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
                  </span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* 输入区域 */}
      <div className="bg-white border-t border-gray-200 px-4 py-3 safe-area-pb">
        <div className="flex items-center gap-2 bg-gray-100 rounded-2xl px-4 py-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息..."
            disabled={sending}
            className="flex-1 bg-transparent text-sm text-gray-800 placeholder-gray-400 outline-none disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || sending}
            className="w-8 h-8 rounded-full bg-green-500 hover:bg-green-600 disabled:bg-gray-300 flex items-center justify-center transition-colors shrink-0"
          >
            {sending ? (
              <Loader2 className="w-4 h-4 text-white animate-spin" />
            ) : (
              <Send className="w-4 h-4 text-white" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

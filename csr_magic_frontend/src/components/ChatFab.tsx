import { MessageSquare } from 'lucide-react';

interface ChatFabProps {
  onClick: () => void;
}

export default function ChatFab({ onClick }: ChatFabProps) {
  return (
    <button
      onClick={onClick}
      title="AI 对话报名"
      className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-[#2EB87A] hover:bg-[#27a46d] active:scale-95 shadow-lg flex items-center justify-center transition-all"
    >
      <MessageSquare className="w-6 h-6 text-white" />
    </button>
  );
}

import { useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { Menu, Leaf, X, LogOut } from 'lucide-react';
import { useAuthStore } from '../stores/authStore';
import NotificationBell from './NotificationBell';
import ChatFab from './ChatFab';
import ChatDrawer from './ChatDrawer';

const navLinks = [
  { to: '/', label: '首页' },
  { to: '/activities', label: '活动' },
  { to: '/poster', label: '海报工作台' },
  { to: '/my', label: '个人中心' },
];

export default function EmployeeLayout() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F7FAF8] text-[#1A2E22] font-sans">
      {/* 顶部导航栏 */}
      <nav className="bg-white shadow-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            {/* 左侧：Logo + 汉堡菜单 */}
            <div className="flex items-center gap-2">
              <button
                className="md:hidden p-2 -ml-2 text-[#1A2E22]/60 hover:text-[#1A2E22]"
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              >
                {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
              </button>
              <div
                className="flex items-center gap-2 cursor-pointer"
                onClick={() => navigate('/')}
              >
                <div className="w-8 h-8 bg-[#2EB87A]/10 rounded-xl flex items-center justify-center">
                  <Leaf className="w-5 h-5 text-[#2EB87A]" />
                </div>
                <span className="font-bold text-lg hidden sm:block">CSR Hub</span>
              </div>
            </div>

            {/* 中间：桌面端导航链接 */}
            <div className="hidden md:flex items-center gap-8">
              {navLinks.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  end={link.to === '/'}
                  className={({ isActive }) =>
                    `font-medium transition-colors ${
                      isActive
                        ? 'text-[#2EB87A]'
                        : 'text-[#1A2E22]/60 hover:text-[#1A2E22]'
                    }`
                  }
                >
                  {link.label}
                </NavLink>
              ))}
            </div>

            {/* 右侧：通知 + 头像 + 登出 */}
            <div className="flex items-center gap-3">
              <NotificationBell />
              <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-[#2EB87A] to-[#FFB347] p-[2px]">
                <div className="w-full h-full rounded-full bg-white flex items-center justify-center text-sm font-bold text-[#2EB87A]">
                  {user?.displayName?.charAt(0) ?? user?.username?.charAt(0) ?? 'U'}
                </div>
              </div>
              <button
                type="button"
                onClick={logout}
                className="p-2 text-[#1A2E22]/40 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                title="退出登录"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* 移动端下拉菜单 */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-gray-100 bg-white">
            <div className="px-4 py-3 space-y-1">
              {navLinks.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  end={link.to === '/'}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    `block px-3 py-2 rounded-xl font-medium transition-colors ${
                      isActive
                        ? 'bg-[#2EB87A]/10 text-[#2EB87A]'
                        : 'text-[#1A2E22]/60 hover:bg-gray-50 hover:text-[#1A2E22]'
                    }`
                  }
                >
                  {link.label}
                </NavLink>
              ))}
            </div>
          </div>
        )}
      </nav>

      {/* 内容区 */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-24 md:pb-8">
        <Outlet />
      </main>

      {/* AI 对话悬浮按钮 + 抽屉 */}
      <ChatFab onClick={() => setChatOpen(true)} />
      <ChatDrawer open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}

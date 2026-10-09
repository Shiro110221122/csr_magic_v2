import { useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import ErrorBoundary from './components/ErrorBoundary';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import PrivateRoute from './components/PrivateRoute';
import PublicOnlyRoute from './components/PublicOnlyRoute';
import AdminLayout from './components/AdminLayout';
import EmployeeLayout from './components/EmployeeLayout';
import EventManagementPage from './pages/admin/EventManagementPage';
import SurveyManagementPage from './pages/admin/SurveyManagementPage';
import SurveyFillPage from './pages/SurveyFillPage';
import MySurveysPage from './pages/MySurveysPage';
import ActivityManagementPage from './pages/admin/ActivityManagementPage';
import UserManagementPage from './pages/admin/UserManagementPage';
import ParticipationPage from './pages/admin/ParticipationPage';
import DashboardPage from './pages/admin/DashboardPage';
import ActivityListPage from './pages/ActivityListPage';
import ActivityDetailPage from './pages/ActivityDetailPage';
import HomePage from './pages/HomePage';
import MyProfilePage from './pages/MyProfilePage';
import NotificationListPage from './pages/NotificationListPage';
import AIPosterStudioPage from './pages/AIPosterStudioPage';
import ChatRegistrationPage from './pages/ChatRegistrationPage';
import { useAuthStore } from './stores/authStore';

export default function App() {
  const loadFromStorage = useAuthStore.getState().loadFromStorage;

  useEffect(() => {
    loadFromStorage();
  }, [loadFromStorage]);

  return (
    <ErrorBoundary>
      <Routes>
        {/* 公开路由（已登录用户被重定向首页） */}
        <Route element={<PublicOnlyRoute />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Route>

        {/* 受保护路由 */}
        <Route element={<PrivateRoute />}>
          {/* 员工端路由 */}
          <Route element={<EmployeeLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/activities" element={<ActivityListPage />} />
            <Route path="/activities/:id" element={<ActivityDetailPage />} />
            <Route path="/activities/:id/chat" element={<ChatRegistrationPage />} />
            <Route path="/my-surveys" element={<MySurveysPage />} />
          <Route path="/surveys/:id" element={<SurveyFillPage />} />
          <Route path="/notifications" element={<NotificationListPage />} />
            <Route path="/my" element={<MyProfilePage />} />
            <Route path="/poster" element={<AIPosterStudioPage />} />
          </Route>

          {/* 管理端路由 */}
          <Route path="/admin" element={<AdminLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="events" element={<EventManagementPage />} />
            <Route path="activities" element={<ActivityManagementPage />} />
            <Route path="surveys" element={<SurveyManagementPage />} />
          <Route path="participations" element={<ParticipationPage />} />
            <Route path="users" element={<UserManagementPage />} />
            <Route path="notifications" element={<Navigate to="/admin/participations?state=PENDING" replace />} />
          </Route>
        </Route>

        {/* 兜底重定向 */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  );
}
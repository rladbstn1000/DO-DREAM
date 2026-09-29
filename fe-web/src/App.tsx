// src/App.tsx
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import Swal from 'sweetalert2';
import { authSession, AUTH_STATE_EVENT } from './auth/client';
import { MemoProvider } from './contexts/MemoContext';
import Join from './pages/Join';
import ClassroomList from './pages/ClassroomList';
import Classroom from './pages/Classroom';
import EditorPage from './pages/EditorPage';
import StudentRoom from './pages/StudentRoom';
import ChatHistory from './pages/ChatHistory'; 
import './index.css';

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(() => {
    const stored = localStorage.getItem('isLoggedIn');
    return stored === 'true' && !!localStorage.getItem('accessToken');
  });

  const navigate = useNavigate();
  useEffect(() => {
    const changed = (event: Event) => {
      const { authenticated, reason } = (event as CustomEvent).detail;
      setIsLoggedIn(authenticated);
      if (!authenticated) navigate('/', { replace: true });
      if (reason === 'expired') {
        void Swal.fire({ icon: 'info', title: '다시 로그인해주세요',
          text: '로그인이 만료되었거나 인증 서비스를 사용할 수 없습니다.' });
      }
    };
    window.addEventListener(AUTH_STATE_EVENT, changed);
    return () => window.removeEventListener(AUTH_STATE_EVENT, changed);
  }, [navigate]);

  const handleLogin = () => {
    setIsLoggedIn(true);
  };

  const handleLogout = async () => {
    await authSession.logout();
  };

  return (
    <MemoProvider>
      <Routes>
        {/* 로그인/회원가입 페이지 */}
        <Route
          path="/"
          element={
            isLoggedIn ? (
              <Navigate to="/classrooms" replace />
            ) : (
              <Join onLoginSuccess={handleLogin} />
            )
          }
        />

        {/* 반 선택 페이지 */}
        <Route
          path="/classrooms"
          element={
            isLoggedIn ? (
              <ClassroomList onLogout={handleLogout} />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />

        {/* 반별 자료함 & 학생 관리 페이지 */}
        <Route
          path="/classroom/:classroomId"
          element={isLoggedIn ? <Classroom /> : <Navigate to="/" replace />}
        />

        {/* 에디터 페이지 */}
        <Route
          path="/editor"
          element={isLoggedIn ? <EditorPage /> : <Navigate to="/" replace />}
        />

        {/* 학생 페이지 */}
        <Route
          path="/student/:studentId"
          element={isLoggedIn ? <StudentRoom /> : <Navigate to="/" replace />}
        />

        {/* 대화 기록 페이지 */}
        <Route
          path="/chat-history/:sessionId"
          element={isLoggedIn ? <ChatHistory /> : <Navigate to="/" replace />}
        />

        {/* 기본 라우트 */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </MemoProvider>
  );
}

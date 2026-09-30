import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { useEffect, type ReactNode } from 'react';
import Swal from 'sweetalert2';
import { authSession, AUTH_STATE_EVENT } from './auth/client';
import { MemoProvider } from './contexts/MemoContext';
import Join from './pages/Join';
import ClassroomList from './pages/ClassroomList';
import Classroom from './pages/Classroom';
import EditorPage from './pages/EditorPage';
import StudentRoom from './pages/StudentRoom';
import ChatHistory from './pages/ChatHistory';
import { StudentSessionProvider, useStudentSession, VerifiedRoute } from './student/Session';
import { DemoPage, LibraryPage } from './student/DemoLibrary';
import { ReaderPage } from './student/Reader';
import { QuizPage, ResultPage } from './student/Quiz';
import './index.css';
import './student/student.css';
function LoginRoute() {
  const { user, loading, error, refresh } = useStudentSession();
  if (loading) return <main className="learn-shell"><p role="status">로그인 정보를 확인하고 있습니다.</p></main>;
  if (user) return <Navigate to={user.role === 'STUDENT' ? '/learn' : '/classrooms'} replace />;
  if (error) return <main className="learn-shell"><h1>로그인 확인이 필요합니다</h1><button onClick={refresh}>로그인 다시 확인</button><button onClick={() => void authSession.logout().catch(() => {})}>로그아웃</button></main>;
  return <Join onLoginSuccess={refresh} />;
}
function ApplicationRoutes() {
  const navigate = useNavigate(); const location = useLocation();
  useEffect(() => {
    const changed = (event: Event) => {
      const { authenticated, reason } = (event as CustomEvent).detail;
      if (!authenticated && reason) navigate(location.pathname.startsWith('/learn') || location.pathname === '/demo' ? '/demo' : '/', { replace: true });
      if (reason === 'expired') void Swal.fire({ icon: 'info', title: '다시 로그인해주세요', text: '로그인이 만료되었거나 인증 서비스를 사용할 수 없습니다.' });
    };
    window.addEventListener(AUTH_STATE_EVENT, changed); return () => window.removeEventListener(AUTH_STATE_EVENT, changed);
  }, [navigate, location.pathname]);
  const teacher = (page: ReactNode) => <VerifiedRoute role="TEACHER">{page}</VerifiedRoute>;
  const student = (page: ReactNode) => <VerifiedRoute role="STUDENT">{page}</VerifiedRoute>;
  return <Routes>
    <Route path="/" element={<LoginRoute />} />
    <Route path="/classrooms" element={teacher(<ClassroomList onLogout={() => authSession.logout()} />)} />
    <Route path="/classroom/:classroomId" element={teacher(<Classroom />)} />
    <Route path="/editor" element={teacher(<EditorPage />)} />
    <Route path="/student/:studentId" element={teacher(<StudentRoom />)} />
    <Route path="/chat-history/:sessionId" element={teacher(<ChatHistory />)} />
    <Route path="/demo" element={<DemoPage />} />
    <Route path="/learn" element={student(<LibraryPage />)} />
    <Route path="/learn/:materialId" element={student(<ReaderPage key={location.pathname} />)} />
    <Route path="/learn/:materialId/quiz" element={student(<QuizPage key={location.pathname} />)} />
    <Route path="/learn/:materialId/results/:attemptId" element={student(<ResultPage key={location.pathname} />)} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
}
export default function App() { return <StudentSessionProvider><MemoProvider><ApplicationRoutes /></MemoProvider></StudentSessionProvider>; }

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { authSession, AUTH_STATE_EVENT } from '../auth/client';
import { identity, type Identity } from './model';
import { studentJson } from './api';
import { pendingPrefix } from './submission';

type Session = { user: Identity | null; loading: boolean; error: boolean; refresh: () => void };
const Context = createContext<Session>({ user: null, loading: true, error: false, refresh: () => {} });
export function StudentSessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Omit<Session, 'refresh'>>({ user: null, loading: !!authSession.getToken(), error: false });
  const [generation, setGeneration] = useState(0);
  const refresh = useCallback(() => setGeneration(n => n + 1), []);
  useEffect(() => {
    const changed = (event: Event) => {
      const authenticated = (event as CustomEvent).detail?.authenticated;
      if (!authenticated) {
        setState({ user: null, loading: false, error: false });
        try { for (let i = sessionStorage.length - 1; i >= 0; i--) { const key = sessionStorage.key(i); if (key?.startsWith(pendingPrefix) || key?.startsWith('dodream.student.chat.') || key?.startsWith('dodream.student.result.')) sessionStorage.removeItem(key); } } catch { /* Storage may be disabled. */ }
        window.speechSynthesis?.cancel();
      }
      if (authenticated) setState({ user: null, loading: true, error: false });
      refresh();
    };
    window.addEventListener(AUTH_STATE_EVENT, changed);
    return () => window.removeEventListener(AUTH_STATE_EVENT, changed);
  }, [refresh]);
  useEffect(() => {
    let alive = true;
    const epoch = authSession.getEpoch();
    if (!authSession.getToken()) { setState({ user: null, loading: false, error: false }); return; }
    setState({ user: null, loading: true, error: false });
    studentJson('/api/session/me').then(data => {
      const user = identity(data);
      if (!alive || epoch !== authSession.getEpoch()) return;
      // This is a routing hint only. Every protected view requires this server check.
      try { localStorage.setItem('authRole', user.role); } catch { throw new Error('로그인 저장소를 사용할 수 없습니다.'); }
      setState({ user, loading: false, error: false });
    }).catch(() => { if (alive && epoch === authSession.getEpoch()) setState({ user: null, loading: false, error: true }); });
    return () => { alive = false; };
  }, [generation]);
  return <Context.Provider value={{ ...state, refresh }}>{children}</Context.Provider>;
}
export const useStudentSession = () => useContext(Context);
export function VerifiedRoute({ role, children }: { role: Identity['role']; children: ReactNode }) {
  const { user, loading, error, refresh } = useStudentSession();
  const location = useLocation();
  if (loading) return <main className="learn-shell"><p role="status">로그인 정보를 확인하고 있습니다.</p></main>;
  if (error) return <main className="learn-shell"><h1>로그인 확인이 필요합니다</h1><p>사용자 정보를 받지 못했습니다. 계정을 바꾸지 않고 다시 확인할 수 있습니다.</p><button onClick={refresh}>다시 확인</button></main>;
  if (!user) return <Navigate to={role === 'STUDENT' ? '/demo' : '/'} state={{ from: location.pathname }} replace />;
  if (user.role !== role) return <Navigate to={user.role === 'STUDENT' ? '/learn' : '/classrooms'} replace />;
  return <>{children}</>;
}

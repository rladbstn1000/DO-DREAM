import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { authSession } from '../auth/client';
import { useStudentSession } from './Session';
import { PageHeading, ReaderSpeechView } from '../learning/Presentation';
export { Notice } from '../learning/Presentation';

export function LearningLayout({ children, title, subtitle }: { children: ReactNode; title: string; subtitle?: string }) {
  const { user } = useStudentSession();
  const [logoutError, setLogoutError] = useState('');
  return <div className="learn-app">
    <a className="learn-skip" href="#learning-main">본문으로 건너뛰기</a>
    <header className="learn-header"><Link className="learn-brand" to={user?.role === 'STUDENT' ? '/learn' : '/demo'} aria-label="두드림 학생 홈">DO:DREAM<span>한 걸음씩, 나의 속도로</span></Link>
      <nav aria-label="학습 메뉴">{user?.role === 'STUDENT' && <Link to="/learn">자료함</Link>}
        {user ? <><span className="learn-user">{user.name}</span><button className="learn-quiet" onClick={() => {
          void authSession.logout().catch(() => setLogoutError('이 화면에서는 로그아웃했습니다. 서버 로그아웃은 확인하지 못했습니다.'));
        }}>로그아웃</button></> : <Link to="/">교사 로그인</Link>}</nav>
    </header>
    <main id="learning-main" className="learn-shell"><PageHeading title={title} subtitle={subtitle} />
      {logoutError && <p role="alert" className="learn-error">{logoutError}</p>}{children}</main>
    <footer className="learn-footer">로컬 학생 웹 체험 · 직접 작성한 합성 학습 자료</footer>
  </div>;
}
export function useFence() {
  const ref = useRef({ active: true, epoch: authSession.getEpoch(), generation: 0 });
  useEffect(() => { ref.current.active = true; return () => { ref.current.active = false; ref.current.generation++; }; }, []);
  return { capture: () => ref.current.generation,
    current: (generation: number) => ref.current.active && generation === ref.current.generation && ref.current.epoch === authSession.getEpoch() };
}
export function ReaderSpeech({ text }: { text: string }) {
  return <ReaderSpeechView text={text} getEpoch={authSession.getEpoch} />;
}

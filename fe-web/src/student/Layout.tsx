import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { authSession } from '../auth/client';
import { useStudentSession } from './Session';
import { createReaderSpeech, koreanLocalVoice, type SpeechView } from './speech';

export function LearningLayout({ children, title, subtitle }: { children: ReactNode; title: string; subtitle?: string }) {
  const { user } = useStudentSession();
  const [logoutError, setLogoutError] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);
  const location = useLocation();
  useEffect(() => { heading.current?.focus(); }, [location.pathname]);
  return <div className="learn-app">
    <a className="learn-skip" href="#learning-main">본문으로 건너뛰기</a>
    <header className="learn-header"><Link className="learn-brand" to={user?.role === 'STUDENT' ? '/learn' : '/demo'} aria-label="두드림 학생 홈">DO:DREAM<span>한 걸음씩, 나의 속도로</span></Link>
      <nav aria-label="학습 메뉴">{user?.role === 'STUDENT' && <Link to="/learn">자료함</Link>}
        {user ? <><span className="learn-user">{user.name}</span><button className="learn-quiet" onClick={() => {
          void authSession.logout().catch(() => setLogoutError('이 화면에서는 로그아웃했습니다. 서버 로그아웃은 확인하지 못했습니다.'));
        }}>로그아웃</button></> : <Link to="/">교사 로그인</Link>}</nav>
    </header>
    <main id="learning-main" className="learn-shell"><div className="learn-page-heading"><span className="learn-eyebrow">DO:DREAM 학생 학습</span><h1 ref={heading} tabIndex={-1}>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>
      {logoutError && <p role="alert" className="learn-error">{logoutError}</p>}{children}</main>
    <footer className="learn-footer">로컬 학생 웹 체험 · 직접 작성한 합성 학습 자료</footer>
  </div>;
}
export function Notice({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <p className={error ? 'learn-error' : 'learn-notice'} role={error ? 'alert' : 'status'}>{children}</p>;
}
export function useFence() {
  const ref = useRef({ active: true, epoch: authSession.getEpoch(), generation: 0 });
  useEffect(() => { ref.current.active = true; return () => { ref.current.active = false; ref.current.generation++; }; }, []);
  return { capture: () => ref.current.generation,
    current: (generation: number) => ref.current.active && generation === ref.current.generation && ref.current.epoch === authSession.getEpoch() };
}
export function ReaderSpeech({ text }: { text: string }) {
  const [view, setView] = useState<SpeechView>({ state: 'idle', part: 0, total: 0, truncated: false });
  const [available, setAvailable] = useState(false);
  const controller = useRef<ReturnType<typeof createReaderSpeech> | null>(null);
  useEffect(() => {
    const speech = window.speechSynthesis;
    if (!speech || typeof SpeechSynthesisUtterance === 'undefined') return;
    const voices = () => setAvailable(!!koreanLocalVoice(speech.getVoices()));
    voices(); speech.addEventListener('voiceschanged', voices);
    controller.current = createReaderSpeech({ getEpoch: authSession.getEpoch, voices: () => speech.getVoices(),
      utterance: value => new SpeechSynthesisUtterance(value), speak: value => speech.speak(value as SpeechSynthesisUtterance),
      cancel: () => speech.cancel(), pause: () => speech.pause(), resume: () => speech.resume(), changed: setView });
    return () => { controller.current?.dispose(); controller.current = null; speech.removeEventListener('voiceschanged', voices); };
  }, []);
  useEffect(() => { controller.current?.stop(); }, [text]);
  return <section className="learn-speech" aria-label="본문 듣기"><div className="learn-button-row">
    <button disabled={!available} onClick={() => controller.current?.start(text)}>본문 듣기</button>
    <button disabled={view.state !== 'speaking' && view.state !== 'paused'} onClick={() => view.state === 'paused' ? controller.current?.resume() : controller.current?.pause()}>{view.state === 'paused' ? '듣기 계속' : '듣기 일시정지'}</button>
    <button disabled={view.state !== 'speaking' && view.state !== 'paused'} onClick={() => controller.current?.stop()}>듣기 중지</button>
  </div><p className="learn-small" role="status">{!available ? '이 브라우저에 로컬 한국어 음성이 없습니다. 글을 읽으며 계속 학습할 수 있습니다.' :
    view.state === 'error' ? '음성 재생을 마쳤거나 사용할 수 없습니다. 본문으로 계속 학습해주세요.' :
    view.state === 'idle' ? '기기에 있는 한국어 음성만 사용합니다. 버튼을 누르면 현재 단원을 읽습니다.' :
    `${view.state === 'paused' ? '일시정지' : '읽는 중'} · 현재 단원 ${view.part}/${view.total} 구간${view.truncated ? ' · 앞 10,000자까지 읽습니다.' : ''}`}</p></section>;
}

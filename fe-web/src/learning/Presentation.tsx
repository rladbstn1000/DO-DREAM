import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { createReaderSpeech, koreanLocalVoice, type SpeechView } from '../student/speech';

export function Notice({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <p className={error ? 'learn-error' : 'learn-notice'} role={error ? 'alert' : 'status'}>{children}</p>;
}
export function PageHeading({ title, subtitle, eyebrow = 'DO:DREAM 학생 학습' }: { title: string; subtitle?: string; eyebrow?: string }) {
  const heading = useRef<HTMLHeadingElement>(null);
  const location = useLocation();
  useLayoutEffect(() => { heading.current?.focus(); }, [location.pathname]);
  return <div className="learn-page-heading"><span className="learn-eyebrow">{eyebrow}</span><h1 ref={heading} tabIndex={-1}>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>;
}

export function ReaderSpeechView({ text, getEpoch }: { text: string; getEpoch: () => number }) {
  const [view, setView] = useState<SpeechView>({ state: 'idle', part: 0, total: 0, truncated: false });
  const [available, setAvailable] = useState(false);
  const controller = useRef<ReturnType<typeof createReaderSpeech> | null>(null);
  useLayoutEffect(() => {
    let speech: SpeechSynthesis;
    try { speech = window.speechSynthesis; } catch { return; }
    if (!speech || typeof SpeechSynthesisUtterance === 'undefined') return;
    const voices = () => { try { setAvailable(!!koreanLocalVoice(speech.getVoices())); } catch { setAvailable(false); } };
    voices();
    try { speech.addEventListener('voiceschanged', voices); } catch { /* Initial capability still applies. */ }
    controller.current = createReaderSpeech({ getEpoch, voices: () => speech.getVoices(),
      utterance: value => new SpeechSynthesisUtterance(value), speak: value => speech.speak(value as SpeechSynthesisUtterance),
      cancel: () => speech.cancel(), pause: () => speech.pause(), resume: () => speech.resume(), changed: setView });
    return () => { controller.current?.dispose(); controller.current = null; try { speech.removeEventListener('voiceschanged', voices); } catch { /* Text remains available. */ } };
  }, [getEpoch]);
  useLayoutEffect(() => { controller.current?.stop(); }, [text]);
  return <section className="learn-speech" aria-label="본문 듣기"><div className="learn-button-row">
    <button data-testid="tts-toggle" disabled={!available} onClick={() => controller.current?.start(text)}>본문 듣기</button>
    <button disabled={view.state !== 'speaking' && view.state !== 'paused'} onClick={() => view.state === 'paused' ? controller.current?.resume() : controller.current?.pause()}>{view.state === 'paused' ? '듣기 계속' : '듣기 일시정지'}</button>
    <button disabled={view.state !== 'speaking' && view.state !== 'paused'} onClick={() => controller.current?.stop()}>듣기 중지</button>
  </div><p className="learn-small" role="status">{!available || view.state === 'unavailable' ? '이 브라우저에 로컬 한국어 음성이 없습니다. 글을 읽으며 계속 학습할 수 있습니다.' :
    view.state === 'error' ? '음성 재생을 마쳤거나 사용할 수 없습니다. 본문으로 계속 학습해주세요.' :
    view.state === 'idle' ? '기기에 있는 한국어 음성만 사용합니다. 버튼을 누르면 현재 단원을 읽습니다.' :
    `${view.state === 'paused' ? '일시정지' : '읽는 중'} · 현재 단원 ${view.part}/${view.total} 구간${view.truncated ? ' · 앞 10,000자까지 읽습니다.' : ''}`}</p></section>;
}

import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { Link, Route, Routes, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Notice, PageHeading, ReaderSpeechView } from '../learning/Presentation';
import type { RecommendedQuestion, Sample } from './samples';
import type { createShowcaseStore, ShowcaseSnapshot } from './store';

export type ShowcasePort = {
  samples: readonly Sample[];
  findSample: (id: string | undefined) => Sample | undefined;
  store: ReturnType<typeof createShowcaseStore>;
};
type ViewProps = { port: ShowcasePort; state: ShowcaseSnapshot };
const normalizeQuestion = (value: string) => value.trim().replace(/\s+/g, ' ');

export function ShowcaseApp({ port }: { port: ShowcasePort }) {
  const state = useSyncExternalStore(port.store.subscribe, port.store.getSnapshot);
  const [resetCount, setResetCount] = useState(0);
  const [message, setMessage] = useState('');
  const epoch = useRef(0);
  const getEpoch = useRef(() => epoch.current).current;
  const navigate = useNavigate();
  return <div className="learn-app showcase-app">
    <a className="learn-skip" href="#showcase-main" onClick={event => { event.preventDefault(); document.getElementById('showcase-main')?.focus(); }}>본문으로 건너뛰기</a>
    <header className="learn-header"><Link className="learn-brand" to="/" aria-label="두드림 체험 홈">DO:DREAM<span>한 걸음씩, 나의 속도로</span></Link>
      <nav aria-label="체험 메뉴"><Link to="/learn">자료함</Link><Link to="/teacher">교사 보기</Link><button className="learn-quiet" data-testid="reset-demo" onClick={() => {
        epoch.current++; port.store.reset(); setResetCount(value => value + 1); setMessage('현재 화면의 체험을 초기화했습니다.'); navigate('/');
      }}>데모 초기화</button></nav>
    </header>
    <main className="learn-shell" id="showcase-main" tabIndex={-1}>
      <aside className="showcase-banner" aria-label="샘플 체험 안내"><span className="learn-pill">샘플 체험</span><p>포트폴리오 체험용 데모입니다. 샘플 교재와 준비된 답변·채점 규칙을 사용합니다. 질문과 답안은 이 페이지에서만 처리합니다.</p></aside>
      {state.notice && <Notice>{state.notice}</Notice>}{message && <Notice>{message}</Notice>}
      <Routes key={resetCount}>
        <Route path="/" element={<Start />} />
        <Route path="/learn" element={<Library port={port} state={state} />} />
        <Route path="/learn/:sampleId" element={<SampleRoute port={port}>{sample => <Reader key={sample.id} sample={sample} port={port} state={state} getEpoch={getEpoch} />}</SampleRoute>} />
        <Route path="/learn/:sampleId/quiz" element={<SampleRoute port={port}>{sample => <Quiz sample={sample} port={port} state={state} />}</SampleRoute>} />
        <Route path="/learn/:sampleId/results/:resultId" element={<SampleRoute port={port}>{sample => <Result sample={sample} port={port} state={state} />}</SampleRoute>} />
        <Route path="/teacher" element={<Teacher port={port} state={state} />} />
        <Route path="*" element={<><PageHeading title="이 체험 화면을 찾을 수 없어요" /><Notice>주소를 확인하거나 자료함에서 다시 시작해주세요.</Notice><Link className="learn-primary" to="/learn">자료함으로 돌아가기</Link></>} />
      </Routes>
    </main>
    <footer className="learn-footer">직접 작성한 공개 샘플 · 같은 탭의 임시 체험 기록<br />페이지를 여는 데 필요한 정적 파일만 요청합니다. 자료별 최근 풀이 10개를 이 탭에 보관합니다.</footer>
  </div>;
}

function Start() {
  return <><PageHeading title="배움의 속도는 달라도, 함께 앞으로" subtitle="읽기와 이해에 도움이 필요한 학생을 위한 학습 도우미, 두드림을 만나보세요." eyebrow="DO:DREAM 포트폴리오 체험" />
    <section className="learn-hero"><div><span className="learn-pill">가입 없이 시작해요</span><h2>짧게 읽고, 물어보고,<br />스스로 확인해요.</h2><p>쉬운 글과 단원별 읽기, 참고 문장, 짧은 퀴즈를 차례로 체험할 수 있어요. 교사 화면에서는 같은 탭에서 만든 질문과 풀이를 살펴봅니다.</p><div className="learn-button-row"><Link className="learn-primary" data-testid="start-student" to="/learn">학생 체험 시작</Link><Link data-testid="teacher-link" to="/teacher">교사 화면 보기</Link></div></div>
      <div className="learn-steps" aria-label="체험 순서"><span>01 · 나의 속도로 읽기</span><span>02 · 참고 문장 살펴보기</span><span>03 · 퀴즈로 확인하기</span></div></section>
    <div className="learn-grid"><section className="learn-card"><h2>이렇게 체험할 수 있어요</h2><p>샘플 교재 2개, 준비된 질문과 답변, 선택형 퀴즈를 제공합니다. 기기에 한국어 음성이 있으면 본문 듣기도 사용할 수 있어요.</p></section><section className="learn-card"><h2>교사와 학생의 흐름을 연결해요</h2><p>화면 전환은 체험 역할을 바꾸는 기능입니다. 실제 회원가입·문서 업로드·변환·공유·서버 저장은 제공하지 않습니다.</p></section></div>
  </>;
}

function Library({ port, state }: ViewProps) {
  return <><PageHeading title="나의 자료함" subtitle="마음에 드는 샘플 교재를 골라 한 단원씩 읽어보세요." /><div className="learn-grid">{port.samples.map((sample, index) => <article className="learn-card learn-material" key={sample.id}>
    <span className="learn-number">0{index + 1}</span><span className="learn-pill">{sample.category} · 샘플</span><h2>{sample.title}</h2><p>{sample.description}</p><span className="learn-small">{sample.sections.length}개 단원 · {sample.quiz.length}개 문제</span><Link className="learn-primary" data-testid={`material-${sample.id}`} to={`/learn/${sample.id}?section=${state.samples[sample.id].sectionId}`}>교재 읽기<span className="learn-sr-only"> · {sample.title}</span></Link>
  </article>)}</div></>;
}

function SampleRoute({ port, children }: { port: ShowcasePort; children: (sample: Sample) => ReactNode }) {
  const { sampleId } = useParams();
  const sample = port.findSample(sampleId);
  return sample ? children(sample) : <><PageHeading title="샘플 교재를 찾을 수 없어요" /><Notice error>이 주소에 해당하는 공개 샘플이 없습니다.</Notice><Link className="learn-primary" to="/learn">자료함으로 돌아가기</Link></>;
}

function Reader({ sample, port, state, getEpoch }: ViewProps & { sample: Sample; getEpoch: () => number }) {
  const progress = state.samples[sample.id];
  const [search, setSearch] = useSearchParams();
  const requested = search.get('section');
  const section = sample.sections.find(item => item.id === (requested ?? progress.sectionId)) ?? sample.sections[0];
  const index = sample.sections.indexOf(section);
  const sectionHeading = useRef<HTMLHeadingElement>(null);
  const previousSection = useRef(section.id);
  useEffect(() => { port.store.setSection(sample.id, section.id); if (previousSection.current !== section.id) sectionHeading.current?.focus(); previousSection.current = section.id; }, [port, sample.id, section.id]);
  const goSection = (id: string) => setSearch({ section: id });
  return <><Link className="learn-back" to="/learn">← 자료함</Link><PageHeading title={sample.title} subtitle={sample.description} />
    {requested && !sample.sections.some(item => item.id === requested) && <Notice>이 단원을 찾을 수 없어 첫 단원을 보여드립니다.</Notice>}
    <div className="learn-reader-grid"><aside className="learn-card learn-chapters"><h2>단원</h2><nav aria-label="단원 목록">{sample.sections.map((item, i) => <button key={item.id} aria-current={item.id === section.id ? 'step' : undefined} onClick={() => goSection(item.id)}><span>{i + 1}</span>{item.title}</button>)}</nav></aside>
      <div><article className="learn-card learn-reading"><div className="learn-section-row"><span className="learn-pill">현재 위치 {index + 1} / {sample.sections.length}</span><div className="learn-button-row" role="group" aria-label="글자 크기">{([18, 22, 26] as const).map((size, i) => <button key={size} aria-pressed={progress.fontSize === size} onClick={() => port.store.setFontSize(sample.id, size)}>{['기본 글자', '큰 글자', '아주 큰 글자'][i]}</button>)}</div></div>
        <h2 ref={sectionHeading} tabIndex={-1}>{section.title}</h2><div className={`learn-reading-text showcase-font-${progress.fontSize}`}>{section.paragraphs.map((text, i) => <p key={i}>{text}</p>)}</div>
        <ReaderSpeechView text={section.paragraphs.join('\n\n')} getEpoch={getEpoch} />
        <div className="learn-button-row"><button disabled={index === 0} onClick={() => goSection(sample.sections[index - 1].id)}>이전 단원</button><button data-testid="section-next" disabled={index === sample.sections.length - 1} onClick={() => goSection(sample.sections[index + 1].id)}>다음 단원</button><a href="#questions" onClick={event => { event.preventDefault(); document.getElementById('questions')?.focus(); }}>질문으로 이동</a><Link className="learn-primary" data-testid="quiz-start" to={`/learn/${sample.id}/quiz`}>퀴즈 풀기</Link></div>
      </article><Questions key={sample.id} sample={sample} port={port} state={state} goSection={goSection} /></div></div>
  </>;
}

function Questions({ sample, port, state, goSection }: ViewProps & { sample: Sample; goSection: (id: string) => void }) {
  const history = state.samples[sample.id].questionIds;
  const [question, setQuestion] = useState('');
  const [feedback, setFeedback] = useState('');
  const [selected, setSelected] = useState<string | null>(history[history.length - 1] ?? null);
  const answer = sample.recommendations.find(item => item.id === selected);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef(true);
  const source = answer && sample.sections.find(item => item.id === answer.source.sectionId);
  function ask(item?: RecommendedQuestion) {
    if (!item) { setFeedback('이 질문에는 준비된 답변이 없습니다. 아래 추천 질문 중 하나를 선택해주세요.'); setSelected(null); return; }
    setQuestion(item.question); setSelected(item.id); setFeedback(''); port.store.rememberQuestion(sample.id, item.id);
  }
  function close() { dialog.current?.close(); }
  function containTab(event: React.KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== 'Tab') return;
    const buttons = event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)');
    const first = buttons[0], last = buttons[buttons.length - 1];
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
  return <section className="learn-card learn-question" aria-labelledby="questions"><h2 id="questions" tabIndex={-1}>궁금한 점을 물어봐요</h2><p className="learn-small">추천 질문과 같은 질문에만 준비된 샘플 답변을 보여줍니다. 입력한 질문을 새롭게 해석하지 않습니다.</p>
    <div className="showcase-recommendations">{sample.recommendations.map(item => <button key={item.id} data-testid={`recommended-question-${item.id}`} onClick={() => ask(item)}>{item.question}</button>)}</div>
    <form onSubmit={event => { event.preventDefault(); ask(sample.recommendations.find(item => normalizeQuestion(item.question) === normalizeQuestion(question))); }}><label htmlFor="ask-input">질문</label><textarea id="ask-input" data-testid="ask-input" value={question} maxLength={500} rows={2} onChange={event => setQuestion(event.target.value)} /><button className="learn-primary" data-testid="ask-submit" type="submit">질문 보내기</button></form>
    {feedback && <Notice>{feedback}</Notice>}{answer && <article className="learn-message" data-testid="sample-answer" aria-live="polite"><span className="learn-pill">준비된 샘플 답변</span><h3>{answer.question}</h3><p>{answer.answer}</p><button ref={opener} data-testid="reference-open" onClick={() => { restoreFocus.current = true; dialog.current?.showModal(); }}>참고 구간 보기</button></article>}
    <dialog ref={dialog} className="learn-source-dialog" aria-labelledby="source-title" onKeyDown={containTab} onClose={() => { if (restoreFocus.current) opener.current?.focus(); }}><h2 id="source-title">샘플 참고 구간</h2>{answer && source && <><p>{sample.title} · {source.title}</p><blockquote>{source.paragraphs[answer.source.paragraphIndex]}</blockquote><p className="learn-small">이 답변에 미리 연결한 공개 샘플의 문장입니다.</p><div className="learn-button-row"><button onClick={() => { restoreFocus.current = false; close(); goSection(source.id); }}>이 단원으로 이동</button><button onClick={close}>참고 구간 닫기</button></div></>}</dialog>
  </section>;
}

function Quiz({ sample, port, state }: ViewProps & { sample: Sample }) {
  const navigate = useNavigate();
  const progress = state.samples[sample.id];
  const [error, setError] = useState('');
  return <><Link className="learn-back" to={`/learn/${sample.id}`}>← 본문으로</Link><PageHeading title={`${sample.title} 퀴즈`} subtitle="읽은 내용을 떠올리며 하나씩 골라보세요." /><p className="learn-mode">샘플 채점 규칙: 정해진 정답과 선택한 답이 같으면 문항당 1점입니다.</p>
    {progress.result ? <section className="learn-card"><h2>이 풀이는 제출했어요</h2><Link className="learn-primary" to={`/learn/${sample.id}/results/run-${progress.result.attemptNumber}`}>저장된 체험 결과 보기</Link></section> : <form className="learn-quiz-form" onSubmit={event => { event.preventDefault(); const result = port.store.submit(sample.id); if (result) navigate(`/learn/${sample.id}/results/run-${result.attemptNumber}`); else setError('모든 문제에서 답을 하나씩 골라주세요.'); }}>
      {sample.quiz.map((item, i) => <fieldset className="learn-card showcase-choices" key={item.id}><legend>{i + 1}. {item.prompt}</legend>{item.choices.map(choice => <label key={choice.id}><input type="radio" name={item.id} value={choice.id} checked={progress.draft[item.id] === choice.id} onChange={() => { port.store.setAnswer(sample.id, item.id, choice.id); setError(''); }} />{choice.text}</label>)}</fieldset>)}
      {error && <Notice error>{error}</Notice>}<button className="learn-primary" data-testid="quiz-submit" type="submit">제출하기</button>
    </form>}</>;
}

function Result({ sample, port, state }: ViewProps & { sample: Sample }) {
  const { resultId } = useParams();
  const navigate = useNavigate();
  const progress = state.samples[sample.id];
  const result = progress.results.find(item => `run-${item.attemptNumber}` === resultId);
  return <><PageHeading title="체험 결과" subtitle={`${sample.title} · 공개 샘플 퀴즈`} />{!result ? <><Notice>이 탭에 저장된 풀이 결과가 없습니다. 먼저 퀴즈를 풀어주세요.</Notice><Link className="learn-primary" to={`/learn/${sample.id}/quiz`}>퀴즈 풀기</Link></> : <>
    <section className="learn-card learn-result-summary"><span className="learn-pill" data-testid="result-attempt">{result.attemptNumber}번째 풀이</span><h2>{result.total}문제 중 {result.score}문제를 맞혔어요</h2><p>틀린 문제는 설명과 본문을 함께 보며 다시 살펴봐요.</p></section>
    {result.answers.map((answer, i) => { const item = sample.quiz.find(q => q.id === answer.questionId)!; return <article className="learn-card" key={answer.questionId}><span className={`learn-pill ${answer.correct ? 'learn-correct' : 'learn-incorrect'}`}>{answer.correct ? '정답' : '다시 살펴봐요'}</span><h2 className="learn-result-question">{i + 1}. {item.prompt}</h2><dl className="learn-result-detail"><dt>선택한 답</dt><dd>{item.choices.find(c => c.id === answer.choiceId)?.text}</dd><dt>샘플 정답</dt><dd>{item.choices.find(c => c.id === answer.correctChoiceId)?.text}</dd><dt>설명</dt><dd>{answer.explanation}</dd></dl></article>; })}
    <div className="learn-button-row"><button className="learn-primary" data-testid="retry-quiz" onClick={() => { port.store.retry(sample.id); navigate(`/learn/${sample.id}/quiz`); }}>{progress.result ? '다시 풀기' : '진행 중인 풀이 계속하기'}</button><Link to={`/learn/${sample.id}`}>본문 다시 읽기</Link><Link to="/teacher">교사 화면 보기</Link></div>
  </>}</>;
}

function Teacher({ port, state }: ViewProps) {
  const results = port.samples.flatMap(sample => state.samples[sample.id].results.map(result => ({ sample, result })));
  const questions = port.samples.flatMap(sample => state.samples[sample.id].questionIds.map(id => ({ sample, question: sample.recommendations.find(item => item.id === id)! })));
  return <><PageHeading title="교사 샘플 화면" subtitle="이 탭에서 체험한 질문과 풀이를 함께 살펴봅니다. 실제 학급이나 학생의 기록이 아닙니다." eyebrow="DO:DREAM 교사 흐름 체험" />
    <section className="learn-card"><h2>자료에서 학습까지</h2><ol className="showcase-process"><li><strong>자료 준비</strong><span>공개 샘플 교재 2개를 준비했어요.</span></li><li><strong>읽기와 질문</strong><span>단원과 연결된 문장으로 이해를 도와요.</span></li><li><strong>풀이 살펴보기</strong><span>같은 탭의 선택형 퀴즈 결과를 확인해요.</span></li></ol><p className="learn-small">실제 업로드·문서 변환·공유·외부 저장은 이 체험에서 제공하지 않습니다. 다른 기기와 기록을 공유하지 않습니다.</p></section>
    <section className="learn-card"><h2>샘플 자료</h2><ul className="showcase-list">{port.samples.map(sample => <li key={sample.id}><Link to={`/learn/${sample.id}`}>{sample.title}</Link><span>{sample.sections.length}개 단원 · {sample.quiz.length}개 문제 · 공개 샘플</span></li>)}</ul></section>
    <section className="learn-card" data-testid="teacher-results"><h2>이 탭의 풀이 결과</h2>{results.length ? <ul className="showcase-list">{results.map(({ sample, result }) => <li key={`${sample.id}-${result.attemptNumber}`}><Link to={`/learn/${sample.id}/results/run-${result.attemptNumber}`}>{sample.title} · {result.attemptNumber}번째 풀이</Link><span>샘플 결과 · {result.total}문제 중 {result.score}문제 정답</span></li>)}</ul> : <p>아직 체험한 풀이가 없습니다. 학생 화면에서 퀴즈를 풀면 여기에 표시됩니다.</p>}</section>
    <section className="learn-card"><h2>이 탭에서 살펴본 질문</h2>{questions.length ? <ul className="showcase-list">{questions.map(({ sample, question }) => <li key={question.id}><strong>{question.question}</strong><span>{sample.title} · 준비된 샘플 답변</span><p>{question.answer}</p></li>)}</ul> : <p>아직 살펴본 질문이 없습니다. 학생 화면의 추천 질문으로 시작해보세요.</p>}</section><Link className="learn-primary" to="/learn">학생 자료함으로</Link>
  </>;
}

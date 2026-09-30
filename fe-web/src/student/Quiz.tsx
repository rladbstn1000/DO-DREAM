import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { authSession } from '../auth/client';
import { LearningLayout, Notice } from './Layout';
import { useStudentSession } from './Session';
import { denied, studentJson, studentRequest } from './api';
import { canonicalId, isUuid, modeLabel, questions, type Mode, type Question } from './model';
import { createStudentSubmission, parseResults, type View, type Result } from './submission';

const initial: View = { state: 'IDLE', busy: false, retryable: false };
const messages: Record<View['state'], string> = {
  IDLE: '답안을 적은 뒤 제출해주세요.', SUBMITTING: '답안을 제출하고 있습니다.', READY: '채점 실행을 기다리고 있습니다.',
  PROCESSING: '채점이 진행 중입니다. 잠시 뒤 같은 제출의 상태를 확인해주세요.', SUCCEEDED: '채점 결과가 저장되었습니다.',
  FAILED: '채점이 실패한 것으로 확인되었습니다. 오답이나 0점을 뜻하지 않습니다.',
  UNKNOWN: '결과 불명: 서버가 답안을 받았을 수 있습니다. 같은 제출의 상태를 먼저 확인해주세요.',
  REVOKED: '자료가 없거나 공유 권한이 회수되었습니다. 답안과 결과를 표시하지 않습니다.',
  VERSION_CONFLICT: '문제가 변경되었습니다. 최신 문제를 확인한 뒤 새 풀이를 시작해주세요.',
  CONFLICT: '제출 내용이 기존 요청과 다릅니다. 새 key로 우회하지 않고 기존 제출을 확인해주세요.',
  RETRY_LIMIT: '이 제출의 재시도 한도를 초과했습니다. 결과 확인만 할 수 있습니다.',
  REJECTED: '답안을 접수하지 못했습니다. 문제와 답안 형식을 확인해주세요.',
  SESSION_CHANGED: '로그인이 변경되었습니다. 현재 계정을 확인해주세요.',
  STORAGE_UNAVAILABLE: '이 탭의 제출 정보를 저장할 수 없어 안전한 제출 복구를 보장할 수 없습니다. 이번 제출은 중단합니다.',
};
function SubmissionStatus({ view }: { view: View }) {
  return <div className="learn-submission-state" data-grading-state={view.state}><Notice error={['FAILED', 'UNKNOWN', 'REVOKED', 'VERSION_CONFLICT', 'CONFLICT', 'RETRY_LIMIT', 'REJECTED', 'STORAGE_UNAVAILABLE'].includes(view.state)}>{messages[view.state]}</Notice>
    {view.generation !== undefined && <p className="learn-small">채점 실행 {view.generation} / 최대 3회</p>}{view.storageWarning && <Notice error>완료된 제출 정보를 이 탭에서 지우지 못했습니다. 다음 화면에서도 서버 결과를 다시 확인합니다.</Notice>}</div>;
}
function Results({ results }: { results: Result[] }) {
  return <><section className="learn-card learn-result-summary" aria-label="채점 요약"><span className="learn-eyebrow">제출 당시 문제 기준</span><h2>{results.length}문제 중 {results.filter(r => r.is_correct).length}문제 정답</h2><p>아래 내용은 서버가 저장한 채점 결과입니다. 실패한 요청을 점수로 표시하지 않습니다.</p></section>
    <div className="learn-result-list">{results.map((result, i) => <article className="learn-card" key={result.question_id}><div className="learn-section-row"><h2>문제 {i + 1}</h2><span className={`learn-pill ${result.is_correct ? 'learn-correct' : 'learn-incorrect'}`}>{result.is_correct ? '정답' : '다시 생각해보기'}</span></div>
      {result.snapshotAvailable ? <p className="learn-result-question">{result.questionContent}</p> : <Notice>과거 문제의 snapshot이 없어 당시 문제와 채점 기준을 확인할 수 없습니다.</Notice>}
      <dl className="learn-result-detail"><dt>내 답안</dt><dd>{result.student_answer || '(답안 없음)'}</dd><dt>제출 당시 정답</dt><dd>{result.snapshotAvailable ? result.correct_answer : '당시 정답을 확인할 수 없음'}</dd><dt>피드백</dt><dd>{result.ai_feedback}</dd></dl>
    </article>)}</div></>;
}
function GradingMode() {
  const [mode, setMode] = useState<Mode | null>(null);
  useEffect(() => { const abort = new AbortController(); studentJson('/rag/mode', { signal: abort.signal }).then(value => { if (!abort.signal.aborted) setMode(value); }).catch(() => {}); return () => abort.abort(); }, []);
  return <p className="learn-mode">{mode?.grading_provider === 'local_stub' ? '로컬 대역 채점 · 실제 서버 제출 및 결과 저장' : '채점 실행 모드 확인 필요 · 실제 AI 품질은 검증하지 않았습니다'}<span className="learn-sr-only">{modeLabel(mode)}</span></p>;
}
export function QuizPage() {
  const { materialId: raw } = useParams(); const materialId = canonicalId(raw);
  const { user } = useStudentSession(); const navigate = useNavigate();
  const [items, setItems] = useState<Question[] | null>(null); const [answers, setAnswers] = useState<Record<number, string>>({});
  const [view, setView] = useState<View>(initial); const [error, setError] = useState(''); const [version, setVersion] = useState(0);
  const [confirmUnknown, setConfirmUnknown] = useState(false); const [lastAttempt, setLastAttempt] = useState<string | null>(null);
  const client = useRef<ReturnType<typeof createStudentSubmission> | null>(null);
  const epoch = authSession.getEpoch();
  useEffect(() => {
    const abort = new AbortController(); let alive = true; setItems(null); setError(''); setAnswers({}); setView(initial); setLastAttempt(null);
    if (!materialId || !user) { setError('자료가 없거나 현재 공유 권한이 없습니다.'); return; }
    studentJson(`/api/materials/${materialId}/quizzes`, { signal: abort.signal }).then(value => {
      const parsed = questions(value); if (!alive || epoch !== authSession.getEpoch()) return;
      const submission = createStudentSubmission({ userId: user.userId, materialId, questions: parsed, storage: { getItem: key => window.sessionStorage.getItem(key), setItem: (key, value) => window.sessionStorage.setItem(key, value), removeItem: key => window.sessionStorage.removeItem(key) },
        getEpoch: authSession.getEpoch, request: (path, method, body, key) => studentRequest(path, { method, ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
          headers: key ? { 'Idempotency-Key': key } : {} }), changed: next => { if (alive) setView(next); } });
      client.current = submission; setItems(parsed); setView(submission.getView());
      const pending = submission.getPending(); if (pending) setAnswers(Object.fromEntries(pending.answers.map(a => [a.quizId, a.answer])));
      try { const previous = sessionStorage.getItem(`dodream.student.result.${user.userId}.${materialId}`); if (isUuid(previous)) setLastAttempt(previous); } catch { /* Optional navigation hint only. */ }
    }).catch(cause => { if (alive && !abort.signal.aborted) setError(denied(cause) ? '자료가 없거나 현재 공유 권한이 없습니다.' : '퀴즈를 불러오지 못했습니다. 다시 확인해주세요.'); });
    return () => { alive = false; abort.abort(); client.current?.dispose(); client.current = null; };
  }, [materialId, user?.userId, version, epoch]);
  useEffect(() => {
    if (view.state === 'SUCCEEDED' && view.attemptId && materialId && user) {
      try { sessionStorage.setItem(`dodream.student.result.${user.userId}.${materialId}`, view.attemptId); } catch { /* Result URL is independently reloadable. */ }
      navigate(`/learn/${materialId}/results/${view.attemptId}`, { replace: true });
    }
  }, [view.state, view.attemptId, materialId, user, navigate]);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!client.current || !items || view.busy) return;
    await client.current.submit(items.map(q => ({ quizId: q.id, version: q.version, answer: answers[q.id] || '' })));
  }
  const frozen = !!client.current?.getPending();
  const allowed = items && view.state !== 'REVOKED';
  return <LearningLayout title="배운 내용을 확인해요" subtitle="정답은 제출한 뒤 확인할 수 있어요. 천천히 내 생각을 적어보세요.">
    <Link className="learn-back" to={materialId ? `/learn/${materialId}` : '/learn'}>← 본문으로 돌아가기</Link><GradingMode />
    {error && <Notice error>{error}</Notice>}{!items && !error && <Notice>학생용 문제와 버전을 확인하고 있습니다.</Notice>}
    {error && <button onClick={() => setVersion(n => n + 1)}>문제 다시 확인</button>}
    {items?.length === 0 && <Notice>이 자료에는 아직 퀴즈가 없습니다. 본문으로 돌아가 계속 읽을 수 있습니다.</Notice>}
    {allowed && <form onSubmit={event => void submit(event)} className="learn-quiz-form">{items.map((q, i) => <section className="learn-card" key={q.id}><span className="learn-eyebrow">문제 {i + 1} / {items.length}</span><h2 id={`question-${q.id}`}>{q.content}</h2>
      <label htmlFor={`answer-${q.id}`}>문제 {i + 1} 답안</label><textarea id={`answer-${q.id}`} value={answers[q.id] || ''} onChange={event => setAnswers(a => ({ ...a, [q.id]: event.target.value }))} disabled={frozen || view.busy} rows={3} maxLength={4000} aria-describedby={`answer-help-${q.id}`} aria-invalid={Array.from(answers[q.id] || '').length > 2000} />
      <p id={`answer-help-${q.id}`} className="learn-small">최대 2,000자. 문제 버전 {q.version}로 제출합니다.</p></section>)}
      {items.length > 0 && !frozen && <button className="learn-primary" disabled={view.busy || items.some(q => Array.from(answers[q.id] || '').length > 2000)}>제출하기</button>}
    </form>}
    {items && <SubmissionStatus view={view} />}
    {frozen && !['SUCCEEDED', 'REVOKED', 'SESSION_CHANGED'].includes(view.state) && <section className="learn-card"><h2>진행 중인 제출</h2><p>답안과 문제 버전이 고정되어 있습니다. 새로고침 후에도 현재 계정을 확인한 뒤 같은 요청으로 결과를 확인합니다. 이 탭을 닫으면 복구 정보를 잃을 수 있습니다.</p>
      <button className="learn-primary" disabled={view.busy} onClick={() => void client.current?.check()}>같은 제출 확인</button>
      {view.retryable && <div className="learn-retry">{view.state === 'UNKNOWN' && <label><input type="checkbox" checked={confirmUnknown} onChange={event => setConfirmUnknown(event.target.checked)} />이전 실행 결과가 불명임을 확인하고 같은 제출을 재시도합니다.</label>}
        <button disabled={view.busy || view.state === 'UNKNOWN' && !confirmUnknown} onClick={() => void client.current?.retry(confirmUnknown)}>채점 재시도</button></div>}
      {view.state === 'VERSION_CONFLICT' && <button disabled={view.busy} onClick={() => { if (client.current?.reset()) { setVersion(n => n + 1); setConfirmUnknown(false); } }}>최신 문제로 새 풀이 시작</button>}
    </section>}
    {lastAttempt && <Link className="learn-back" to={`/learn/${materialId}/results/${lastAttempt}`}>결과 보기</Link>}
  </LearningLayout>;
}
export function ResultPage() {
  const { materialId: raw, attemptId } = useParams(); const materialId = canonicalId(raw);
  const [view, setView] = useState<View | null>(null); const [error, setError] = useState(''); const [version, setVersion] = useState(0);
  useEffect(() => {
    const abort = new AbortController(); setView(null); setError('');
    if (!materialId || !isUuid(attemptId)) { setError('결과 주소를 확인할 수 없습니다.'); return; }
    studentRequest(`/api/materials/${materialId}/quiz-attempts/${attemptId}`, { signal: abort.signal }).then(response => {
      if (abort.signal.aborted) return;
      if (response.status === 403 || response.status === 404) { setView({ state: 'REVOKED', busy: false, retryable: false }); return; }
      if (response.attemptId !== attemptId) throw new Error('Wrong attempt');
      if (response.status === 200 && response.state === 'SUCCEEDED') setView({ state: 'SUCCEEDED', busy: false, retryable: false, attemptId, results: parseResults(response.data) });
      else {
        const data = response.data;
        const states: Record<string, number> = { READY: 202, PROCESSING: 202, FAILED: 502, UNKNOWN: 503, REVOKED: 409 };
        if (data?.attemptId !== attemptId || states[data?.state] !== response.status || !Number.isSafeInteger(data.generation)) throw new Error('Invalid state');
        setView({ state: data.state, busy: false, retryable: false, generation: data.generation, attemptId });
      }
    }).catch(() => { if (!abort.signal.aborted) setError('결과를 확인하지 못했습니다. 같은 결과를 다시 확인해주세요.'); });
    return () => abort.abort();
  }, [materialId, attemptId, version]);
  return <LearningLayout title="퀴즈 결과" subtitle="내가 제출한 당시의 문제와 서버가 확정한 피드백을 다시 확인해요."><GradingMode />
    {!view && !error && <Notice>현재 권한과 제출 결과를 확인하고 있습니다.</Notice>}{error && <Notice error>{error}</Notice>}
    {view && <SubmissionStatus view={view} />}{view?.results && <Results results={view.results} />}
    {(error || view && ['READY', 'PROCESSING', 'FAILED', 'UNKNOWN'].includes(view.state)) && <button onClick={() => setVersion(n => n + 1)}>결과 다시 확인</button>}
    <div className="learn-button-row">{materialId && <><Link className="learn-primary" to={`/learn/${materialId}`}>본문으로 돌아가기</Link><Link to={`/learn/${materialId}/quiz`}>{view?.state === 'SUCCEEDED' ? '새 풀이 시작' : '진행 중인 제출 확인'}</Link></>}<Link to="/learn">자료함</Link></div>
  </LearningLayout>;
}

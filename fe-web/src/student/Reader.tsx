import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { authSession } from '../auth/client';
import { LearningLayout, Notice, ReaderSpeech, useFence } from './Layout';
import { useStudentSession } from './Session';
import { denied, StudentApiError, studentJson } from './api';
import { canonicalId, chapters, isUuid, materials, modeLabel, positiveId, readiness, source, studentIndex,
  type Chapter, type ChatMessage, type Material, type Mode, type Source, type StudentIndex } from './model';

export type Document = { material: Material; chapters: Chapter[]; indexing: StudentIndex | null };
export function useMaterial(materialId: number | null) {
  const [document, setDocument] = useState<Document | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  const [revoked, setRevoked] = useState(false);
  const generation = useRef(0);
  const epoch = useRef(authSession.getEpoch());
  async function load() {
    const mine = ++generation.current;
    setBusy(true); setError(''); setDocument(null);
    try {
      if (!materialId) throw new StudentApiError(404);
      const [list, json] = await Promise.all([studentJson('/api/materials/shared'), studentJson(`/api/materials/shared/${materialId}/json`)]);
      const material = materials(list).find(d => d.materialId === materialId);
      if (!material) throw new StudentApiError(404);
      const value = { material, chapters: chapters(json), indexing: studentIndex(json?.indexing) };
      if (mine !== generation.current || epoch.current !== authSession.getEpoch()) throw new Error('Stale material');
      setDocument(value); setRevoked(false);
      return value;
    } catch (cause) {
      if (mine === generation.current && epoch.current === authSession.getEpoch()) {
        setDocument(null); setRevoked(denied(cause));
        setError(denied(cause) ? '자료가 없거나 현재 공유 권한이 없습니다. 저장된 본문과 참고 자료를 표시하지 않습니다.' : '자료를 확인하지 못했습니다. 다시 확인해주세요.');
      }
      throw cause;
    } finally { if (mine === generation.current) setBusy(false); }
  }
  function revoke() {
    generation.current++; setDocument(null); setBusy(false); setRevoked(true);
    setError('자료가 없거나 현재 공유 권한이 없습니다. 저장된 본문과 참고 자료를 표시하지 않습니다.');
    window.speechSynthesis?.cancel();
  }
  useEffect(() => {
    void load().catch(() => {});
    const visible = () => { if (documentVisibility()) void load().catch(() => {}); else { generation.current++; setDocument(null); window.speechSynthesis?.cancel(); } };
    window.document.addEventListener('visibilitychange', visible);
    return () => { generation.current++; window.document.removeEventListener('visibilitychange', visible); };
  }, [materialId]);
  return { document, error, busy, revoked, load, revoke };
}
const documentVisibility = () => window.document.visibilityState === 'visible';

export function ReaderPage() {
  const { materialId: raw } = useParams();
  const materialId = canonicalId(raw);
  const material = useMaterial(materialId);
  const [params, setParams] = useSearchParams();
  const [size, setSize] = useState(1);
  const [progress, setProgress] = useState<{ totalSections: number; completedAt?: string } | null>(null);
  const [progressText, setProgressText] = useState('');
  const [saving, setSaving] = useState(false);
  const fence = useFence();
  const heading = useRef<HTMLHeadingElement>(null);
  const doc = material.document;
  const index = Math.min(Math.max(0, Number(params.get('chapter') || 1) - 1 || 0), Math.max(0, (doc?.chapters.length ?? 1) - 1));
  const chapter = doc?.chapters[index];
  useEffect(() => {
    if (!materialId) return;
    const abort = new AbortController();
    studentJson(`/api/progress/materials/${materialId}`, { signal: abort.signal }).then(data => {
      if (!abort.signal.aborted && positiveId(data?.data?.totalSections)) setProgress(data.data);
    }).catch(() => { if (!abort.signal.aborted) setProgressText('학습 진도를 확인하지 못했습니다. 본문은 계속 읽을 수 있어요.'); });
    return () => abort.abort();
  }, [materialId]);
  async function complete() {
    if (!progress || saving || !materialId) return;
    setSaving(true); setProgressText(''); const generation = fence.capture();
    try {
      const response = await studentJson('/api/progress/update', { method: 'POST', body: JSON.stringify({ materialId, currentPage: progress.totalSections, totalPages: progress.totalSections }) });
      if (fence.current(generation)) setProgressText(response?.data?.completed === true ? '학습 완료가 저장되었습니다.' : '서버에서 학습 위치를 저장했습니다.');
    } catch (cause) { if (fence.current(generation)) { if (denied(cause)) material.revoke(); else setProgressText('학습 완료 저장을 확인하지 못했습니다. 다시 확인해주세요.'); } }
    finally { if (fence.current(generation)) setSaving(false); }
  }
  return <LearningLayout title={doc?.material.materialTitle || '학습 자료'} subtitle="글을 읽고, 참고 자료와 함께 궁금한 것을 물어보세요.">
    <Link className="learn-back" to="/learn">← 자료함</Link>
    {material.busy && <Notice>현재 공유 권한과 본문을 확인하고 있습니다.</Notice>}
    {material.error && <Notice error>{material.error}</Notice>}
    {!material.busy && !doc && <button onClick={() => void material.load().catch(() => {})}>자료 다시 확인</button>}
    {doc && <><div className="learn-section-row"><span className="learn-pill">{readiness(doc.indexing)}</span><Link className="learn-primary" to={`/learn/${materialId}/quiz`}>퀴즈 풀기</Link></div>
      {!doc.indexing?.readable ? <Notice>현재 자료의 색인이 준비되지 않았습니다. <button onClick={() => void material.load().catch(() => {})}>준비 상태 확인</button></Notice> : <>
      <div className="learn-reader-grid"><aside className="learn-card learn-chapters"><h2>단원</h2><nav aria-label="단원 선택">{doc.chapters.map((c, i) => <button key={c.id} aria-current={i === index ? 'step' : undefined} onClick={() => { setParams({ chapter: String(i + 1) }); requestAnimationFrame(() => heading.current?.focus()); }}><span>{i + 1}</span>{c.title}</button>)}</nav></aside>
        <article className="learn-card learn-reading"><div className="learn-section-row"><span className="learn-eyebrow">{index + 1} / {doc.chapters.length} 단원</span><div className="learn-button-row" aria-label="글자 크기"><button aria-label="글자 작게" disabled={size <= 0} onClick={() => setSize(n => n - 1)}>가 −</button><button aria-label="글자 크게" disabled={size >= 3} onClick={() => setSize(n => n + 1)}>가 +</button></div></div>
          <h2 ref={heading} tabIndex={-1}>{chapter?.title || '본문이 없습니다'}</h2><div className={`learn-reading-text learn-size-${size}`}>{chapter?.text.split(/\n\s*\n/).map((paragraph, i) => <p key={i}>{paragraph}</p>)}</div>
          {chapter && <ReaderSpeech text={chapter.text} />}
          <div className="learn-section-row"><button disabled={index === 0} onClick={() => { setParams({ chapter: String(index) }); requestAnimationFrame(() => heading.current?.focus()); }}>이전 단원</button><button disabled={index >= doc.chapters.length - 1} onClick={() => { setParams({ chapter: String(index + 2) }); requestAnimationFrame(() => heading.current?.focus()); }}>다음 단원</button></div>
          {index === doc.chapters.length - 1 && <div className="learn-complete"><p>글을 모두 읽었다면 완료를 눌러주세요. 이 버튼을 누를 때만 학습 진도를 저장합니다.</p><button disabled={!progress || saving} onClick={() => void complete()}>학습 완료</button></div>}
          {progressText && <Notice>{progressText}</Notice>}{progress?.completedAt && <p className="learn-small">이 자료의 완료 기록이 있습니다.</p>}
        </article></div>
      <QuestionPanel materialId={materialId!} currentRevision={doc.indexing.sourceRevision} onDenied={material.revoke} onReload={() => material.load()} />
      </>}
    </>}
  </LearningLayout>;
}

function QuestionPanel({ materialId, currentRevision, onDenied, onReload }: { materialId: number; currentRevision: number; onDenied: () => void; onReload: () => Promise<Document> }) {
  const { user } = useStudentSession();
  const [question, setQuestion] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [mode, setMode] = useState<Mode | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [changed, setChanged] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [sessions, setSessions] = useState<{ id: string; session_title: string }[]>([]);
  const [selected, setSelected] = useState<Source | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const sourceTrigger = useRef<HTMLButtonElement | null>(null);
  const inFlight = useRef(false);
  const fence = useFence();
  const storageKey = `dodream.student.chat.${user!.userId}.${materialId}`;
  useEffect(() => {
    try { const stored = sessionStorage.getItem(storageKey); if (isUuid(stored)) setSessionId(stored); } catch { /* History remains available from server. */ }
    const abort = new AbortController();
    studentJson('/rag/mode', { signal: abort.signal }).then(value => { if (!abort.signal.aborted) setMode(value); }).catch(() => {});
    return () => abort.abort();
  }, [storageKey]);
  useEffect(() => { if (selected) dialog.current?.showModal(); else dialog.current?.close(); }, [selected]);
  function failed(cause: unknown) {
    if (denied(cause)) { setMessages([]); setSelected(null); onDenied(); return; }
    if (cause instanceof StudentApiError && cause.code === 'RAG_SOURCE_CHANGED') {
      setChanged(true); setSelected(null); setMessages(old => old.map(m => ({ ...m, sources: [] })));
      setError('자료가 새 버전으로 바뀌었습니다. 이전 대화 기록은 유지하고 새 자료로 대화를 시작해주세요.');
    } else if (cause instanceof StudentApiError && cause.code === 'INDEX_NOT_READY') setError('자료의 색인을 준비하고 있습니다. 준비 완료 후 다시 질문해주세요.');
    else if (cause instanceof StudentApiError && cause.code === 'INDEX_STORAGE_UNAVAILABLE') setError('자료 검색 저장소를 사용할 수 없습니다. 답변을 만들지 않았습니다.');
    else { setUncertain(true); setError('답변 응답을 확인하지 못했습니다. 서버에 대화가 저장되었을 수 있습니다. 대화 기록을 확인한 뒤 직접 다시 보내주세요.'); }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || !question.trim() || Array.from(question).length > 2000 || changed) return;
    inFlight.current = true; setBusy(true); setError(''); const generation = fence.capture();
    const submitted = question;
    try {
      const data = await studentJson('/rag/chat', { method: 'POST', body: JSON.stringify({ document_id: String(materialId), question: submitted, ...(sessionId ? { session_id: sessionId } : {}) }) });
      if (!isUuid(data.session_id) || !positiveId(data.message_id) || typeof data.answer !== 'string' || String(data.document_id) !== String(materialId) || !Array.isArray(data.sources)) throw new Error('Invalid answer');
      const sources = data.sources.map((d: unknown) => source(d, materialId));
      if (sources.some((s: Source) => s.source_revision !== data.source_revision || s.source_hash !== data.source_hash)) throw new Error('Source mismatch');
      if (!fence.current(generation)) return;
      setSessionId(data.session_id); try { sessionStorage.setItem(storageKey, data.session_id); } catch { /* Server history still exists. */ }
      setMessages(old => [...old, { id: -Date.now(), role: 'user', content: submitted }, { id: data.message_id, role: 'ai', content: data.answer, sources, mode: data.mode }]);
      setMode(data.mode); setQuestion(''); setUncertain(false);
    } catch (cause) { if (fence.current(generation)) failed(cause); }
    finally { inFlight.current = false; if (fence.current(generation)) setBusy(false); }
  }
  async function history(id?: string) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(''); const generation = fence.capture();
    try {
      const target = id ?? sessionId;
      if (!target) {
        const data = await studentJson(`/rag/chat/sessions?student_id=${user!.userId}`);
        if (!Array.isArray(data)) throw new Error();
        if (fence.current(generation)) { setSessions(data.filter(d => String(d.document_id) === String(materialId) && isUuid(d.id))); setError('확인할 대화를 선택해주세요. 목록이 비어 있으면 저장된 대화를 찾지 못한 상태입니다. 다시 보내면 새 질문이 될 수 있습니다.'); }
        return;
      }
      const data = await studentJson(`/rag/chat/sessions/${target}/messages?student_id=${user!.userId}`);
      if (String(data.document_id) !== String(materialId) || !Array.isArray(data.messages)) throw new Error();
      const outdated = data.source_revision !== currentRevision;
      const parsed = data.messages.map((m: ChatMessage) => {
        if (!positiveId(m.id) || !['ai', 'user'].includes(m.role) || typeof m.content !== 'string') throw new Error();
        return { id: m.id, role: m.role, content: m.content, mode: m.mode, sources: outdated ? [] : (m.sources ?? []).map(s => source(s, materialId)) };
      });
      if (fence.current(generation)) { setSessionId(target); setMessages(parsed); setSessions([]); setUncertain(false); setChanged(outdated);
        if (outdated) setError('이 대화는 이전 자료 버전입니다. 새 자료로 대화를 시작해주세요.'); }
    } catch (cause) { if (fence.current(generation)) failed(cause); }
    finally { inFlight.current = false; if (fence.current(generation)) setBusy(false); }
  }
  async function openSource(message: ChatMessage, index: number, trigger: HTMLButtonElement) {
    if (!sessionId || inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(''); const generation = fence.capture();
    try {
      const expected = message.sources![index];
      const verified = source(await studentJson(`/rag/chat/sessions/${sessionId}/messages/${message.id}/sources/${index}?student_id=${user!.userId}`), materialId);
      if (verified.source_hash !== expected.source_hash || verified.source_revision !== expected.source_revision || verified.content_hash !== expected.content_hash) throw new StudentApiError(409, { code: 'RAG_SOURCE_CHANGED' });
      if (fence.current(generation)) { sourceTrigger.current = trigger; setSelected(verified); }
    } catch (cause) { if (fence.current(generation)) failed(cause); }
    finally { inFlight.current = false; if (fence.current(generation)) setBusy(false); }
  }
  return <section className="learn-card learn-question" aria-labelledby="question-title"><div className="learn-section-row"><div><span className="learn-eyebrow">ASK & FIND</span><h2 id="question-title">자료에 질문하기</h2></div><span className="learn-pill">{modeLabel(mode)}</span></div>
    <p>답변에 사용한 본문 발췌를 함께 확인하세요. 자료를 검색했다는 사실이 답변의 정확성을 보장하지는 않습니다.</p>
    <div className="learn-conversation" aria-label="질문과 답변">{messages.map(message => <article key={message.id} className={`learn-message ${message.role === 'user' ? 'learn-my-question' : ''}`}><h3>{message.role === 'user' ? '나의 질문' : '자료를 참고한 답변'}</h3><p>{message.content}</p>
      {message.role === 'ai' && <p className="learn-small">{modeLabel(message.mode)}</p>}
      {message.sources?.map((s, i) => <button key={`${s.chunk_position}-${i}`} disabled={busy || changed} onClick={event => void openSource(message, i, event.currentTarget)}>참고 자료 보기{message.sources!.length > 1 ? ` ${i + 1}` : ''}</button>)}
    </article>)}</div>
    {busy && <Notice>요청을 확인하고 있습니다. 중복해서 보내지 않아도 괜찮아요.</Notice>}{error && <Notice error>{error}</Notice>}
    {changed ? <button className="learn-primary" onClick={() => { setSessionId(null); setMessages([]); setChanged(false); setError(''); setUncertain(false); try { sessionStorage.removeItem(storageKey); } catch { /* optional hint */ } void onReload().catch(() => {}); }}>새 자료로 대화 시작</button> :
      <form onSubmit={event => void send(event)}><label htmlFor="learning-question">질문</label><textarea id="learning-question" value={question} onChange={event => setQuestion(event.target.value)} rows={3} maxLength={4000} aria-describedby="question-help" disabled={busy} placeholder="글에서 궁금했던 내용을 적어보세요." />
        <p id="question-help" className="learn-small">최대 2,000자. {uncertain ? '응답이 유실되었을 수 있습니다. 기록 확인 없이 다시 보내면 중복 질문이 될 수 있어요.' : '질문은 직접 보내기를 누를 때 전송됩니다.'}</p>
        <button className="learn-primary" disabled={busy || !question.trim() || Array.from(question).length > 2000}>질문 보내기</button></form>}
    <button className="learn-history" disabled={busy} onClick={() => void history()}>대화 기록 확인</button>{sessions.map(s => <button key={s.id} disabled={busy} onClick={() => void history(s.id)}>{s.session_title || '저장된 대화'} 확인</button>)}
    <dialog ref={dialog} className="learn-source-dialog" aria-labelledby="source-title" onClose={() => { setSelected(null); sourceTrigger.current?.focus(); }}><h2 id="source-title">답변에 사용한 본문 발췌</h2>{selected && <><p className="learn-eyebrow">{selected.material_title || '현재 학습 자료'} · 자료 버전 {selected.source_revision}</p><blockquote>{selected.excerpt}</blockquote><p className="learn-small">현재 공유 권한과 답변 당시 자료 버전을 서버에서 다시 확인했습니다. 실제 검색된 발췌이며 전체 단원이나 페이지를 뜻하지 않습니다.</p></>}<button onClick={() => dialog.current?.close()}>참고 자료 닫기</button></dialog>
  </section>;
}

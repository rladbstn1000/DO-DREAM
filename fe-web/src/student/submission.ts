import { isUuid, positiveId, revision } from './model.ts';
import type { Question } from './model.ts';
export type Answer = { quizId: number; version: number; answer: string };
export type Result = { question_id: number; version?: number; questionContent?: string; snapshotAvailable: boolean;
  is_correct: boolean; student_answer: string; correct_answer: string; ai_feedback: string };
export type Pending = { schema: 1; userId: number; materialId: number; key: string; answers: Answer[];
  attemptId?: string; retry?: { expectedGeneration: number; confirmUnknown: boolean } };
export type View = { state: 'IDLE' | 'SUBMITTING' | 'READY' | 'PROCESSING' | 'SUCCEEDED' | 'FAILED' | 'UNKNOWN' | 'REVOKED' |
  'VERSION_CONFLICT' | 'CONFLICT' | 'RETRY_LIMIT' | 'REJECTED' | 'SESSION_CHANGED' | 'STORAGE_UNAVAILABLE';
  busy: boolean; attemptId?: string; generation?: number; retryable: boolean; results?: Result[]; code?: string; storageWarning?: boolean };
type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
type Response = { status: number; data: unknown; attemptId?: string; state?: string };
export const pendingPrefix = 'dodream.student.pending.v1.';
export const pendingKey = (userId: number, materialId: number) => `${pendingPrefix}${userId}.${materialId}`;
const validAnswers = (answers: unknown): answers is Answer[] => Array.isArray(answers) && answers.length > 0 && answers.length <= 50 &&
  new Set(answers.map(a => a?.quizId)).size === answers.length && answers.every(a => a && positiveId(a.quizId) && revision(a.version) &&
    typeof a.answer === 'string' && Array.from(a.answer).length <= 2000);
export class PendingStorageError extends Error {}
export function readPending(storage: StorageLike, userId: number, materialId: number): Pending | null {
  const key = pendingKey(userId, materialId);
  let raw: string | null;
  try { raw = storage.getItem(key); } catch { throw new PendingStorageError('Pending storage unreadable'); }
  try {
    if (!raw) return null;
    if (raw.length > 500000) throw new Error('Storage too large');
    const d = JSON.parse(raw) as Pending;
    if (d.schema !== 1 || d.userId !== userId || d.materialId !== materialId || !isUuid(d.key) || !validAnswers(d.answers) ||
      (d.attemptId !== undefined && !isUuid(d.attemptId)) || d.retry && (!d.attemptId || !revision(d.retry.expectedGeneration) ||
      d.retry.expectedGeneration > 3 || typeof d.retry.confirmUnknown !== 'boolean')) throw new Error('Invalid pending data');
    // Storage is untrusted. Copy only the request fields; server authorization/version checks remain mandatory.
    return { schema: 1, userId, materialId, key: d.key, answers: d.answers.map(a => ({ quizId: a.quizId, version: a.version, answer: a.answer })),
      ...(d.attemptId ? { attemptId: d.attemptId } : {}), ...(d.retry ? { retry: { ...d.retry } } : {}) };
  } catch { try { storage.removeItem(key); if (storage.getItem(key) !== null) throw new Error(); } catch { throw new PendingStorageError('Invalid pending record could not be cleared'); } return null; }
}
export function parseResults(value: unknown): Result[] {
  if (!Array.isArray(value) || !value.length || value.length > 50) throw new Error('결과를 확인하지 못했습니다.');
  return value.map(d => {
    if (!positiveId(d.question_id) || typeof d.is_correct !== 'boolean' || typeof d.student_answer !== 'string' ||
      typeof d.correct_answer !== 'string' || typeof d.ai_feedback !== 'string') throw new Error('채점 결과 형식이 올바르지 않습니다.');
    if (d.snapshotAvailable === true && (!revision(d.version) || typeof d.questionContent !== 'string')) throw new Error('채점 당시 문제를 확인하지 못했습니다.');
    return { question_id: d.question_id, version: d.version, questionContent: d.questionContent, snapshotAvailable: d.snapshotAvailable === true,
      is_correct: d.is_correct, student_answer: d.student_answer, correct_answer: d.correct_answer, ai_feedback: d.ai_feedback };
  });
}
type Options = { userId: number; materialId: number; questions: Question[]; storage: StorageLike; getEpoch: () => number;
  request: (path: string, method: 'GET' | 'POST', body?: unknown, key?: string) => Promise<Response>;
  changed: (view: View) => void; makeKey?: () => string; wait?: (ms: number) => Promise<void>; timeout?: number };
/** A tab-scoped immutable logical submission. Only explicit recovery can issue another POST. */
export function createStudentSubmission(options: Options) {
  const epoch = options.getEpoch();
  const storageKey = pendingKey(options.userId, options.materialId);
  const prefix = `/api/materials/${options.materialId}`;
  let pending: Pending | null = null;
  let storageUnavailable = false;
  try { pending = readPending(options.storage, options.userId, options.materialId); } catch { storageUnavailable = true; }
  let view: View = { state: storageUnavailable ? 'STORAGE_UNAVAILABLE' : pending ? 'UNKNOWN' : 'IDLE', busy: false, retryable: false, attemptId: pending?.attemptId };
  let disposed = false;
  let flight: Promise<View> | null = null;
  const current = () => !disposed && options.getEpoch() === epoch;
  function publish(next: View) {
    view = current() ? next : { state: 'SESSION_CHANGED', busy: false, retryable: false };
    if (!disposed) options.changed(view);
    return view;
  }
  function save() {
    try {
      options.storage.setItem(storageKey, JSON.stringify(pending));
      if (options.storage.getItem(storageKey) !== JSON.stringify(pending)) throw new Error('Storage not durable');
      return true;
    } catch { publish({ ...view, state: 'STORAGE_UNAVAILABLE', busy: false, retryable: false }); return false; }
  }
  function clear() { try { options.storage.removeItem(storageKey); return options.storage.getItem(storageKey) === null; } catch { return false; } }
  function accept(response: Response) {
    if (!current()) throw new Error('Session changed');
    if (response.status === 200 && Array.isArray(response.data)) {
      if (!isUuid(response.attemptId) || response.state !== 'SUCCEEDED' || pending?.attemptId && pending.attemptId !== response.attemptId) throw new Error('Invalid attempt');
      const results = parseResults(response.data);
      if (pending && (results.length !== pending.answers.length || results.some(result => !result.snapshotAvailable ||
        !pending!.answers.some(answer => answer.quizId === result.question_id && answer.version === result.version)))) throw new Error('Snapshot mismatch');
      const storageWarning = !clear();
      return publish({ storageWarning, state: 'SUCCEEDED', busy: false, retryable: false, attemptId: response.attemptId, results });
    }
    const d = response.data as Record<string, unknown> | null;
    const code = typeof d?.code === 'string' ? d.code : '';
    if (response.status === 403 || response.status === 404) { clear(); return publish({ state: 'REVOKED', busy: false, retryable: false }); }
    if (response.status === 401) { clear(); return publish({ state: 'SESSION_CHANGED', busy: false, retryable: false }); }
    if (isUuid(d?.attemptId) && revision(d?.generation) && ['READY', 'PROCESSING', 'FAILED', 'UNKNOWN', 'REVOKED'].includes(String(d?.state))) {
      if (pending?.attemptId && pending.attemptId !== d!.attemptId) throw new Error('Attempt changed');
      const state = d!.state as View['state'];
      if (state === 'REVOKED') { clear(); pending = null; return publish({ state, busy: false, retryable: false }); }
      const expected = ['READY', 'PROCESSING'].includes(state) ? 202 : state === 'FAILED' ? 502 : state === 'UNKNOWN' ? 503 : 409;
      if (response.status !== expected) throw new Error('Invalid state');
      if (pending) { pending.attemptId = d!.attemptId as string; delete pending.retry; if (!save()) return view; }
      return publish({ state, busy: false, attemptId: d!.attemptId as string, generation: d!.generation as number,
        retryable: d!.retryable === true && Number(d!.generation) < 3 && ['READY', 'FAILED', 'UNKNOWN'].includes(state),
        code: typeof d?.failureCode === 'string' ? d.failureCode : undefined });
    }
    if (response.status === 409) return publish({ state: code === 'QUIZ_VERSION_CONFLICT' ? 'VERSION_CONFLICT' :
      code === 'RETRY_LIMIT_REACHED' ? 'RETRY_LIMIT' : 'CONFLICT', busy: false, retryable: false, code, attemptId: pending?.attemptId });
    if (response.status >= 400 && response.status < 500) return publish({ state: 'REJECTED', busy: false, retryable: false, code });
    throw new Error('Outcome unavailable');
  }
  async function send(path: string, method: 'GET' | 'POST', body?: unknown) {
    if (!current()) throw new Error('Session changed');
    let timer: ReturnType<typeof setTimeout>;
    try {
      const response = await Promise.race([options.request(path, method, body, pending?.key),
        new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Timeout')), options.timeout ?? 22000); })]);
      return accept(response);
    } finally { clearTimeout(timer!); }
  }
  async function observe() {
    for (let i = 0; i < 3 && current() && ['READY', 'PROCESSING'].includes(view.state) && pending?.attemptId; i++) {
      await (options.wait ?? (ms => new Promise(resolve => setTimeout(resolve, ms))))(1000);
      if (!current()) break;
      await send(`${prefix}/quiz-attempts/${pending.attemptId}`, 'GET');
    }
    return view;
  }
  function run(action: () => Promise<View>) {
    if (flight) return flight;
    if (!current()) return Promise.resolve(publish({ state: 'SESSION_CHANGED', busy: false, retryable: false }));
    publish({ ...view, busy: true });
    const promise = Promise.resolve().then(action).catch(() => publish({ ...view, state: 'UNKNOWN', busy: false, retryable: false, results: undefined }));
    flight = promise;
    void promise.finally(() => { if (flight === promise) flight = null; });
    return promise;
  }
  function check() {
    return run(async () => {
      if (!pending || view.state === 'SUCCEEDED') return publish({ ...view, busy: false });
      if (pending.retry) await send(`${prefix}/quiz-attempts/${pending.attemptId}/retry`, 'POST', pending.retry);
      else if (pending.attemptId) await send(`${prefix}/quiz-attempts/${pending.attemptId}`, 'GET');
      else await send(`${prefix}/quizzes/submit`, 'POST', { answers: pending.answers });
      return observe();
    });
  }
  function submit(answers: Answer[]) {
    if (storageUnavailable) return Promise.resolve(publish({ state: 'STORAGE_UNAVAILABLE', busy: false, retryable: false }));
    if (!current()) return Promise.resolve(publish({ state: 'SESSION_CHANGED', busy: false, retryable: false }));
    if (pending) return JSON.stringify(pending.answers) === JSON.stringify(answers) ? check() : Promise.resolve(publish({ ...view, state: 'CONFLICT', busy: false, retryable: false }));
    if (!validAnswers(answers) || answers.length !== options.questions.length || answers.some((a, i) => a.quizId !== options.questions[i].id || a.version !== options.questions[i].version)) {
      return Promise.resolve(publish({ state: 'REJECTED', busy: false, retryable: false }));
    }
    const key = (options.makeKey ?? (() => crypto.randomUUID()))();
    if (!isUuid(key)) return Promise.resolve(publish({ state: 'REJECTED', busy: false, retryable: false }));
    pending = { schema: 1, userId: options.userId, materialId: options.materialId, key, answers: answers.map(a => ({ ...a })) };
    if (!save()) { pending = null; return Promise.resolve(view); }
    publish({ state: 'SUBMITTING', busy: false, retryable: false });
    return check();
  }
  function retry(confirmUnknown: boolean) {
    if (!pending || !view.retryable || view.generation === undefined || view.state === 'UNKNOWN' && !confirmUnknown) return Promise.resolve(view);
    if (pending.retry) return check();
    pending.retry = { expectedGeneration: view.generation, confirmUnknown };
    if (!save()) return Promise.resolve(view);
    return check();
  }
  return { submit, check, retry, getView: () => view, getPending: () => pending,
    reset: () => { if (flight || storageUnavailable) return false; if (!clear()) { publish({ state: 'STORAGE_UNAVAILABLE', busy: false, retryable: false }); return false; } pending = null; publish({ state: 'IDLE', busy: false, retryable: false }); return true; },
    dispose: () => { disposed = true; } };
}

import type { QuizQuestion } from '../types/quiz';
import type { QuizAnswerPayload, QuizGradingResultItem, RawQuizGradingResult } from '../types/api/quizApiTypes';

export type GradingState = 'IDLE' | 'READY' | 'PROCESSING' | 'SUCCEEDED' | 'FAILED' | 'UNKNOWN' | 'REVOKED'
  | 'VERSION_CONFLICT' | 'CONFLICT' | 'REJECTED' | 'SESSION_CHANGED';
export type SubmissionView = {
  state: GradingState;
  attemptId?: string;
  generation?: number;
  retryable: boolean;
  results?: QuizGradingResultItem[];
};
export type SubmissionRequest = {
  method: 'GET' | 'POST'; path: string; key: string; body?: unknown;
};
export type SubmissionResponse = {
  status: number; data: unknown; attemptId?: string; state?: string;
};
type Options = {
  materialId: number | string;
  questions: QuizQuestion[];
  session: () => number | null;
  request: (request: SubmissionRequest) => Promise<SubmissionResponse>;
  mergeResults: (questions: QuizQuestion[], results: RawQuizGradingResult[]) => QuizGradingResultItem[];
  makeKey?: () => string;
  wait?: (milliseconds: number) => Promise<void>;
  requestTimeoutMs?: number;
  changed?: (view: SubmissionView) => void;
};

let keySequence = 0;
/** An idempotency identifier, never an authentication secret. No new native dependency. */
export function newSubmissionKey(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
  const random = Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16));
  // Timestamp + process counter also distinguish rapid calls on native runtimes without Web Crypto.
  const stamp = Date.now().toString(16).padStart(12, '0').slice(-12);
  const count = (++keySequence).toString(16).padStart(8, '0').slice(-8);
  for (let i = 0; i < 12; i++) random[i + 20] = stamp[i];
  for (let i = 0; i < 8; i++) random[i] = count[i];
  random[12] = '4'; random[16] = (8 + Math.floor(Math.random() * 4)).toString(16);
  const hex = random.join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const active = (state: GradingState) => state === 'READY' || state === 'PROCESSING';

/** One screen's logical submission. Network recovery never invents a replacement key. */
export function createQuizSubmission(options: Options) {
  const epoch = options.session();
  const questions = options.questions.map(question => ({ ...question }));
  const prefix = `/api/materials/${options.materialId}`;
  const wait = options.wait ?? (milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds)));
  let view: SubmissionView = { state: 'IDLE', retryable: false };
  let key: string | undefined;
  let payload: QuizAnswerPayload | undefined;
  let flight: Promise<SubmissionView> | null = null;
  let disposed = false;
  // Preserve a recovery generation if its HTTP response is lost.
  let pendingRetry: { expectedGeneration: number; confirmUnknown: boolean } | undefined;
  let recoveries = 0;
  const current = () => !disposed && epoch !== null && options.session() === epoch;
  function publish(next: SubmissionView) {
    if (!current()) {
      view = { state: 'SESSION_CHANGED', retryable: false };
    } else view = next;
    if (!disposed) options.changed?.(view);
    return view;
  }
  function assertCurrent() {
    if (!current()) throw new Error('Submission session changed');
  }
  function accept(response: SubmissionResponse): SubmissionView {
    assertCurrent();
    if (response.status === 200 && Array.isArray(response.data)) {
      if (!response.data.every(result => result?.snapshotAvailable === true && Number.isSafeInteger(result.version) &&
          typeof result.questionContent === 'string')) throw new Error('Missing grading snapshot');
      const results = options.mergeResults(questions, response.data);
      if (!response.attemptId || !uuid.test(response.attemptId) || response.state !== 'SUCCEEDED') {
        throw new Error('Invalid grading result metadata');
      }
      if (view.attemptId && view.attemptId !== response.attemptId) throw new Error('Grading attempt changed');
      pendingRetry = undefined;
      return publish({ state: 'SUCCEEDED', attemptId: response.attemptId, retryable: false, results });
    }
    const data = response.data as Record<string, unknown> | null;
    const known = ['READY', 'PROCESSING', 'FAILED', 'UNKNOWN', 'REVOKED'];
    if (data && typeof data === 'object' && typeof data.attemptId === 'string' && uuid.test(data.attemptId)
        && typeof data.state === 'string' && known.includes(data.state)
        && Number.isSafeInteger(data.generation) && Number(data.generation) >= 0) {
      const state = data.state as GradingState;
      if (view.attemptId && view.attemptId !== data.attemptId) throw new Error('Grading attempt changed');
      const expected = active(state) ? 202 : state === 'FAILED' ? 502 : state === 'UNKNOWN' ? 503 : 409;
      if (response.status !== expected) throw new Error('Invalid grading state response');
      pendingRetry = undefined;
      return publish({ state, attemptId: data.attemptId, generation: Number(data.generation),
        retryable: data.retryable === true && recoveries < 2 && ['READY', 'FAILED', 'UNKNOWN'].includes(state) });
    }
    if (response.status === 401) return publish({ state: 'SESSION_CHANGED', retryable: false });
    if (response.status === 403 || response.status === 404) return publish({ state: 'REVOKED', retryable: false });
    if (response.status === 409) {
      const code = typeof data?.code === 'string' ? data.code : typeof data?.error === 'string' ? data.error : '';
      return publish({ state: code === 'QUIZ_VERSION_CONFLICT' || code === 'VERSION_CONFLICT' ? 'VERSION_CONFLICT' : 'CONFLICT', retryable: false });
    }
    if (response.status >= 400 && response.status < 500) return publish({ state: 'REJECTED', retryable: false });
    throw new Error('Grading outcome unavailable');
  }
  async function send(request: Omit<SubmissionRequest, 'key'>) {
    assertCurrent();
    // Also bound a pending authentication refresh. A timeout does not claim that
    // the server/provider stopped; later HTTP completion cannot change this view.
    let timer: ReturnType<typeof setTimeout> | undefined;
    let response: SubmissionResponse;
    try {
      response = await Promise.race([options.request({ ...request, key: key! }),
        new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Grading response timeout')), options.requestTimeoutMs ?? 20000); }),
      ]);
    } finally { if (timer !== undefined) clearTimeout(timer); }
    assertCurrent();
    return accept(response);
  }
  const initialRequest = () => ({ method: 'POST' as const, path: `${prefix}/quizzes/submit`, body: payload });
  const retryRequest = () => ({ method: 'POST' as const,
    path: `${prefix}/quiz-attempts/${view.attemptId}/retry`, body: pendingRetry });
  async function observe() {
    // A finite read-only wait. No automatic provider retry, including after UNKNOWN.
    for (let count = 0; count < 3 && active(view.state) && view.attemptId; count++) {
      await wait(1000); assertCurrent();
      await send({ method: 'GET', path: `${prefix}/quiz-attempts/${view.attemptId}` });
    }
    return view;
  }
  function run(action: () => Promise<SubmissionView>): Promise<SubmissionView> {
    if (flight) return flight;
    if (!current()) return Promise.resolve(publish({ state: 'SESSION_CHANGED', retryable: false }));
    const promise = Promise.resolve().then(action).catch(() => {
      if (!current()) return publish({ state: 'SESSION_CHANGED', retryable: false });
      return publish({ ...view, state: 'UNKNOWN', retryable: false, results: undefined });
    });
    flight = promise;
    void promise.then(() => { if (flight === promise) flight = null; });
    return promise;
  }
  function submit(answers: QuizAnswerPayload): Promise<SubmissionView> {
    if (payload) {
      if (JSON.stringify(payload) !== JSON.stringify(answers)) {
        return Promise.resolve({ state: 'CONFLICT', retryable: false });
      }
      return check();
    }
    if (!current()) return Promise.resolve(publish({ state: 'SESSION_CHANGED', retryable: false }));
    if (questions.length === 0 || questions.length > 50 || answers.answers.length !== questions.length ||
        new Set(questions.map(question => question.id)).size !== questions.length ||
        answers.answers.some((answer, index) => answer.quizId !== questions[index].id || answer.version !== questions[index].version ||
          !Number.isSafeInteger(answer.version) || answer.version < 0 || typeof answer.answer !== 'string' || Array.from(answer.answer).length > 2000)) {
      return Promise.resolve(publish({ state: 'REJECTED', retryable: false }));
    }
    key = (options.makeKey ?? newSubmissionKey)();
    if (!uuid.test(key)) throw new Error('Invalid submission identifier');
    payload = { answers: answers.answers.map(answer => ({ ...answer })) };
    return run(async () => {
      publish({ state: 'PROCESSING', retryable: false });
      await send(initialRequest());
      return observe();
    });
  }
  function check(): Promise<SubmissionView> {
    return run(async () => {
      if (!payload || view.state === 'SUCCEEDED') return view;
      if (pendingRetry) await send(retryRequest());
      else if (view.attemptId) await send({ method: 'GET', path: `${prefix}/quiz-attempts/${view.attemptId}` });
      else await send(initialRequest()); // Same key and frozen request if the first response was lost.
      return observe();
    });
  }
  function retry(confirmUnknown = false): Promise<SubmissionView> {
    return run(async () => {
      if (!view.retryable || !view.attemptId || view.generation === undefined || recoveries >= 2 ||
          (view.state === 'UNKNOWN' && !confirmUnknown)) return view;
      pendingRetry = { expectedGeneration: view.generation, confirmUnknown };
      recoveries++;
      await send(retryRequest());
      return observe();
    });
  }
  return { submit, check, retry, current, getView: () => view, hasSubmission: () => payload !== undefined,
    dispose: () => { disposed = true; } };
}

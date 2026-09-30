export type IndexingSummary = {
  jobId: string | null;
  state: 'NONE' | 'QUEUED' | 'PROCESSING' | 'SUCCEEDED' | 'FAILED' | 'SUPERSEDED' | 'REVOKED';
  sourceRevision: number;
  executionGeneration: number;
  readable: boolean;
  activeCurrent: boolean;
  retryable: boolean;
};
export type IndexingView = {
  summary: IndexingSummary | null;
  error: 'unavailable' | 'denied' | 'session' | null;
  busy: boolean;
  exhausted: boolean;
};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const integer = (value: unknown) => Number.isSafeInteger(value) && Number(value) >= 0;

/** Celery task identifiers/results and absent metadata never imply a usable index. */
export function parseIndexingSummary(value: unknown): IndexingSummary | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  if (!['NONE', 'QUEUED', 'PROCESSING', 'SUCCEEDED', 'FAILED', 'SUPERSEDED', 'REVOKED'].includes(String(data.state)) ||
      !integer(data.sourceRevision) || !integer(data.executionGeneration) ||
      typeof data.readable !== 'boolean' || typeof data.activeCurrent !== 'boolean' || typeof data.retryable !== 'boolean') return null;
  if (data.state === 'NONE' ? data.jobId !== null : typeof data.jobId !== 'string' || !uuid.test(data.jobId)) return null;
  if (data.activeCurrent && !data.readable || data.state === 'NONE' && (data.readable || data.activeCurrent || data.retryable) ||
      data.state === 'REVOKED' && (data.readable || data.activeCurrent || data.retryable)) return null;
  return { jobId: data.jobId as string | null, state: data.state as IndexingSummary['state'],
    sourceRevision: data.sourceRevision as number, executionGeneration: data.executionGeneration as number,
    readable: data.readable, activeCurrent: data.activeCurrent, retryable: data.retryable };
}

export const indexingPending = (summary: IndexingSummary | null) =>
  summary?.state === 'QUEUED' || summary?.state === 'PROCESSING';

export function indexingPresentation(view: Pick<IndexingView, 'summary' | 'error'>) {
  if (view.error === 'denied') return { label: '접근할 수 없음', tone: 'failed', hint: '자료가 없거나 접근 권한이 없습니다.' };
  if (view.error === 'session') return { label: '로그인 확인 필요', tone: 'unknown', hint: '다시 로그인한 뒤 자료를 열어주세요.' };
  if (view.error || !view.summary) return { label: '상태 확인 필요', tone: 'unknown', hint: '색인 준비 상태를 확인하지 못했습니다. 상태 확인을 눌러주세요.' };
  const summary = view.summary;
  if (summary.readable) {
    if (summary.state === 'FAILED') return { label: '사용 가능 · 재색인 실패', tone: 'warning', hint: '현재 원본과 일치하는 이전 색인은 사용할 수 있습니다. 새 색인 생성은 실패했습니다.' };
    if (indexingPending(summary)) return { label: '사용 가능 · 재색인 준비 중', tone: 'ready', hint: '현재 원본의 기존 색인을 사용하며 새 색인을 준비하고 있습니다.' };
    return { label: '사용 가능', tone: 'ready', hint: '현재 원본과 일치하는 검증된 색인을 사용할 수 있습니다.' };
  }
  if (summary.state === 'QUEUED') return { label: '발행 접수', tone: 'pending', hint: '자료는 저장되었습니다. 색인 작업 전달을 기다리고 있습니다.' };
  if (summary.state === 'PROCESSING') return { label: '색인 준비 중', tone: 'pending', hint: '자료는 저장되었습니다. AI 기능은 색인이 준비된 뒤 사용할 수 있습니다.' };
  if (summary.state === 'FAILED') return { label: '색인 실패', tone: 'failed', hint: '자료는 저장되어 있지만 사용할 수 있는 색인이 없습니다.' };
  if (summary.state === 'REVOKED') return { label: '사용할 수 없음', tone: 'failed', hint: '자료 접근 상태가 바뀌어 색인을 사용할 수 없습니다.' };
  if (summary.state === 'NONE') return { label: '색인 준비 필요', tone: 'unknown', hint: '확인된 색인 작업이 없습니다. 발행됨 표시는 색인 완료를 뜻하지 않습니다.' };
  return { label: '상태 확인 필요', tone: 'unknown', hint: '현재 원본에 사용할 수 있는 색인이 확인되지 않았습니다.' };
}

export function indexingErrorMessage(status: number, body: unknown): string | null {
  const data = body as { code?: unknown; detail?: { code?: unknown } } | null;
  const code = data?.detail?.code ?? data?.code;
  if (status === 409 && code === 'INDEX_NOT_READY') return '현재 자료의 색인이 아직 준비되지 않았습니다. 자료 목록에서 준비 상태를 확인해주세요.';
  if (status === 503 && code === 'INDEX_STORAGE_UNAVAILABLE') return '색인 저장소에 연결할 수 없습니다. 잠시 뒤 다시 확인해주세요.';
  return null;
}

type Request = { method: 'GET' | 'POST'; path: string; body?: unknown; signal: AbortSignal };
type Response = { status: number; data: unknown };
type Options = {
  resourcePath: string;
  initial?: unknown;
  getEpoch: () => number;
  request: (request: Request) => Promise<Response>;
  changed: (view: IndexingView) => void;
  wait?: (milliseconds: number, signal: AbortSignal) => Promise<void>;
  requestTimeoutMs?: number;
  maxPolls?: number;
};

/** One resource in one login epoch; only GETs are automatic and polling is finite. */
export function createIndexingController(options: Options) {
  if (!/^\/api\/(documents|pdf)\/[1-9][0-9]*\/indexing$/.test(options.resourcePath)) throw new Error('Invalid indexing resource');
  const epoch = options.getEpoch();
  let view: IndexingView = { summary: parseIndexingSummary(options.initial), error: null, busy: false, exhausted: false };
  let disposed = false;
  let flight: Promise<IndexingView> | null = null;
  const lifetime = new AbortController();
  const current = () => !disposed && options.getEpoch() === epoch;
  const wait = options.wait ?? ((milliseconds, signal) => new Promise<void>((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new Error('Stopped')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, milliseconds);
    if (signal.aborted) abort(); else signal.addEventListener('abort', abort, { once: true });
  }));
  function publish(next: IndexingView) {
    if (!current()) next = { summary: null, error: 'session', busy: false, exhausted: false };
    view = next;
    if (!disposed) options.changed(view);
    return view;
  }
  async function send(method: 'GET' | 'POST', path: string, body?: unknown) {
    if (!current()) return publish({ ...view, error: 'session' });
    const controller = new AbortController();
    const stop = () => controller.abort();
    lifetime.signal.addEventListener('abort', stop, { once: true });
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const response = await Promise.race([options.request({ method, path, body, signal: controller.signal }),
        new Promise<never>((_, reject) => { timer = setTimeout(() => { controller.abort(); reject(new Error('Index status timeout')); }, options.requestTimeoutMs ?? 8000); }),
      ]);
      if (!current()) return publish({ ...view, error: 'session' });
      if (response.status === 403 || response.status === 404) return publish({ ...view, summary: null, error: 'denied' });
      if (response.status !== 200) return publish({ ...view, error: 'unavailable' });
      const summary = parseIndexingSummary(response.data);
      if (!summary || view.summary && summary.sourceRevision < view.summary.sourceRevision) return publish({ ...view, error: 'unavailable' });
      return publish({ ...view, summary, error: null });
    } catch {
      return publish({ ...view, error: current() ? 'unavailable' : 'session' });
    } finally {
      if (timer !== undefined) clearTimeout(timer);
      lifetime.signal.removeEventListener('abort', stop);
    }
  }
  function run(retry: boolean): Promise<IndexingView> {
    if (flight) return flight;
    if (!current()) return Promise.resolve(publish({ ...view, error: 'session' }));
    // Preserve the exact generation for this explicit retry, including an auth replay.
    const retryJob = retry && !view.error && view.summary?.retryable && view.summary.jobId ?
      { jobId: view.summary.jobId, generation: view.summary.executionGeneration } : null;
    if (retry && !retryJob) return Promise.resolve(view);
    publish({ ...view, busy: true, exhausted: false });
    const promise = Promise.resolve().then(async () => {
      if (retryJob) await send('POST', `/api/indexing/jobs/${retryJob.jobId}/retry`, { expectedGeneration: retryJob.generation });
      else await send('GET', options.resourcePath);
      for (let count = 0; count < (options.maxPolls ?? 10) && current() && !view.error && indexingPending(view.summary); count++) {
        await wait(2000, lifetime.signal);
        if (!current()) break;
        await send('GET', options.resourcePath);
      }
      return publish({ ...view, busy: false, exhausted: !view.error && indexingPending(view.summary) });
    }).catch(() => publish({ ...view, busy: false, error: current() ? 'unavailable' : 'session' }));
    flight = promise;
    void promise.then(() => { if (flight === promise) flight = null; });
    return promise;
  }
  return { refresh: () => run(false), retry: () => run(true), getView: () => view,
    dispose: () => { disposed = true; lifetime.abort(); } };
}

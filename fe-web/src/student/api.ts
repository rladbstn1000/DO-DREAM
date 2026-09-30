import { authenticatedFetch, authSession } from '../auth/client';
export const apiBase = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '');
export const ragBase = (import.meta.env.VITE_RAG_BASE || '/ai').replace(/\/+$/, '');
export class StudentApiError extends Error {
  status: number; code: string;
  constructor(status: number, body?: unknown) {
    const d = body as { code?: string; detail?: { code?: string } } | undefined;
    super(status === 403 || status === 404 ? '자료가 없거나 현재 공유 권한이 없습니다.' : '요청을 완료하지 못했습니다.');
    this.status = status; this.code = d?.detail?.code ?? d?.code ?? '';
  }
}
export async function studentRequest(path: string, init: RequestInit = {}, timeout = 20000) {
  const controller = new AbortController();
  const epoch = authSession.getEpoch();
  const stop = () => controller.abort();
  init.signal?.addEventListener('abort', stop, { once: true });
  if (init.signal?.aborted) controller.abort();
  let timer: ReturnType<typeof setTimeout>;
  try {
    return await Promise.race([(async () => {
      const response = await authenticatedFetch(path.startsWith('/rag/') ? `${ragBase}${path}` : `${apiBase}${path}`,
        { ...init, signal: controller.signal, headers: { 'Content-Type': 'application/json', ...init.headers } });
      const data = response.status === 204 ? null : await response.json().catch(() => null);
      if (controller.signal.aborted || epoch !== authSession.getEpoch()) throw new Error('로그인 상태가 변경되었습니다.');
      return { status: response.status, data, attemptId: response.headers.get('X-Grading-Attempt-Id') ?? undefined,
        state: response.headers.get('X-Grading-State') ?? undefined };
    })(),
    new Promise<never>((_, reject) => { timer = setTimeout(() => { controller.abort(); reject(new Error('응답을 기다리는 시간이 끝났습니다.')); }, timeout); })]);
  } finally { clearTimeout(timer!); init.signal?.removeEventListener('abort', stop); }
}
export async function studentJson(path: string, init?: RequestInit, timeout?: number) {
  const response = await studentRequest(path, init, timeout);
  if (response.status < 200 || response.status >= 300) throw new StudentApiError(response.status, response.data);
  return response.data;
}
export const denied = (error: unknown) => error instanceof StudentApiError && (error.status === 403 || error.status === 404);

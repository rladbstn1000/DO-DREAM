import test from 'node:test';
import assert from 'node:assert/strict';
import { createIndexingController, indexingErrorMessage, indexingPresentation, parseIndexingSummary } from '../src/indexing/status.ts';
import { createAuthSession } from '../src/auth/session.ts';

const id = '11111111-1111-4111-8111-111111111111';
const summary = (state = 'QUEUED', extra: Record<string, unknown> = {}) => ({ jobId: id, state,
  sourceRevision: 1, executionGeneration: state === 'QUEUED' ? 0 : 1, readable: false, activeCurrent: false,
  retryable: state === 'FAILED', ...extra });
const ready = () => summary('SUCCEEDED', { readable: true, activeCurrent: true });
const present = (value: unknown) => indexingPresentation({ summary: parseIndexingSummary(value), error: null });
const deferred = <T>() => { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; };
function setup(responses: Array<{ status: number; data: unknown }> = [], extra: Record<string, unknown> = {}) {
  const requests: any[] = []; const views: any[] = []; const waits: number[] = [];
  let epoch = 0;
  const client = createIndexingController({ resourcePath: '/api/documents/23/indexing', getEpoch: () => epoch,
    request: async request => { requests.push(request); const response = responses.shift(); if (!response) throw new Error('Unexpected request'); return response; },
    changed: view => views.push(view), wait: async ms => { waits.push(ms); }, ...extra });
  return { client, requests, views, waits, changeAccount: () => { epoch++; } };
}

test('index status requires durable summary rather than a Celery task ID or SUCCESS', () => {
  for (const value of [null, {}, { task_id: id }, { task_id: id, status: 'SUCCESS' }, summary('SUCCESS')]) {
    assert.equal(parseIndexingSummary(value), null); assert.equal(present(value).label, '상태 확인 필요');
  }
});
test('malformed identity, revision and boolean metadata never imply availability', () => {
  for (const extra of [{ jobId: '../other' }, { jobId: null }, { sourceRevision: -1 }, { sourceRevision: 1.5 },
    { sourceRevision: Number.MAX_SAFE_INTEGER + 1 }, { executionGeneration: '1' }, { readable: 'true' },
    { activeCurrent: true, readable: false }, { state: 'NONE', jobId: null, readable: true }]) {
    assert.equal(parseIndexingSummary(summary('FAILED', extra)), null);
  }
});
test('accepted, processing, available and first-index failure are distinct', () => {
  assert.equal(present(summary()).label, '발행 접수');
  assert.equal(present(summary('PROCESSING')).label, '색인 준비 중');
  assert.equal(present(ready()).label, '사용 가능');
  assert.equal(present(summary('FAILED')).label, '색인 실패');
  assert.equal(present(summary('NONE', { jobId: null, sourceRevision: 0, executionGeneration: 0 })).label, '색인 준비 필요');
});
test('same-source reindex failure preserves availability but exposes failure separately', () => {
  const state = summary('FAILED', { readable: true, activeCurrent: false });
  assert.equal(present(state).label, '사용 가능 · 재색인 실패');
  assert.equal(present(summary('PROCESSING', { readable: true })).label, '사용 가능 · 재색인 준비 중');
  assert.equal(present(summary('SUCCEEDED')).label, '상태 확인 필요');
});
test('storage and version errors use fixed messages and never echo private detail', () => {
  const message = indexingErrorMessage(409, { detail: { code: 'INDEX_NOT_READY', collection: 'private-collection' } });
  assert.ok(message?.includes('준비되지')); assert.ok(!message.includes('private-collection'));
  assert.ok(indexingErrorMessage(503, { detail: { code: 'INDEX_STORAGE_UNAVAILABLE' } })?.includes('저장소'));
  assert.equal(indexingErrorMessage(404, { detail: { code: 'INDEX_NOT_READY' } }), null);
});
test('polling reads a resource until a verified active index is available', async () => {
  const state = setup([summary(), summary('PROCESSING'), ready()].map(data => ({ status: 200, data })));
  const view = await state.client.refresh();
  assert.equal(view.summary?.activeCurrent, true); assert.equal(view.busy, false);
  assert.equal(state.requests.length, 3); assert.ok(state.requests.every(request => request.method === 'GET'));
  assert.deepEqual(state.waits, [2000, 2000]);
});
test('poll budget is finite and does not turn a pending job into failure or success', async () => {
  const state = setup(Array.from({ length: 4 }, () => ({ status: 200, data: summary('PROCESSING') })), { maxPolls: 3 });
  const view = await state.client.refresh();
  assert.equal(state.requests.length, 4); assert.equal(view.exhausted, true);
  assert.equal(view.error, null); assert.equal(view.summary?.state, 'PROCESSING');
});
test('duplicate status actions join one request flight', async () => {
  const response = deferred<{ status: number; data: unknown }>(); let calls = 0;
  const state = setup([], { request: async () => { calls++; return response.promise; } });
  const first = state.client.refresh(); const second = state.client.refresh();
  assert.equal(first, second); await Promise.resolve(); response.resolve({ status: 200, data: ready() });
  await first; assert.equal(calls, 1);
});
test('manual retry freezes job identity and execution generation without an automatic second POST', async () => {
  const response = deferred<{ status: number; data: unknown }>(); const requests: any[] = [];
  const state = setup([], { initial: summary('FAILED', { executionGeneration: 2 }), request: async request => { requests.push(request); return response.promise; } });
  const first = state.client.retry(); const second = state.client.retry(); assert.equal(first, second);
  await Promise.resolve(); response.resolve({ status: 200, data: summary('FAILED', { executionGeneration: 3, retryable: false }) });
  await first; await state.client.retry();
  assert.equal(requests.length, 1); assert.equal(requests[0].path, `/api/indexing/jobs/${id}/retry`);
  assert.deepEqual(requests[0].body, { expectedGeneration: 2 });
});
test('lost retry response requires read-only status confirmation before another retry', async () => {
  const requests: any[] = []; let fail = true;
  const state = setup([], { initial: summary('FAILED'), request: async request => {
    requests.push(request); if (fail) { fail = false; throw new Error('Response lost'); }
    return { status: 200, data: ready() };
  } });
  assert.equal((await state.client.retry()).error, 'unavailable');
  await state.client.retry(); assert.equal(requests.length, 1);
  await state.client.refresh(); assert.deepEqual(requests.map(request => request.method), ['POST', 'GET']);
});
for (const status of [403, 404, 409, 503]) test(`index status HTTP ${status} stops polling without changing the login epoch`, async () => {
  const state = setup([{ status, data: { collection: 'private' } }], { initial: ready() });
  const view = await state.client.refresh();
  assert.equal(view.error, status === 403 || status === 404 ? 'denied' : 'unavailable');
  assert.notEqual(indexingPresentation(view).label, '사용 가능'); assert.equal(state.requests.length, 1);
});
test('older source revisions cannot replace newer status', async () => {
  const state = setup([{ status: 200, data: ready() }], { initial: summary('PROCESSING', { sourceRevision: 2 }) });
  const view = await state.client.refresh(); assert.equal(view.summary?.sourceRevision, 2);
  assert.equal(view.error, 'unavailable'); assert.notEqual(indexingPresentation(view).label, '사용 가능');
});
test('logout or an account switch fences late completion and later recovery actions', async () => {
  const response = deferred<{ status: number; data: unknown }>(); let calls = 0;
  const state = setup([], { request: async () => { calls++; return response.promise; } });
  const pending = state.client.refresh(); await Promise.resolve(); state.changeAccount();
  response.resolve({ status: 200, data: ready() });
  assert.equal((await pending).error, 'session'); await state.client.refresh(); await state.client.retry();
  assert.equal(calls, 1); assert.equal(state.client.getView().summary, null);
});
test('component disposal aborts its request and ignores its late success', async () => {
  const response = deferred<{ status: number; data: unknown }>(); let signal: AbortSignal | undefined;
  const state = setup([], { request: async request => { signal = request.signal; return response.promise; } });
  const pending = state.client.refresh(); await Promise.resolve(); const count = state.views.length;
  state.client.dispose(); assert.equal(signal?.aborted, true); response.resolve({ status: 200, data: ready() }); await pending;
  assert.equal(state.views.length, count);
});
test('a stalled response has a deadline and cannot publish a late available state', async () => {
  const response = deferred<{ status: number; data: unknown }>();
  const state = setup([], { requestTimeoutMs: 5, request: async () => response.promise });
  assert.equal((await state.client.refresh()).error, 'unavailable'); const count = state.views.length;
  response.resolve({ status: 200, data: ready() }); await Promise.resolve(); await Promise.resolve();
  assert.equal(state.views.length, count); assert.equal(state.client.getView().summary, null);
});
test('invalid resource paths cannot send a request', () => {
  for (const resourcePath of ['/api/documents/../auth/indexing', 'https://other.invalid/api/documents/1/indexing', '/api/pdf/01/indexing']) {
    assert.throws(() => setup([], { resourcePath }));
  }
});
test('auth refresh preserves the manual retry generation while index errors preserve the session', async () => {
  const storage = new Map([['accessToken', 'old'], ['isLoggedIn', 'true']]); const requests: Request[] = [];
  const auth = createAuthSession({ origin: 'http://127.0.0.1:15173', storage: {
    getItem: key => storage.get(key) ?? null, setItem: (key, value) => { storage.set(key, value); }, removeItem: key => { storage.delete(key); } },
    fetch: (async request => {
      requests.push(request as Request); const path = new URL((request as Request).url).pathname;
      if (path.endsWith('/csrf')) return Response.json({ token: 'synthetic-csrf', headerName: 'X-XSRF-TOKEN' });
      if (path.endsWith('/refresh')) return Response.json({ accessToken: 'renewed' });
      if ((request as Request).headers.get('Authorization') === 'Bearer old') return new Response('{}', { status: 401 });
      return new Response('{}', { status: 403 });
    }) as typeof fetch });
  const state = setup([], { initial: summary('FAILED'), getEpoch: auth.getEpoch, request: async request => {
    const response = await auth.authenticatedFetch(request.path, { method: request.method, signal: request.signal,
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request.body) });
    return { status: response.status, data: await response.json() };
  } });
  assert.equal((await state.client.retry()).error, 'denied'); assert.equal(auth.getToken(), 'renewed');
  const attempts = requests.filter(request => request.url.endsWith('/retry'));
  assert.equal(attempts.length, 2);
  assert.deepEqual(await attempts[0].clone().json(), { expectedGeneration: 1 });
  assert.deepEqual(await attempts[1].clone().json(), { expectedGeneration: 1 });
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { createAuthSession } from '../src/auth/session.ts';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
const deferred = () => { let resolve!: (value?: any) => void; const promise = new Promise<any>(r => { resolve = r; }); return { promise, resolve }; };
function setup(handler: (request: Request) => Promise<Response> | Response, initial = 'old-at', bases: { apiBase?: string; ragBase?: string } = {}) {
  const values = new Map<string, string>(initial ? [['accessToken', initial], ['isLoggedIn', 'true']] : []);
  const calls: Request[] = [];
  const changes: Array<{ authenticated: boolean; reason?: string }> = [];
  const client = createAuthSession({
    origin: 'http://127.0.0.1:15174',
    ...bases,
    storage: { getItem: k => values.get(k) ?? null, setItem: (k, v) => { values.set(k, v); }, removeItem: k => { values.delete(k); } },
    fetch: (async (request: Request) => {
      calls.push(request.clone());
      if (new URL(request.url).pathname === '/api/auth/csrf') return json({ token: 'synthetic-csrf', headerName: 'X-XSRF-TOKEN' });
      return handler(request);
    }) as typeof fetch,
    onChange: (authenticated, reason) => changes.push({ authenticated, reason }),
  });
  return { client, values, calls, changes, refreshCount: () => calls.filter(r => r.url.endsWith('/refresh')).length };
}
const tick = () => new Promise(r => setImmediate(r));

test('cookie login bootstraps CSRF, never sends an access token, and accepts only AT body', async () => {
  const state = setup(request => {
    assert.equal(request.headers.get('X-XSRF-TOKEN'), 'synthetic-csrf');
    assert.equal(request.headers.get('Authorization'), null);
    assert.equal(request.credentials, 'include');
    return json({ accessToken: 'new-at' });
  }, '');
  await state.client.login('synthetic@example.invalid', 'synthetic-password');
  assert.equal(state.client.getToken(), 'new-at');
  assert.equal(state.values.get('isLoggedIn'), 'true');
  assert.equal(state.calls.length, 2);
});

test('12 concurrent expired requests share exactly one refresh', async () => {
  const gate = deferred();
  const state = setup(async request => {
    if (request.url.endsWith('/refresh')) { await gate.promise; return json({ accessToken: 'new-at' }); }
    return json({}, request.headers.get('Authorization') === 'Bearer new-at' ? 200 : 401);
  });
  const pending = Array.from({ length: 12 }, () => state.client.authenticatedFetch('/api/teacher/me'));
  await tick(); gate.resolve();
  assert.deepEqual((await Promise.all(pending)).map(r => r.status), Array(12).fill(200));
  assert.equal(state.refreshCount(), 1);
});

test('a late old-token 401 reuses the newer AT without another refresh', async () => {
  const late = deferred();
  const state = setup(async request => {
    if (request.url.endsWith('/refresh')) return json({ accessToken: 'new-at' });
    if (request.headers.get('Authorization') === 'Bearer new-at') return json({});
    if (request.url.includes('/slow')) await late.promise;
    return json({}, 401);
  });
  const slow = state.client.authenticatedFetch('/api/slow');
  assert.equal((await state.client.authenticatedFetch('/api/fast')).status, 200);
  late.resolve();
  assert.equal((await slow).status, 200);
  assert.equal(state.refreshCount(), 1);
});

test('POST body is preserved across one replay', async () => {
  const bodies: string[] = [];
  const state = setup(async request => {
    if (request.url.endsWith('/refresh')) return json({ accessToken: 'new-at' });
    bodies.push(await request.text());
    return json({}, bodies.length === 1 ? 401 : 200);
  });
  assert.equal((await state.client.authenticatedFetch('/api/example', { method: 'POST', body: '{"sample":1}' })).status, 200);
  assert.deepEqual(bodies, ['{"sample":1}', '{"sample":1}']);
});

test('retry is bounded when renewed token is also rejected', async () => {
  let protectedCalls = 0;
  const state = setup(request => request.url.endsWith('/refresh') ? json({ accessToken: 'new-at' }) : (protectedCalls++, json({}, 401)));
  await assert.rejects(state.client.authenticatedFetch('/api/teacher/me'));
  assert.equal(protectedCalls, 2);
  assert.equal(state.refreshCount(), 1);
  assert.equal(state.client.getToken(), null);
});

test('a late retry 401 cannot clear an AT refreshed by another request', async () => {
  const replayStarted = deferred(); const releaseReplay = deferred();
  let refreshes = 0;
  const state = setup(async request => {
    if (request.url.endsWith('/refresh')) return json({ accessToken: ++refreshes === 1 ? 'at-two' : 'at-three' });
    if (request.url.endsWith('/first') && request.headers.get('Authorization') === 'Bearer at-two') {
      replayStarted.resolve(); await releaseReplay.promise; return json({}, 401);
    }
    return json({}, request.headers.get('Authorization') === 'Bearer at-three' ? 200 : 401);
  });
  const first = assert.rejects(state.client.authenticatedFetch('/api/first'));
  await replayStarted.promise;
  assert.equal((await state.client.authenticatedFetch('/api/second')).status, 200);
  releaseReplay.resolve(); await first;
  assert.equal(state.client.getToken(), 'at-three');
  assert.equal(state.refreshCount(), 2);
  assert.equal(state.changes.length, 0);
});

test('403 is returned without refreshing or clearing the session', async () => {
  const state = setup(() => json({}, 403));
  assert.equal((await state.client.authenticatedFetch('/api/teacher/me')).status, 403);
  assert.equal(state.refreshCount(), 0);
  assert.equal(state.client.getToken(), 'old-at');
});

test('auth endpoints and foreign origins cannot enter the retry wrapper', async () => {
  const state = setup(() => json({}));
  for (const url of ['/api/auth/teacher/login', '/api/auth/teacher/refresh', '/api/auth/teacher/logout', 'https://example.invalid/api/private']) {
    await assert.rejects(state.client.authenticatedFetch(url));
  }
  assert.equal(state.calls.length, 0);
});

test('configured root AI origin permits only its RAG routes', async () => {
  const state = setup(request => {
    assert.equal(request.headers.get('Authorization'), 'Bearer old-at');
    return json({});
  }, 'old-at', { ragBase: 'https://ai.example.invalid' });
  assert.equal((await state.client.authenticatedFetch('https://ai.example.invalid/rag/chat')).status, 200);
  await assert.rejects(state.client.authenticatedFetch('https://ai.example.invalid/unrelated'));
  await assert.rejects(state.client.authenticatedFetch('https://other.example.invalid/rag/chat'));
  assert.equal(state.calls.length, 1);
});

test('configured API and AI base path prefixes are preserved and bounded', async () => {
  const state = setup(() => json({}), 'old-at', { apiBase: 'https://api.example.invalid/backend', ragBase: 'https://ai.example.invalid/assistant' });
  assert.equal((await state.client.authenticatedFetch('https://api.example.invalid/backend/api/teacher/me')).status, 200);
  assert.equal((await state.client.authenticatedFetch('https://ai.example.invalid/assistant/rag/chat')).status, 200);
  for (const url of ['https://api.example.invalid/api/teacher/me', 'https://api.example.invalid/backend/api/auth/teacher/login', 'https://ai.example.invalid/assistant-extra/rag/chat']) {
    await assert.rejects(state.client.authenticatedFetch(url));
  }
  assert.equal(state.calls.length, 2);
});

test('refresh failure rejects all waiting requests and aborts unrelated in-flight requests', async () => {
  const entered = deferred();
  let aborted = false;
  const state = setup(async request => {
    if (request.url.includes('/slow')) return new Promise((_, reject) => {
      request.signal.addEventListener('abort', () => { aborted = true; reject(new Error('aborted')); });
      entered.resolve();
    });
    if (request.url.endsWith('/refresh')) return json({}, 503);
    return json({}, 401);
  });
  const slow = state.client.authenticatedFetch('/api/slow');
  const slowRejected = assert.rejects(slow);
  await entered.promise;
  await Promise.all(Array.from({ length: 6 }, () => assert.rejects(state.client.authenticatedFetch('/api/teacher/me'))));
  await slowRejected;
  assert.equal(aborted, true);
  assert.equal(state.refreshCount(), 1);
  assert.equal(state.client.getToken(), null);
  assert.equal(state.changes.filter(c => c.reason === 'expired').length, 1);
});

test('logout invalidates a refresh response even when the transport ignores abort', async () => {
  const arrived = deferred(); const release = deferred();
  const state = setup(async request => {
    if (request.url.endsWith('/refresh')) { arrived.resolve(); await release.promise; return json({ accessToken: 'late-at' }); }
    if (request.url.endsWith('/logout')) return json({});
    return json({}, 401);
  });
  const oldRequest = state.client.authenticatedFetch('/api/teacher/me');
  const rejected = assert.rejects(oldRequest);
  await arrived.promise;
  await state.client.logout();
  release.resolve(); await rejected;
  assert.equal(state.client.getToken(), null);
  assert.equal(state.values.get('isLoggedIn'), undefined);
  assert.equal(state.changes.some(c => c.authenticated), false);
});

test('a late old response cannot clear or overwrite a new login', async () => {
  const arrived = deferred(); const release = deferred();
  const state = setup(async request => {
    if (request.url.endsWith('/login')) return json({ accessToken: 'fresh-login-at' });
    arrived.resolve(); await release.promise; return json({}, 401);
  });
  const old = state.client.authenticatedFetch('/api/slow');
  const rejected = assert.rejects(old);
  await arrived.promise;
  await state.client.login('synthetic@example.invalid', 'synthetic-password');
  release.resolve(); await rejected;
  assert.equal(state.client.getToken(), 'fresh-login-at');
  assert.equal(state.refreshCount(), 0);
});

test('logout Redis failure leaves local state cleared and reports server revocation failure', async () => {
  const state = setup(() => json({}, 503));
  await assert.rejects(state.client.logout(), error => (error as any).status === 503);
  assert.equal(state.client.getToken(), null);
});

test('login failure is not retried and never marks the session authenticated', async () => {
  const state = setup(() => json({}, 401), '');
  await assert.rejects(state.client.login('synthetic@example.invalid', 'wrong'));
  assert.equal(state.refreshCount(), 0);
  assert.equal(state.client.getToken(), null);
  assert.equal(state.changes.some(c => c.authenticated), false);
});

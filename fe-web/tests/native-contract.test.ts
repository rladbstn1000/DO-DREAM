import test from 'node:test';
import assert from 'node:assert/strict';
import { createNativeTokenSession, safeRequestError } from '../../fe_app/src/api/nativeTokenSession.ts';

function setup(post: (path: string, body: any, signal: AbortSignal) => Promise<any>) {
  let accessToken: string | null = 'old-at'; let refreshToken: string | null = 'old-rt';
  const calls: Array<{ path: string; body: any }> = [];
  const session = createNativeTokenSession({
    getAccessToken: () => accessToken, getRefreshToken: () => refreshToken,
    saveTokens: tokens => { accessToken = tokens.accessToken; refreshToken = tokens.refreshToken; },
    clearTokens: () => { accessToken = null; refreshToken = null; },
    post: (path, body, signal) => { calls.push({ path, body }); return post(path, body, signal); },
  });
  return { session, calls, tokens: () => ({ accessToken, refreshToken }) };
}
const deferred = () => { let resolve!: (value?: any) => void; const promise = new Promise<any>(r => { resolve = r; }); return { promise, resolve }; };

test('native login uses explicit route and stores both returned tokens', async () => {
  const state = setup(async () => ({ accessToken: 'new-at', refreshToken: 'new-rt' }));
  await state.session.login({ deviceId: 'synthetic-device', deviceSecret: 'synthetic-secret' });
  assert.equal(state.calls[0].path, '/api/auth/student/native/login');
  assert.deepEqual(state.calls[0].body, { deviceId: 'synthetic-device', deviceSecret: 'synthetic-secret' });
  assert.deepEqual(state.tokens(), { accessToken: 'new-at', refreshToken: 'new-rt' });
});

test('native concurrent expiration rotates the body RT once; no device relogin', async () => {
  const gate = deferred();
  const state = setup(async () => { await gate.promise; return { accessToken: 'new-at', refreshToken: 'new-rt' }; });
  const pending = Array.from({ length: 12 }, () => state.session.refreshFor(0, 'old-at'));
  gate.resolve();
  assert.deepEqual(await Promise.all(pending), Array(12).fill('new-at'));
  assert.equal(state.calls.length, 1);
  assert.equal(state.calls[0].path, '/api/auth/student/native/refresh');
  assert.deepEqual(state.calls[0].body, { refreshToken: 'old-rt' });
});

test('native late old-token response reuses the latest AT', async () => {
  const state = setup(async () => ({ accessToken: 'new-at', refreshToken: 'new-rt' }));
  await state.session.refreshFor(0, 'old-at');
  assert.equal(await state.session.refreshFor(0, 'old-at'), 'new-at');
  assert.equal(state.calls.length, 1);
});

test('native old sessions without a RT require login instead of device fallback', async () => {
  const state = setup(async () => { throw new Error('must not send'); });
  state.session.invalidate();
  await assert.rejects(state.session.refresh());
  assert.equal(state.calls.length, 0);
});

test('native refresh failure clears both tokens and rejects all waiting calls', async () => {
  const gate = deferred();
  const state = setup(async () => { await gate.promise; throw new Error('redis unavailable'); });
  const pending = Array.from({ length: 5 }, () => assert.rejects(state.session.refreshFor(0, 'old-at')));
  gate.resolve(); await Promise.all(pending);
  assert.deepEqual(state.tokens(), { accessToken: null, refreshToken: null });
  assert.equal(state.calls.length, 1);
});

test('native logout sends captured RT, invalidates immediately, and rejects a late refresh', async () => {
  const gate = deferred(); const arrived = deferred();
  const state = setup(async path => {
    if (path.endsWith('/refresh')) { arrived.resolve(); await gate.promise; return { accessToken: 'late-at', refreshToken: 'late-rt' }; }
  });
  const pending = assert.rejects(state.session.refresh());
  await arrived.promise;
  await state.session.logout();
  gate.resolve(); await pending;
  assert.equal(state.calls[1].path, '/api/auth/student/native/logout');
  assert.deepEqual(state.calls[1].body, { refreshToken: 'old-rt' });
  assert.deepEqual(state.tokens(), { accessToken: null, refreshToken: null });
});

test('native logout failure is reported with local tokens cleared', async () => {
  const state = setup(async () => { throw new Error('redis unavailable'); });
  await assert.rejects(state.session.logout());
  assert.deepEqual(state.tokens(), { accessToken: null, refreshToken: null });
});

test('native token response missing RT is rejected and never stored', async () => {
  const state = setup(async () => ({ accessToken: 'only-at' }));
  await assert.rejects(state.session.login({ deviceId: 'synthetic', deviceSecret: 'synthetic' }));
  assert.deepEqual(state.tokens(), { accessToken: null, refreshToken: null });
});

test('native transport errors keep status but never expose token, cookie or device request data', async () => {
  const state = setup(async () => {
    throw Object.assign(new Error('request failed with synthetic-private-marker'), {
      response: { status: 503, data: { token: 'synthetic-private-marker' } },
      config: { data: '{"refreshToken":"synthetic-private-marker"}', headers: { Authorization: 'Bearer synthetic-private-marker', Cookie: 'refresh=synthetic-private-marker' } },
    });
  });
  await assert.rejects(state.session.refresh(), error => {
    assert.equal((error as any).response.status, 503);
    assert.equal((error as any).config, undefined);
    assert.equal(JSON.stringify(error).includes('synthetic-private-marker'), false);
    assert.equal(String(error).includes('synthetic-private-marker'), false);
    return true;
  });
});

test('sanitized native 401 preserves the existing Axios login-guidance contract', () => {
  const error = safeRequestError({ response: { status: 401 }, config: { headers: { Authorization: 'private' } } });
  assert.equal(error.isAxiosError && error.response?.status === 401, true);
  assert.equal((error as any).config, undefined);
});

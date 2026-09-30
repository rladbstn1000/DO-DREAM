import test from 'node:test';
import assert from 'node:assert/strict';
import { createQuizSubmission, newSubmissionKey } from '../../fe_app/src/api/quizSubmission.ts';
import { mergeSubmittedQuizResults } from '../../fe_app/src/api/submittedQuizResults.ts';
import type { SubmissionRequest, SubmissionResponse } from '../../fe_app/src/api/quizSubmission.ts';
import { createNativeTokenSession } from '../../fe_app/src/api/nativeTokenSession.ts';
import { createAuthSession } from '../src/auth/session.ts';

const key = 'bf7737e0-1c6f-4fb7-8139-b4d35efcfa2f';
const attempt = '92d1140c-88eb-4b2e-8bc0-0ee77b33e06b';
const questions = [{ id: 23, version: 0, question_type: 'SHORT_ANSWER' as const,
  question_number: 1, title: '합성 문제', content: '최초 문제 내용', chapter_reference: '합성 단원' }];
const answers = { answers: [{ quizId: 23, version: 0, answer: '  합성 답안  ' }] };
const results = [{ question_id: 23, student_answer: '  합성 답안  ', is_correct: true,
  ai_feedback: '제출 후 피드백', correct_answer: '접수 당시 서버 정답',
  version: 0, snapshotAvailable: true, questionContent: '최초 문제 내용' }];
const success = (): SubmissionResponse => ({ status: 200, data: results, attemptId: attempt, state: 'SUCCEEDED' });
const state = (name: string, generation = 1, retryable = false): SubmissionResponse => ({
  status: name === 'FAILED' ? 502 : name === 'UNKNOWN' ? 503 : name === 'REVOKED' ? 409 : 202,
  data: { attemptId: attempt, state: name, generation, retryable },
});
function fixture(request: (request: SubmissionRequest) => Promise<SubmissionResponse>) {
  let epoch: number | null = 1;
  let keys = 0;
  const client = createQuizSubmission({ materialId: 7, questions, session: () => epoch, mergeResults: mergeSubmittedQuizResults,
    makeKey: () => { keys++; return key; }, wait: async () => {}, request });
  return { client, keys: () => keys, switchAccount: () => { epoch = 2; }, logout: () => { epoch = null; } };
}

test('logical submission allocates one key synchronously for double click and freezes whitespace/version', async () => {
  const calls: SubmissionRequest[] = [];
  let complete!: (value: SubmissionResponse) => void;
  const { client, keys } = fixture(async request => { calls.push(request); return new Promise(resolve => { complete = resolve; }); });
  const input = structuredClone(answers);
  const first = client.submit(input);
  const second = client.submit(input);
  assert.equal(first, second);
  input.answers[0].answer = '나중에 바뀐 UI 답안';
  await Promise.resolve();
  assert.equal(calls.length, 1); assert.equal(keys(), 1);
  assert.equal(calls[0].key, key); assert.deepEqual(calls[0].body, answers);
  complete(success());
  assert.equal((await first).state, 'SUCCEEDED');
});

test('lost initial response replays the exact key and frozen body without creating another submission', async () => {
  const calls: SubmissionRequest[] = [];
  const { client, keys } = fixture(async request => { calls.push(request); if (calls.length === 1) throw new Error('network'); return success(); });
  assert.equal((await client.submit(answers)).state, 'UNKNOWN');
  assert.equal(calls.length, 1);
  assert.equal((await client.check()).state, 'SUCCEEDED');
  assert.deepEqual(calls[0], calls[1]); assert.equal(keys(), 1);
});

test('client deadline bounds a hanging request or refresh and ignores its late result', async () => {
  const calls: SubmissionRequest[] = [];
  let complete!: (value: SubmissionResponse) => void;
  const client = createQuizSubmission({ materialId: 7, questions, session: () => 1, makeKey: () => key,
    mergeResults: mergeSubmittedQuizResults, requestTimeoutMs: 5,
    request: async request => {
      calls.push(request);
      return calls.length === 1 ? new Promise(resolve => { complete = resolve; }) : success();
    } });
  assert.equal((await client.submit(answers)).state, 'UNKNOWN');
  complete(success()); await Promise.resolve(); await Promise.resolve();
  assert.equal(client.getView().state, 'UNKNOWN');
  assert.equal((await client.check()).state, 'SUCCEEDED');
  assert.deepEqual(calls[0], calls[1]);
});

test('processing performs at most three read-only polls and then leaves explicit processing guidance', async () => {
  const calls: SubmissionRequest[] = [];
  const { client } = fixture(async request => { calls.push(request); return state('PROCESSING'); });
  assert.equal((await client.submit(answers)).state, 'PROCESSING');
  assert.deepEqual(calls.map(row => row.method), ['POST', 'GET', 'GET', 'GET']);
  assert.equal(calls.filter(row => row.path.endsWith('/retry')).length, 0);
});

test('UNKNOWN is never automatically re-executed and needs explicit confirmation', async () => {
  const calls: SubmissionRequest[] = [];
  const { client } = fixture(async request => { calls.push(request); return calls.length === 1 ? state('UNKNOWN', 1, true) : success(); });
  assert.equal((await client.submit(answers)).state, 'UNKNOWN');
  await client.retry(false); assert.equal(calls.length, 1);
  assert.equal((await client.retry(true)).state, 'SUCCEEDED');
  assert.deepEqual(calls[1].body, { expectedGeneration: 1, confirmUnknown: true });
});

test('lost retry response keeps its expected generation when the recovery request is retransmitted', async () => {
  const calls: SubmissionRequest[] = [];
  const { client } = fixture(async request => {
    calls.push(request);
    if (calls.length === 1) return state('FAILED', 1, true);
    if (calls.length === 2) throw new Error('response lost');
    return success();
  });
  await client.submit(answers); assert.equal((await client.retry()).state, 'UNKNOWN');
  assert.equal((await client.check()).state, 'SUCCEEDED');
  assert.deepEqual(calls[1], calls[2]);
});

test('confirmed failures permit at most two client recovery executions', async () => {
  const calls: SubmissionRequest[] = [];
  const { client } = fixture(async request => { calls.push(request); return state('FAILED', calls.length, true); });
  await client.submit(answers); await client.retry(); await client.retry(); await client.retry();
  assert.equal(calls.length, 3); assert.equal(client.getView().retryable, false);
});

test('editing an accepted answer cannot silently create a new key or mutate the accepted request', async () => {
  let calls = 0;
  const { client, keys } = fixture(async () => { calls++; return state('UNKNOWN', 1, true); });
  await client.submit(answers);
  const altered = { answers: [{ ...answers.answers[0], answer: '의도하지 않은 새 답안' }] };
  assert.equal((await client.submit(altered)).state, 'CONFLICT');
  assert.equal(keys(), 1); assert.equal(calls, 1);
});

test('generated logical submission keys have unique canonical UUID form', async () => {
  const generated = new Set(Array.from({ length: 100 }, () => newSubmissionKey()));
  assert.equal(generated.size, 100);
  for (const value of generated) assert.match(value, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

test('native UUID fallback distinguishes rapid calls even with a fixed clock and random source', () => {
  const crypto = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  const random = Math.random;
  const now = Date.now;
  try {
    Object.defineProperty(globalThis, 'crypto', { configurable: true, value: undefined });
    Math.random = () => 0;
    Date.now = () => 1;
    const generated = new Set(Array.from({ length: 100 }, () => newSubmissionKey()));
    assert.equal(generated.size, 100);
    for (const value of generated) assert.match(value, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  } finally {
    if (crypto) Object.defineProperty(globalThis, 'crypto', crypto); else Reflect.deleteProperty(globalThis, 'crypto');
    Math.random = random; Date.now = now;
  }
});

for (const action of ['logout', 'switchAccount'] as const) {
  test(`${action} fences a late grading result and prevents later retransmission`, async () => {
    let calls = 0;
    let complete!: (value: SubmissionResponse) => void;
    const f = fixture(async () => { calls++; return new Promise(resolve => { complete = resolve; }); });
    const pending = f.client.submit(answers); await Promise.resolve(); f[action](); complete(success());
    assert.equal((await pending).state, 'SESSION_CHANGED');
    assert.equal((await f.client.check()).state, 'SESSION_CHANGED'); assert.equal(calls, 1);
  });
}

test('a disposed screen does not deliver results or issue later requests', async () => {
  let calls = 0;
  const { client } = fixture(async () => { calls++; return success(); });
  client.dispose(); assert.equal((await client.submit(answers)).state, 'SESSION_CHANGED'); assert.equal(calls, 0);
});

test('version conflict, object denial, and malformed result remain explicit without fabricated feedback', async () => {
  for (const [response, expected] of [
    [{ status: 409, data: { code: 'QUIZ_VERSION_CONFLICT' } }, 'VERSION_CONFLICT'],
    [{ status: 409, data: { code: 'IDEMPOTENCY_KEY_CONFLICT' } }, 'CONFLICT'],
    [{ status: 404, data: {} }, 'REVOKED'],
    [{ ...success(), data: [] }, 'UNKNOWN'],
    [{ ...success(), data: [{ ...results[0], correct_answer: undefined }] }, 'UNKNOWN'],
    [{ ...success(), data: [{ ...results[0], snapshotAvailable: false }] }, 'UNKNOWN'],
    [{ ...success(), data: [{ ...results[0], version: 1 }] }, 'UNKNOWN'],
  ] as const) {
    const { client } = fixture(async () => response);
    const observed = await client.submit(answers);
    assert.equal(observed.state, expected); assert.equal(observed.results, undefined);
  }
});

test('new results preserve the initially displayed question and submitted server snapshot answer', async () => {
  const input = structuredClone(questions);
  const client = createQuizSubmission({ materialId: 7, questions: input, session: () => 1, mergeResults: mergeSubmittedQuizResults,
    makeKey: () => key, request: async () => success() });
  input[0].content = '교사가 나중에 변경한 문제';
  const view = await client.submit(answers);
  assert.equal(view.results?.[0].content, '최초 문제 내용');
  assert.equal(view.results?.[0].correct_answer, '접수 당시 서버 정답');
});

test('missing versions, duplicate questions, and overlong answers are rejected before sending', async () => {
  let calls = 0;
  for (const bad of [
    { answers: [{ quizId: 23, answer: '답안' }] },
    { answers: [{ quizId: 23, version: -1, answer: '답안' }] },
    { answers: [{ quizId: 23, version: 0, answer: '🙂'.repeat(2001) }] },
  ]) {
    const { client } = fixture(async () => { calls++; return success(); });
    assert.equal((await client.submit(bad as typeof answers)).state, 'REJECTED');
  }
  const duplicate = createQuizSubmission({ materialId: 7, questions: [...questions, ...questions], session: () => 1,
    mergeResults: mergeSubmittedQuizResults, request: async () => { calls++; return success(); } });
  assert.equal((await duplicate.submit({ answers: [...answers.answers, ...answers.answers] })).state, 'REJECTED');
  assert.equal(calls, 0);
});

test('answer limit counts Unicode code points and retains the submitted whitespace', async () => {
  const input = { answers: [{ quizId: 23, version: 0, answer: '🙂'.repeat(2000) }] };
  let calls = 0;
  const { client } = fixture(async request => {
    calls++; assert.deepEqual(request.body, input);
    return { ...success(), data: [{ ...results[0], student_answer: input.answers[0].answer }] };
  });
  assert.equal((await client.submit(input)).state, 'SUCCEEDED'); assert.equal(calls, 1);
});

test('native AT refresh leaves the logical submission key, version and answer unchanged', async () => {
  let access = 'old-access'; let refresh = 'native-refresh';
  const native = createNativeTokenSession({ getAccessToken: () => access, getRefreshToken: () => refresh,
    saveTokens: tokens => { access = tokens.accessToken; refresh = tokens.refreshToken; }, clearTokens: () => { access = ''; refresh = ''; },
    post: async () => ({ accessToken: 'new-access', refreshToken: 'rotated-native-refresh' }) });
  const sent: SubmissionRequest[] = [];
  const client = createQuizSubmission({ materialId: 7, questions, session: () => native.getEpoch(), makeKey: () => key, mergeResults: mergeSubmittedQuizResults,
    request: async request => {
      sent.push(structuredClone(request));
      // Same replay rule used by the Axios interceptor; no native network/device execution.
      await native.refreshFor(native.getEpoch(), 'old-access'); sent.push(structuredClone(request)); return success();
    } });
  assert.equal((await client.submit(answers)).state, 'SUCCEEDED');
  assert.deepEqual(sent[0], sent[1]); assert.equal(native.getEpoch(), 0);
});

test('web authenticated fetch replays the exact Idempotency-Key and versioned body after 401', async () => {
  const storage = new Map([['accessToken', 'old-access'], ['isLoggedIn', 'true']]);
  const requests: Request[] = [];
  const client = createAuthSession({ origin: 'http://127.0.0.1:15173', storage: {
    getItem: k => storage.get(k) ?? null, setItem: (k, v) => { storage.set(k, v); }, removeItem: k => { storage.delete(k); } },
    fetch: (async (input, init) => {
      const request = new Request(input, init);
      if (request.url.endsWith('/api/auth/csrf')) return Response.json({ token: 'synthetic-csrf', headerName: 'X-XSRF-TOKEN' });
      if (request.url.endsWith('/api/auth/teacher/refresh')) return Response.json({ accessToken: 'new-access' });
      requests.push(request); return requests.length === 1 ? new Response('{}', { status: 401 }) : Response.json(results);
    }) as typeof fetch });
  const response = await client.authenticatedFetch('/api/materials/7/quizzes/submit', {
    method: 'POST', headers: { 'Idempotency-Key': key, 'Content-Type': 'application/json' }, body: JSON.stringify(answers) });
  assert.equal(response.status, 200); assert.equal(requests.length, 2);
  for (const request of requests) { assert.equal(request.headers.get('Idempotency-Key'), key); assert.deepEqual(await request.json(), answers); }
});

/** Actual Chrome API contract checks. There is no student web quiz UI; native UI remains NOT_RUN. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { randomUUID } from 'node:crypto';
import assert from 'node:assert/strict';
const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const origin = process.env.DODREAM_GRADING_BROWSER_ORIGIN || 'http://127.0.0.1:15173';
const lessonTitle = process.env.DODREAM_GRADING_BROWSER_TITLE || '[GRADING LOCAL] phase4';
const base = new URL(origin);
if (!['127.0.0.1', 'localhost'].includes(base.hostname) || base.protocol !== 'http:' || base.origin !== origin) throw new Error('Loopback origin required');
const env = Object.fromEntries((await fs.readFile(path.join(root, '.local/env'), 'utf8')).split('\n')
  .filter(line => line && !line.startsWith('#')).map(line => { const at = line.indexOf('='); return [line.slice(0, at), line.slice(at + 1)]; }));
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(process.env.DODREAM_PLAYWRIGHT_PATH || '/Users/yoonsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'); }
const checks = [];
let browser;
let externalRequestsBlocked = 0;
let step = 'launch';
function check(name, condition, detail = '') {
  const item = { name, status: condition ? 'PASS' : 'FAIL', detail };
  checks.push(item); console.log(JSON.stringify(item));
  if (!condition) { const error = new Error('Recorded check'); error.recorded = true; throw error; }
}
async function contextPage() {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin !== origin) { externalRequestsBlocked++; return route.abort(); }
    return route.continue();
  });
  const page = await context.newPage(); page.setDefaultTimeout(15000); await page.goto(origin);
  return { context, page };
}
async function api(page, pathname, method = 'GET', body, key) {
  assert.ok(pathname.startsWith('/api/'));
  return page.evaluate(async ({ pathname, method, body, key }) => {
    const headers = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + localStorage.getItem('accessToken') };
    if (key !== undefined) headers['Idempotency-Key'] = key;
    const response = await fetch(pathname, { method, headers, credentials: 'omit', body: body === undefined ? undefined : JSON.stringify(body) });
    let data; try { data = await response.json(); } catch { data = null; }
    return { status: response.status, data, attemptId: response.headers.get('X-Grading-Attempt-Id'), state: response.headers.get('X-Grading-State') };
  }, { pathname, method, body, key });
}
async function teacherLogin(page) {
  return page.evaluate(async password => {
    const csrf = await (await fetch('/api/auth/csrf', { credentials: 'include' })).json();
    const response = await fetch('/api/auth/teacher/login', { method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json', [csrf.headerName]: csrf.token },
      body: JSON.stringify({ email: 'authz-owner@local.dodream.invalid', password }) });
    if (response.ok) localStorage.setItem('accessToken', (await response.json()).accessToken);
    return response.status;
  }, env.LOCAL_TEACHER_PASSWORD);
}
async function studentLogin(page) {
  return page.evaluate(async deviceSecret => {
    const response = await fetch('/api/auth/student/native/login', { method: 'POST', credentials: 'omit', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deviceId: 'dodream-authz-shared', deviceSecret }) });
    if (response.ok) {
      const tokens = await response.json(); localStorage.setItem('accessToken', tokens.accessToken);
      sessionStorage.setItem('grading-test-refresh', tokens.refreshToken);
    }
    return response.status;
  }, env.LOCAL_STUDENT_SECRET);
}
const containsAnswer = value => value && typeof value === 'object' && Object.entries(value).some(([key, child]) =>
  ['correct_answer', 'correctAnswer', 'answer', 'rubric', 'teacher_notes'].includes(key) || containsAnswer(child));
async function settle(page, materialId, response) {
  for (let count = 0; count < 5 && response.status === 202; count++) {
    const attemptId = response.data?.attemptId;
    assert.match(attemptId, /^[0-9a-f-]{36}$/);
    await new Promise(resolve => setTimeout(resolve, 1000));
    response = await api(page, `/api/materials/${materialId}/quiz-attempts/${attemptId}`);
  }
  return response;
}
let student;
try {
  browser = await playwright.chromium.launch({ executablePath: process.env.DODREAM_CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--disable-background-networking', '--disable-component-update', '--disable-sync', '--no-first-run'] });
  const owner = await contextPage(); student = await contextPage();
  step = 'synthetic API logins and dedicated grading fixture';
  assert.equal(await teacherLogin(owner.page), 200); assert.equal(await studentLogin(student.page), 200);
  const listing = await api(owner.page, '/api/documents/published'); assert.equal(listing.status, 200);
  const material = listing.data.materials.find(row => row.title === lessonTitle); assert.ok(material?.materialId);
  const id = material.materialId;
  await owner.context.close();
  step = 'student version and answer projection';
  const read = await api(student.page, `/api/materials/${id}/quizzes`);
  check('browser_grading_api_version_without_answers', read.status === 200 && read.data.length === 2 &&
    read.data.every(question => Number.isSafeInteger(question.version) && question.version >= 0) && !containsAnswer(read.data));
  const body = { answers: read.data.map(question => ({ quizId: question.id, version: question.version, answer: '  합성 브라우저 답안  ' })) };
  const submitPath = `/api/materials/${id}/quizzes/submit`;
  check('browser_grading_api_missing_key_rejected', (await api(student.page, submitPath, 'POST', body)).status === 400);
  step = 'normal browser API submission';
  const key = randomUUID();
  const first = await settle(student.page, id, await api(student.page, submitPath, 'POST', body, key));
  const questionsById = new Map(read.data.map(question => [question.id, question]));
  check('browser_grading_api_success_snapshot_feedback', first.status === 200 && first.state === 'SUCCEEDED' &&
    /^[0-9a-f-]{36}$/.test(first.attemptId) && Array.isArray(first.data) && first.data.length === 2 &&
    new Set(first.data.map(result => result.question_id)).size === questionsById.size &&
    first.data.every(result => {
      const question = questionsById.get(result.question_id);
      return question && result.attemptId === first.attemptId && result.snapshotAvailable === true &&
        result.version === question.version && result.questionContent === question.content &&
        typeof result.gradingVersion === 'string' && result.gradingVersion.length > 0 &&
        result.student_answer === body.answers.find(answer => answer.quizId === result.question_id)?.answer &&
        typeof result.is_correct === 'boolean' && typeof result.correct_answer === 'string' && typeof result.ai_feedback === 'string';
    }));
  const replay = await api(student.page, submitPath, 'POST', body, key);
  check('browser_grading_api_identical_replay', replay.status === 200 && replay.attemptId === first.attemptId && JSON.stringify(replay.data) === JSON.stringify(first.data));
  const conflictBody = structuredClone(body); conflictBody.answers[0].answer += ' 다른 답안';
  const conflict = await api(student.page, submitPath, 'POST', conflictBody, key);
  check('browser_grading_api_conflicting_body_rejected', conflict.status === 409 && conflict.data?.code === 'IDEMPOTENCY_KEY_CONFLICT');
  const current = await api(student.page, `/api/materials/${id}/quiz-attempts/${first.attemptId}`);
  check('browser_grading_api_owned_result_lookup', current.status === 200 && JSON.stringify(current.data) === JSON.stringify(first.data));
  step = 'two simultaneous browser API sends with one logical key';
  const concurrentKey = randomUUID();
  const concurrent = await Promise.all([api(student.page, submitPath, 'POST', body, concurrentKey), api(student.page, submitPath, 'POST', body, concurrentKey)]);
  const finalized = await Promise.all(concurrent.map(response => settle(student.page, id, response)));
  check('browser_grading_api_double_send_one_attempt', finalized.every(response => response.status === 200) &&
    finalized[0].attemptId === finalized[1].attemptId && finalized[0].attemptId !== first.attemptId);
  step = 'real server completion followed by browser response loss';
  const lostKey = randomUUID(); let intercepted = 0; let committed;
  await student.page.route('**/api/materials/*/quizzes/submit', async route => {
    if (route.request().headers()['idempotency-key'] !== lostKey) return route.continue();
    intercepted++;
    const response = await route.fetch();
    committed = { status: response.status(), attemptId: response.headers()['x-grading-attempt-id'], data: await response.json() };
    await route.abort('failed');
  });
  let lost = false;
  try { await api(student.page, submitPath, 'POST', body, lostKey); } catch { lost = true; }
  await student.page.unroute('**/api/materials/*/quizzes/submit');
  check('browser_grading_api_response_loss_after_commit', lost && intercepted === 1 && committed?.status === 200,
    'Browser delivery aborted after real server success; provider behavior was not mocked');
  const recovered = await api(student.page, submitPath, 'POST', body, lostKey);
  check('browser_grading_api_lost_response_replay', recovered.status === 200 && recovered.attemptId === committed.attemptId &&
    JSON.stringify(recovered.data) === JSON.stringify(committed.data));
  check('browser_grading_api_intentional_new_key_new_attempt', recovered.attemptId !== first.attemptId && recovered.attemptId !== finalized[0].attemptId);
} catch (error) {
  if (!error.recorded) {
    const item = { name: 'browser_grading_api_execution', status: browser ? 'FAIL' : 'BLOCKED', detail: { error: error.name, step } };
    checks.push(item); console.log(JSON.stringify(item));
  }
} finally {
  if (student) {
    const status = await student.page.evaluate(async () => {
      const refreshToken = sessionStorage.getItem('grading-test-refresh');
      if (!refreshToken) return 0;
      const response = await fetch('/api/auth/student/native/logout', { method: 'POST', credentials: 'omit', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refreshToken }) });
      localStorage.removeItem('accessToken'); sessionStorage.removeItem('grading-test-refresh'); return response.status;
    }).catch(() => 0);
    const item = { name: 'browser_grading_api_test_session_revoked', status: status === 200 ? 'PASS' : 'FAIL', detail: 'HTTP ' + status };
    checks.push(item); console.log(JSON.stringify(item));
  }
  const version = browser?.version() || 'unavailable'; if (browser) await browser.close();
  const report = { browser: 'Chrome ' + version, origin, mode: 'BROWSER_API_CONTRACT_ONLY', studentWebUi: 'NOT_IMPLEMENTED',
    nativeDeviceExecution: 'NOT_RUN', externalRequestsBlocked, checks,
    counts: Object.fromEntries(['PASS', 'FAIL', 'BLOCKED'].map(status => [status, checks.filter(row => row.status === status).length])) };
  const output = path.join(root, '.local/phase4/results/browser-grading-checks.json');
  await fs.mkdir(path.dirname(output), { recursive: true }); await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n');
  await fs.writeFile(output.replace('.json', '-' + Date.now() + '.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ counts: report.counts, evidence: output })); process.exitCode = checks.some(row => row.status !== 'PASS') ? 1 : 0;
}

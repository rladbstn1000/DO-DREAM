/** Actual local Chrome UI and actual Spring/DB policies. Only external providers use local adapters. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const origin = process.env.DODREAM_AUTHZ_BROWSER_ORIGIN || 'http://127.0.0.1:15173';
const base = new URL(origin);
if (!['127.0.0.1', 'localhost'].includes(base.hostname) || base.protocol !== 'http:' || base.origin !== origin) {
  throw new Error('Only a loopback HTTP origin is allowed');
}
const env = Object.fromEntries((await fs.readFile(path.join(root, '.local/env'), 'utf8')).split('\n')
  .filter(line => line && !line.startsWith('#')).map(line => {
    const i = line.indexOf('='); return [line.slice(0, i), line.slice(i + 1)];
  }));
const password = env.LOCAL_TEACHER_PASSWORD;
if (!password) throw new Error('Generated local teacher credential unavailable');
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(process.env.DODREAM_PLAYWRIGHT_PATH || '/Users/yoonsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'); }

const checks = [];
let browser;
let blockedExternal = 0;
let step = 'launch';
const check = (name, passed, detail = '') => {
  const row = { name, status: passed ? 'PASS' : 'FAIL', detail };
  checks.push(row); console.log(JSON.stringify(row));
  if (!passed) { const error = new Error('Recorded assertion'); error.recorded = true; throw error; }
};
async function scenario(name, action) {
  step = name;
  try { await action(); }
  catch (error) {
    if (!error.recorded) {
      const row = { name, status: 'FAIL', detail: { error: error.name, step } };
      checks.push(row); console.log(JSON.stringify(row));
    }
    if (name === 'browser_owner_editor') throw error;
  }
}
async function contextPage() {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin !== origin) { blockedExternal++; return route.abort(); }
    return route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  return { context, page };
}
async function login(email) {
  const state = await contextPage();
  const { page } = state;
  let refreshes = 0;
  const protectedResponses = [];
  page.on('request', request => { if (request.url().endsWith('/api/auth/teacher/refresh')) refreshes++; });
  page.on('response', response => {
    if (/\/api\/(documents\/published|classes\/teacher)$/.test(response.url())) protectedResponses.push(response.status());
  });
  await page.goto(origin);
  await page.getByText('로그인 하기', { exact: true }).click();
  await page.locator('form.sign-in input[name="email"]').fill(email);
  await page.locator('form.sign-in input[name="password"]').fill(password);
  const response = page.waitForResponse(r => r.url().endsWith('/api/auth/teacher/login'));
  await page.locator('form.sign-in button[type="submit"]').click();
  assert.equal((await response).status(), 200);
  await page.waitForURL('**/classrooms');
  await page.waitForLoadState('networkidle');
  await page.locator('.swal2-container').waitFor({ state: 'hidden' });
  assert.ok(protectedResponses.filter(status => status === 200).length >= 2);
  return { ...state, refreshes: () => refreshes };
}
async function api(page, pathname, method = 'GET', body, timeoutMs) {
  assert.ok(pathname.startsWith('/api/') || pathname.startsWith('/ai/'));
  return page.evaluate(async ({ pathname, method, body, timeoutMs }) => {
    const response = await fetch(pathname, { method, credentials: 'include',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + localStorage.getItem('accessToken') },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: timeoutMs === undefined ? undefined : AbortSignal.timeout(timeoutMs) });
    const text = await response.text();
    let data;
    try { data = text ? JSON.parse(text) : null; } catch { data = null; }
    return { status: response.status, data };
  }, { pathname, method, body, timeoutMs });
}
async function waitForCurrentIndex(page, materialId, sourceRevision) {
  const deadline = Date.now() + 30000;
  for (let count = 0; count < 60; count++) {
    const remaining = deadline - Date.now();
    if (remaining <= 0) break;
    const response = await api(page, `/api/documents/${materialId}/indexing`, 'GET', undefined, Math.min(8000, remaining));
    assert.equal(response.status, 200);
    assert.equal(response.data.sourceRevision, sourceRevision);
    if (response.data.readable === true && response.data.activeCurrent === true) return;
    assert.ok(['QUEUED', 'PROCESSING'].includes(response.data.state));
    if (Date.now() >= deadline) break;
    await new Promise(resolve => setTimeout(resolve, Math.min(500, deadline - Date.now())));
  }
  throw new Error('Current index did not become available');
}
const editingJson = data => data?.parsedData ?? data?.editedJson ?? data;
const hasSession = page => page.evaluate(() => !!localStorage.getItem('accessToken') && localStorage.getItem('isLoggedIn') === 'true');
function containsTeacherAnswer(value) {
  if (!value || typeof value !== 'object') return false;
  return Object.entries(value).some(([key, child]) =>
    ['correct_answer', 'correctAnswer', 'answer', 'rubric', 'marking_rubric', 'teacher_notes'].includes(key) || containsTeacherAnswer(child));
}
async function studentLogin() {
  const state = await contextPage();
  await state.page.goto(origin);
  const status = await state.page.evaluate(async deviceSecret => {
    const response = await fetch('/api/auth/student/native/login', { method: 'POST', credentials: 'omit',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ deviceId: 'dodream-authz-shared', deviceSecret }) });
    if (response.ok) {
      const data = await response.json();
      localStorage.setItem('accessToken', data.accessToken);
      sessionStorage.setItem('authz-test-native-refresh', data.refreshToken);
    }
    return response.status;
  }, env.LOCAL_STUDENT_SECRET);
  assert.equal(status, 200);
  return state;
}
async function studentLogout(page) {
  return page.evaluate(async () => {
    const refreshToken = sessionStorage.getItem('authz-test-native-refresh');
    const response = await fetch('/api/auth/student/native/logout', { method: 'POST', credentials: 'omit',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refreshToken }) });
    localStorage.removeItem('accessToken'); sessionStorage.removeItem('authz-test-native-refresh');
    return response.status;
  });
}
const lessonTitle = process.env.DODREAM_AUTHZ_BROWSER_TITLE || '[AUTHZ 4] editable';
let lesson;
let original;

try {
  browser = await playwright.chromium.launch({
    executablePath: process.env.DODREAM_CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--disable-background-networking', '--disable-component-update', '--disable-sync', '--no-first-run'],
  });
  await scenario('browser_owner_editor', async () => {
    const { context, page } = await login('authz-owner@local.dodream.invalid');
    let mutated = false;
    try {
      step = 'owner fixture lookup';
      const listing = await api(page, '/api/documents/published');
      assert.equal(listing.status, 200);
      lesson = listing.data.materials.find(row => row.title === lessonTitle);
      assert.ok(lesson && lesson.uploadedFileId && lesson.materialId);
      const before = await api(page, `/api/pdf/${lesson.uploadedFileId}/json`);
      assert.equal(before.status, 200);
      const quizBefore = await api(page, `/api/materials/${lesson.materialId}/quizzes`);
      assert.equal(quizBefore.status, 200);
      original = { materialTitle: lesson.title, labelColor: lesson.label,
        editedJson: editingJson(before.data),
        quizzes: quizBefore.data.map(({ id: _id, ...quiz }) => quiz) };
      assert.ok(Array.isArray(original.editedJson.chapters));
      step = 'owner opens editor through material list';
      const loaded = page.waitForResponse(r => r.url().endsWith(`/api/pdf/${lesson.uploadedFileId}/json`));
      await page.getByRole('heading', { name: lessonTitle, exact: true }).click();
      assert.equal((await loaded).status(), 200);
      await page.waitForURL('**/editor');
      const editor = page.locator('.tiptap[contenteditable="true"]').first();
      await editor.waitFor({ state: 'visible' });
      await page.getByRole('button', { name: '수정하기', exact: true }).waitFor({ state: 'visible' });
      check('browser_owner_material_opens_real_editor', await page.getByRole('button', { name: '수정하기', exact: true }).isVisible());
      step = 'owner edits and saves through UI';
      const marker = '합성 브라우저 권한 검증 편집 내용';
      await editor.fill(marker);
      const saved = page.waitForResponse(r => r.url().endsWith(`/api/documents/${lesson.uploadedFileId}/publish`) && r.request().method() === 'POST');
      await page.getByRole('button', { name: '수정하기', exact: true }).click();
      const response = await saved;
      mutated = response.status() === 200;
      check('browser_owner_editor_save_allowed', response.status() === 200, 'HTTP ' + response.status());
      const published = await response.json();
      await page.locator('.swal2-confirm').click();
      await page.waitForURL('**/classrooms');
      await page.locator('.swal2-container').waitFor({ state: 'hidden' });
      await page.getByRole('heading', { name: lessonTitle, exact: true }).click();
      await page.waitForURL('**/editor');
      await page.locator('.tiptap[contenteditable="true"]').first().waitFor({ state: 'visible' });
      const reread = await api(page, `/api/pdf/${lesson.uploadedFileId}/json`);
      check('browser_owner_saved_content_reloaded', reread.status === 200 && JSON.stringify(editingJson(reread.data)).includes(marker) &&
        (await page.locator('.tiptap[contenteditable="true"]').first().innerText()).includes(marker));
      step = 'owner generates quiz with canonical Material ID';
      await waitForCurrentIndex(page, lesson.materialId, published.indexing.sourceRevision);
      const generation = page.waitForResponse(r => r.url().endsWith('/ai/rag/quiz/generate'));
      await page.getByRole('button', { name: 'AI 퀴즈 생성', exact: true }).click();
      const generated = await generation;
      const request = generated.request().postDataJSON();
      check('browser_owner_quiz_generation_material_contract', generated.status() === 200 && request.document_id === String(lesson.materialId), 'HTTP ' + generated.status());
    } finally {
      if (mutated) {
        step = 'restore synthetic edited content';
        const restored = await api(page, `/api/documents/${lesson.uploadedFileId}/publish`, 'POST', original);
        check('browser_synthetic_content_restored', restored.status === 200, 'HTTP ' + restored.status);
        await waitForCurrentIndex(page, lesson.materialId, restored.data.indexing.sourceRevision);
      }
      await context.close();
    }
  });
  await scenario('browser_unrelated_teacher', async () => {
    assert.ok(lesson && original);
    const { context, page, refreshes } = await login('authz-other@local.dodream.invalid');
    try {
      check('browser_unrelated_teacher_list_excludes_private_material', await page.getByRole('heading', { name: lessonTitle, exact: true }).count() === 0);
      step = 'unrelated teacher direct object requests';
      const read = await api(page, `/api/pdf/${lesson.uploadedFileId}/json`);
      check('browser_unrelated_teacher_file_read_denied', read.status === 404, 'HTTP ' + read.status);
      // Tamper only with this test browser's navigation input. The actual app must still hit server policy.
      await page.evaluate(({ fileId, materialId }) => sessionStorage.setItem('editor_payload_v1', JSON.stringify({
        fileName: '합성 무권한 편집 시도', pdfId: fileId, materialId: String(materialId), mode: 'edit',
        chapters: [{ id: '1', title: '합성 입력', content: '<p>사용자가 보낸 무권한 편집 입력</p>', type: 'content' }],
      })), { fileId: lesson.uploadedFileId, materialId: lesson.materialId });
      await page.goto(origin + '/editor');
      step = 'unrelated teacher quiz generation through UI';
      const generation = page.waitForResponse(r => r.url().endsWith('/ai/rag/quiz/generate'));
      await page.getByRole('button', { name: 'AI 퀴즈 생성', exact: true }).click();
      check('browser_unrelated_teacher_quiz_generation_denied', (await generation).status() === 404);
      await page.locator('.swal2-confirm').click();
      step = 'unrelated teacher save through UI';
      const saved = page.waitForResponse(r => r.url().endsWith(`/api/documents/${lesson.uploadedFileId}/publish`) && r.request().method() === 'POST');
      await page.getByRole('button', { name: '수정하기', exact: true }).click();
      check('browser_unrelated_teacher_editor_save_denied', (await saved).status() === 404);
      await page.locator('.swal2-confirm').click();
      check('browser_object_denial_keeps_teacher_session', await hasSession(page) && page.url().endsWith('/editor') && refreshes() === 0);
    } finally { await context.close(); }
  });
  await scenario('browser_denied_edit_has_no_effect', async () => {
    assert.ok(lesson && original);
    const { context, page } = await login('authz-owner@local.dodream.invalid');
    try {
      const current = await api(page, `/api/pdf/${lesson.uploadedFileId}/json`);
      assert.equal(current.status, 200);
      assert.deepEqual(editingJson(current.data), original.editedJson);
      check('browser_denied_editor_attempt_preserves_owner_content', true);
    } finally { await context.close(); }
  });
  await scenario('browser_share_revocation', async () => {
    assert.ok(lesson);
    const owner = await login('authz-owner@local.dodream.invalid');
    const student = await studentLogin();
    let revoked = false;
    let restoreBody;
    try {
      step = 'discover synthetic assigned student using actual owner API';
      const classes = await api(owner.page, '/api/classes/teacher');
      assert.equal(classes.status, 200);
      const classroom = classes.data.classrooms.find(row => row.gradeLevel === 9 && row.classNumber === 91);
      assert.ok(classroom);
      const students = await api(owner.page, `/api/classes/students?classroomIds=${classroom.classroomId}`);
      assert.equal(students.status, 200);
      const pupil = students.data.flatMap(row => row.students).find(row => row.studentName === 'AUTHZ 학생 shared');
      assert.ok(pupil);
      restoreBody = { materialId: lesson.materialId, shares: { [String(classroom.classroomId)]: {
        type: 'INDIVIDUAL', studentIds: [pupil.studentId],
      } } };
      step = 'owner navigates through classroom and student UI';
      await owner.page.getByRole('heading', { name: '9학년 91반', exact: true }).click();
      await owner.page.waitForURL(`**/classroom/${classroom.classroomId}`);
      await owner.page.getByText('AUTHZ 학생 shared', { exact: true }).click();
      await owner.page.waitForURL(`**/student/${pupil.studentId}`);
      await owner.page.waitForLoadState('networkidle');
      check('browser_owner_assigned_student_shared_material_visible', await owner.page.getByRole('heading', { name: lessonTitle, exact: true }).count() === 1);
      step = 'student API positive control from separate browser context';
      const material = await api(student.page, `/api/materials/shared/${lesson.materialId}/json`);
      const quizzes = await api(student.page, `/api/materials/${lesson.materialId}/quizzes`);
      check('browser_student_api_shared_json_and_quiz_whitelist', material.status === 200 && quizzes.status === 200 &&
        Array.isArray(quizzes.data) && quizzes.data.length > 0 && !containsTeacherAnswer(material.data) && !containsTeacherAnswer(quizzes.data),
      'Actual browser requests; native UI execution remains NOT_RUN');
      step = 'owner revokes only this synthetic student share';
      const removed = await api(owner.page, `/api/materials/${lesson.materialId}/shares/${pupil.studentId}`, 'DELETE');
      revoked = removed.status === 204;
      check('browser_owner_share_revocation_allowed', removed.status === 204, 'HTTP ' + removed.status);
      await owner.page.reload(); await owner.page.waitForLoadState('networkidle');
      check('browser_teacher_student_view_excludes_revoked_share', await owner.page.getByRole('heading', { name: lessonTitle, exact: true }).count() === 0 &&
        await hasSession(owner.page) && owner.page.url().endsWith(`/student/${pupil.studentId}`));
      const deniedJson = await api(student.page, `/api/materials/shared/${lesson.materialId}/json`);
      const deniedQuiz = await api(student.page, `/api/materials/${lesson.materialId}/quizzes`);
      const deniedChat = await api(student.page, '/ai/rag/chat', 'POST', { document_id: String(lesson.materialId), question: '합성 공유 회수 확인' });
      check('browser_student_api_revoked_objects_denied', deniedJson.status === 404 && deniedQuiz.status === 404 && deniedChat.status === 404,
        'json=' + deniedJson.status + ', quiz=' + deniedQuiz.status + ', chat=' + deniedChat.status);
    } finally {
      try {
        if (revoked) {
          step = 'restore only the synthetic share changed by this scenario';
          const restored = await api(owner.page, '/api/materials/share', 'POST', restoreBody);
          const positive = await api(student.page, `/api/materials/shared/${lesson.materialId}/json`);
          check('browser_synthetic_share_restored', restored.status === 200 && positive.status === 200);
        }
        check('browser_native_api_test_session_revoked', await studentLogout(student.page) === 200);
      } finally {
        await student.context.close(); await owner.context.close();
      }
    }
  });
} catch (error) {
  if (!checks.some(row => row.status === 'FAIL')) checks.push({ name: 'browser_authorization_execution', status: browser ? 'FAIL' : 'BLOCKED', detail: { error: error.name, step } });
} finally {
  const version = browser ? browser.version() : 'unavailable';
  if (browser) await browser.close();
  const report = { browser: 'Chrome ' + version, origin, checks, externalRequestsBlocked: blockedExternal,
    nativeDeviceExecution: 'NOT_RUN', counts: Object.fromEntries(['PASS', 'FAIL', 'BLOCKED'].map(status => [status, checks.filter(row => row.status === status).length])) };
  const output = path.join(root, '.local/phase5/results/browser-authorization-checks.json');
  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n');
  await fs.writeFile(output.replace('.json', '-' + Date.now() + '.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ counts: report.counts, evidence: output }));
  process.exitCode = checks.some(row => row.status !== 'PASS') ? 1 : 0;
}

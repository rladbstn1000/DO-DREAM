/** Bounded real-server student journey + synthetic teacher DOM probe; no fixture edits. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const origin = 'http://127.0.0.1:15173';
const settings = Object.fromEntries((await fs.readFile(path.join(root, '.local/env'), 'utf8')).split('\n')
  .filter(line => line && !line.startsWith('#')).map(line => { const at = line.indexOf('='); return [line.slice(0, at), line.slice(at + 1)]; }));
assert.equal(settings.WEB_PORT, '15173');
let playwright;
try { playwright = require('playwright'); } catch {
  playwright = require('/Users/yoonsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
}
const checks = [];
let browser, externalRequests = 0, step = 'launch';
function check(name, ok, category = 'ACTUAL_UI') {
  checks.push({ name, status: ok ? 'PASS' : 'FAIL', category });
  assert.ok(ok, name);
}
async function context() {
  const context = await browser.newContext({ serviceWorkers: 'block', viewport: { width: 1280, height: 900 } });
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin !== origin) { externalRequests++; return route.abort(); }
    return route.continue();
  });
  const page = await context.newPage(); page.setDefaultTimeout(20000);
  return { context, page };
}
async function api(page, pathname) {
  assert.ok(pathname.startsWith('/api/') || pathname.startsWith('/ai/'));
  return page.evaluate(async pathname => {
    const response = await fetch(pathname, { credentials: 'include', signal: AbortSignal.timeout(15000),
      headers: { Authorization: 'Bearer ' + localStorage.getItem('accessToken') } });
    return { status: response.status, data: await response.json().catch(() => null) };
  }, pathname);
}
try {
  browser = await playwright.chromium.launch({ channel: 'chrome', headless: true });
  const student = await context(); const page = student.page;
  step = 'student bootstrap';
  await page.goto(origin + '/demo');
  await page.getByRole('button', { name: '학생 체험 시작', exact: true }).click();
  await page.waitForURL('**/learn');
  const identity = await api(page, '/api/session/me');
  check('server_verified_new_demo_student', identity.status === 200 && identity.data.role === 'STUDENT' && identity.data.demo === true);
  const mode = await api(page, '/ai/rag/mode');
  check('explicit_keyless_mode', mode.status === 200 && mode.data.configured_mode === 'LOCAL_FAKE');
  const unauthorized = await api(page, '/ai/rag/chat/sessions?student_id=1');
  check('other_subject_history_denied', [403, 404].includes(unauthorized.status), 'API_BOUNDARY');
  const teacherOnly = await api(page, '/api/teacher/me');
  check('student_teacher_api_denied', teacherOnly.status === 403, 'API_BOUNDARY');
  step = 'read and ask';
  await page.getByRole('link', { name: /학습 시작$/ }).first().click();
  await page.locator('.learn-reading-text').waitFor();
  check('real_material_body', (await page.locator('.learn-reading-text').innerText()).length > 30);
  const materialId = new URL(page.url()).pathname.split('/')[2];
  const questions = await api(page, `/api/materials/${materialId}/quizzes`);
  check('student_questions_hide_answers', questions.status === 200 && questions.data.length > 0 && questions.data.every(q => !('correct_answer' in q)), 'API_BOUNDARY');
  await page.getByLabel('질문', { exact: true }).fill('물은 어떻게 순환하나요?');
  await page.getByRole('button', { name: '질문 보내기', exact: true }).click();
  await page.getByRole('heading', { name: '자료를 참고한 답변', exact: true }).waitFor();
  check('local_answer_through_real_search', (await page.locator('.learn-conversation').innerText()).includes('로컬 대역 답변'));
  await page.getByRole('button', { name: /^참고 자료 보기/ }).first().click();
  await page.locator('dialog[open] blockquote').waitFor();
  check('authorized_source_excerpt', (await page.locator('dialog[open] blockquote').innerText()).length > 10);
  await page.getByRole('button', { name: '참고 자료 닫기' }).click();
  await page.getByRole('button', { name: '대화 기록 확인', exact: true }).click();
  check('history_after_source_join', await page.getByRole('heading', { name: '자료를 참고한 답변', exact: true }).count() === 1);
  step = 'quiz and reload';
  await page.getByRole('link', { name: '퀴즈 풀기', exact: true }).click();
  await page.locator('.learn-quiz-form textarea').first().waitFor();
  for (const field of await page.locator('.learn-quiz-form textarea').all()) await field.fill('물이 증발하고 응결하여 비로 내려옵니다.');
  await page.getByRole('button', { name: '제출하기', exact: true }).click();
  await page.waitForURL(/\/results\/[0-9a-f-]+$/);
  await page.locator('.learn-result-list article').first().waitFor();
  check('stored_grading_result', await page.locator('.learn-result-list article').count() === questions.data.length);
  await page.reload();
  await page.locator('.learn-result-list article').first().waitFor();
  check('result_survives_reload', await page.locator('.learn-result-list article').count() === questions.data.length);
  await student.context.close();

  // This probe injects only authored browser state. It never saves/edits a DB material.
  step = 'teacher modal text';
  const teacher = await context();
  await teacher.page.goto(origin + '/');
  await teacher.page.getByText('로그인 하기', { exact: true }).click();
  step = 'teacher login form';
  await teacher.page.locator('form.sign-in input[name=email]').fill('teacher@local.dodream.invalid');
  await teacher.page.locator('form.sign-in input[type=password]').fill(settings.LOCAL_TEACHER_PASSWORD);
  await teacher.page.locator('form.sign-in button[type=submit]').click();
  await teacher.page.waitForURL('**/classrooms');
  await teacher.page.locator('.swal2-container').waitFor({ state: 'hidden' });
  step = 'teacher editor';
  const marker = '\"><img src=x onerror="window.__hardeningExecuted=true">';
  await teacher.page.evaluate(marker => sessionStorage.setItem('editor_payload_v1', JSON.stringify({
    fileName: 'Synthetic rendering probe', mode: 'create', chapters: [
      { id: '1', title: marker, content: '<p>First synthetic text</p>', type: 'content' },
      { id: '2', title: 'Second synthetic title', content: '<p>Second synthetic text</p>', type: 'content' },
    ],
  })), marker);
  await teacher.page.goto(origin + '/editor');
  await teacher.page.getByRole('button', { name: '항목 병합 모드', exact: true }).click();
  await teacher.page.locator('.ae-chapter-item').nth(0).click();
  await teacher.page.locator('.ae-chapter-item').nth(1).click();
  await teacher.page.getByRole('button', { name: '병합하기 (2)', exact: true }).click();
  step = 'teacher merge modal';
  await teacher.page.locator('#mergedTitle').waitFor();
  check('persisted_title_is_text_in_modal', (await teacher.page.locator('#mergedTitle').inputValue()).includes(marker)
    && await teacher.page.locator('.swal2-html-container img').count() === 0
    && !await teacher.page.evaluate(() => window.__hardeningExecuted), 'SYNTHETIC_DOM');
  await teacher.context.close();
  check('no_external_resource_requests', externalRequests === 0, 'NETWORK');
} catch (error) {
  checks.push({ name: step, status: 'FAIL', category: 'HARNESS', errorType: error.constructor.name });
  process.exitCode = 1;
} finally {
  await browser?.close();
  const result = { status: process.exitCode ? 'FAIL' : 'PASS', checks, externalRequests,
    scope: 'one new synthetic student; existing material rows untouched; teacher DOM probe never published' };
  const directory = path.join(root, '.local/portfolio-hardening/results');
  await fs.mkdir(directory, { recursive: true });
  const stamp = new Date().toISOString().replaceAll(':', '').replaceAll('.', '');
  await fs.writeFile(path.join(directory, `browser-hardening-${stamp}.json`), JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
  await fs.writeFile(path.join(directory, 'browser-hardening-checks.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result));
}

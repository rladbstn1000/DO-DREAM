/** Actual teacher UI + real indexing services. Root alone controls local fault gates and Docker. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const origin = process.env.DODREAM_INDEX_BROWSER_ORIGIN || 'http://127.0.0.1:15173';
const base = new URL(origin);
if (!['127.0.0.1', 'localhost'].includes(base.hostname) || base.protocol !== 'http:' || base.origin !== origin) throw new Error('Loopback origin required');
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const checks = [];
let browser, plan, handshakeDirectory;
let handshakeAccepted = false;
let interrupted = false;
// The owning runner may stop this one child; close only its isolated Chrome.
process.once('SIGTERM', () => { interrupted = true; void browser?.close(); });
process.once('SIGINT', () => { interrupted = true; void browser?.close(); });
let externalRequestsBlocked = 0;
let step = 'read synthetic fixture plan';
let completedActivation;
const observations = [];
function check(name, condition, detail = '') {
  const row = { name, status: condition ? 'PASS' : 'FAIL', detail };
  checks.push(row); console.log(JSON.stringify(row));
  if (!condition) { const error = new Error('Recorded assertion'); error.recorded = true; throw error; }
}
async function checkpoint(event, data = {}) {
  if (!handshakeAccepted) return;
  const target = path.join(handshakeDirectory, `${plan.runId}.${event}.json`);
  const temporary = target + '.tmp';
  await fs.writeFile(temporary, JSON.stringify({ runId: plan.runId, event, ...data, at: new Date().toISOString() }) + '\n', { flag: 'wx' });
  // Link publishes the complete file atomically and refuses to replace an earlier run.
  await fs.link(temporary, target);
  await fs.unlink(temporary);
}
async function contextPage() {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin !== origin) { externalRequestsBlocked++; return route.abort(); }
    return route.continue();
  });
  const page = await context.newPage(); page.setDefaultTimeout(30000);
  return { context, page };
}
async function api(page, pathname, timeoutMs = 8000) {
  assert.ok(/^\/api\/documents\/[1-9][0-9]*\/indexing$/.test(pathname));
  return page.evaluate(async ({ pathname, timeoutMs }) => {
    const response = await fetch(pathname, { headers: { Authorization: 'Bearer ' + localStorage.getItem('accessToken') }, credentials: 'include', signal: AbortSignal.timeout(timeoutMs) });
    let data; try { data = await response.json(); } catch { data = null; }
    return { status: response.status, data };
  }, { pathname, timeoutMs });
}
async function currentIndex(page, materialId, predicate) {
  const deadline = Date.now() + 30000;
  for (let count = 0; count < 60; count++) {
    const remaining = deadline - Date.now();
    if (remaining <= 0) break;
    const response = await api(page, `/api/documents/${materialId}/indexing`, Math.min(8000, remaining));
    assert.equal(response.status, 200);
    if (predicate(response.data)) return response.data;
    if (Date.now() >= deadline) break;
    await new Promise(resolve => setTimeout(resolve, Math.min(500, deadline - Date.now())));
  }
  throw new Error('Index state deadline exceeded');
}
const indexPanel = (page, materialId) => page.locator(`[data-indexing-resource="/api/documents/${materialId}/indexing"]`);
const materialRow = (page, title) => page.locator('.cl-material-info').filter({ has: page.getByRole('heading', { name: title, exact: true }) });
async function readyUi(page, materialId) {
  const panel = indexPanel(page, materialId);
  const button = panel.getByRole('button', { name: '상태 확인', exact: true });
  if (await button.isVisible() && await button.isEnabled()) await button.click();
  await panel.getByRole('status').filter({ hasText: /^사용 가능$/ }).waitFor();
}
async function recoverThroughUi(page, row, kind, expectedReadable) {
  const panel = indexPanel(page, row.materialId);
  const before = (await api(page, `/api/documents/${row.materialId}/indexing`)).data;
  check(`browser_indexing_${kind}_server_failure`, before.state === 'FAILED' && before.readable === expectedReadable && before.activeCurrent === false && before.retryable === true);
  const expected = expectedReadable ? '사용 가능 · 재색인 실패' : '색인 실패';
  check(`browser_indexing_${kind}_ui_failure`, await panel.getByRole('status').innerText() === expected);
  const retryResponse = page.waitForResponse(response => response.url().endsWith(`/api/indexing/jobs/${before.jobId}/retry`) && response.request().method() === 'POST');
  await panel.getByRole('button', { name: '색인 다시 시도', exact: true }).click();
  const response = await retryResponse;
  const sent = response.request().postDataJSON();
  check(`browser_indexing_${kind}_explicit_retry`, response.status() === 200 && sent.expectedGeneration === before.executionGeneration);
  const after = await currentIndex(page, row.materialId, state => state.state === 'SUCCEEDED' && state.readable === true && state.activeCurrent === true);
  await readyUi(page, row.materialId);
  check(`browser_indexing_${kind}_recovered_same_job`, after.jobId === before.jobId && after.sourceRevision === before.sourceRevision && after.executionGeneration === before.executionGeneration + 1);
  observations.push({ case: kind, jobId: after.jobId, sourceRevision: after.sourceRevision, beforeGeneration: before.executionGeneration,
    afterGeneration: after.executionGeneration, beforeReadable: before.readable, afterReadable: after.readable });
}
try {
  const manifestPath = process.env.DODREAM_INDEX_BROWSER_PLAN;
  if (!manifestPath) throw new Error('Synthetic UI plan required');
  const allowedDirectory = await fs.realpath(path.join(root, '.local/phase4/browser-ui'));
  const realPlan = await fs.realpath(manifestPath);
  assert.ok(realPlan.startsWith(allowedDirectory + path.sep));
  plan = JSON.parse(await fs.readFile(realPlan, 'utf8'));
  assert.match(plan.runId, uuid);
  const titles = [plan.publishTitle, plan.firstFailureTitle, plan.reindexFailureTitle];
  assert.equal(new Set(titles).size, 3);
  assert.ok(titles.every(title => typeof title === 'string' && title.startsWith('[INDEXING LOCAL] ')));
  handshakeDirectory = path.dirname(realPlan);
  for (const event of ['published', 'processing', 'complete']) {
    await assert.rejects(fs.stat(path.join(handshakeDirectory, `${plan.runId}.${event}.json`)), { code: 'ENOENT' });
  }
  handshakeAccepted = true;
  const env = Object.fromEntries((await fs.readFile(path.join(root, '.local/env'), 'utf8')).split('\n')
    .filter(line => line && !line.startsWith('#')).map(line => { const at = line.indexOf('='); return [line.slice(0, at), line.slice(at + 1)]; }));
  let playwright;
  try { playwright = require('playwright'); }
  catch { playwright = require(process.env.DODREAM_PLAYWRIGHT_PATH || '/Users/yoonsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'); }
  step = 'launch isolated Chrome';
  browser = await playwright.chromium.launch({ executablePath: process.env.DODREAM_CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true, args: ['--disable-background-networking', '--disable-component-update', '--disable-sync', '--no-first-run'] });
  if (interrupted) throw new Error('Owning runner stopped launch');
  const { context, page } = await contextPage();
  try {
    step = 'teacher UI login and new synthetic fixture lookup';
    await page.goto(origin); await page.getByText('로그인 하기', { exact: true }).click();
    await page.locator('form.sign-in input[name="email"]').fill('authz-owner@local.dodream.invalid');
    await page.locator('form.sign-in input[name="password"]').fill(env.LOCAL_TEACHER_PASSWORD);
    const loggedIn = page.waitForResponse(response => response.url().endsWith('/api/auth/teacher/login'));
    await page.locator('form.sign-in button[type="submit"]').click();
    assert.equal((await loggedIn).status(), 200); await page.waitForURL('**/classrooms');
    await page.locator('.swal2-container').waitFor({ state: 'hidden' });
    const rows = await page.evaluate(async () => {
      const response = await fetch('/api/documents/published', { headers: { Authorization: 'Bearer ' + localStorage.getItem('accessToken') } });
      if (!response.ok) throw new Error('Synthetic material listing unavailable');
      return (await response.json()).materials.map(row => ({ materialId: row.materialId, uploadedFileId: row.uploadedFileId, title: row.title }));
    });
    const [publish, firstFailure, reindexFailure] = titles.map(title => rows.find(row => row.title === title));
    assert.ok([publish, firstFailure, reindexFailure].every(row => Number.isSafeInteger(row?.materialId) && row.materialId > 0 && Number.isSafeInteger(row?.uploadedFileId)));
    assert.equal(new Set([publish.materialId, firstFailure.materialId, reindexFailure.materialId]).size, 3);
    step = 'actual teacher editor publication';
    await page.getByRole('heading', { name: plan.publishTitle, exact: true }).click(); await page.waitForURL('**/editor');
    await page.locator('.tiptap[contenteditable="true"]').first().fill('[INDEX LOCAL] 합성 브라우저 색인 상태 검증. 저장된 새 원본의 검증된 색인만 사용합니다.');
    const publication = page.waitForResponse(response => response.url().endsWith(`/api/documents/${publish.uploadedFileId}/publish`) && response.request().method() === 'POST');
    await page.getByRole('button', { name: '수정하기', exact: true }).click();
    const response = await publication; const receipt = await response.json(); const queued = receipt.indexing;
    check('browser_indexing_publication_accepted', response.status() === 200 && uuid.test(queued?.jobId) && queued.state === 'QUEUED' && queued.readable === false && queued.activeCurrent === false);
    await page.getByRole('heading', { name: '수정이 접수되었습니다', exact: true }).waitFor();
    const receiptText = await page.locator('.swal2-container').innerText();
    check('browser_indexing_receipt_does_not_claim_ready', receiptText.includes('발행 접수') && !receiptText.includes('사용 가능'));
    await checkpoint('published', { materialId: publish.materialId, jobId: queued.jobId, sourceRevision: queued.sourceRevision, state: queued.state });
    await page.locator('.swal2-confirm').click(); await page.waitForURL('**/classrooms');
    step = 'actual worker PROCESSING gate observed in teacher list';
    const processing = await currentIndex(page, publish.materialId, state => state.jobId === queued.jobId && state.state === 'PROCESSING');
    const panel = indexPanel(page, publish.materialId);
    await panel.getByRole('status').filter({ hasText: /^색인 준비 중$/ }).waitFor();
    check('browser_indexing_processing_ui_matches_server', processing.readable === false && processing.activeCurrent === false);
    await checkpoint('processing', { materialId: publish.materialId, jobId: processing.jobId, sourceRevision: processing.sourceRevision, state: processing.state });
    step = 'actual candidate activation becomes available';
    const available = await currentIndex(page, publish.materialId, state => state.jobId === queued.jobId && state.state === 'SUCCEEDED' && state.activeCurrent === true && state.readable === true);
    await readyUi(page, publish.materialId);
    check('browser_indexing_validated_activation_visible', available.sourceRevision === queued.sourceRevision);
    completedActivation = { jobId: available.jobId, sourceRevision: available.sourceRevision, executionGeneration: available.executionGeneration };
    await page.reload(); await materialRow(page, plan.publishTitle).waitFor();
    check('browser_indexing_available_survives_reload', await indexPanel(page, publish.materialId).getByRole('status').innerText() === '사용 가능');
    step = 'first index failure and explicit UI recovery';
    await recoverThroughUi(page, firstFailure, 'first_failure', false);
    step = 'same-source failure preserves availability and explicit UI recovery';
    await recoverThroughUi(page, reindexFailure, 'reindex_failure', true);
    step = 'teacher UI logout';
    await page.getByRole('button', { name: '로그아웃', exact: true }).click();
    const loggedOut = page.waitForResponse(response => response.url().endsWith('/api/auth/teacher/logout'));
    await page.getByRole('button', { name: '로그아웃', exact: true }).last().click();
    check('browser_indexing_test_session_revoked', (await loggedOut).status() === 200);
  } finally { await context.close(); }
} catch (error) {
  if (!error.recorded) {
    const row = { name: 'browser_indexing_execution', status: browser ? 'FAIL' : 'BLOCKED', detail: { error: error.name, step } };
    checks.push(row); console.log(JSON.stringify(row));
  }
} finally {
  const version = browser?.version() || 'unavailable'; if (browser) await browser.close();
  if (interrupted && !checks.some(row => row.status !== 'PASS')) checks.push({ name: 'browser_indexing_interrupted', status: 'FAIL', detail: 'Owning runner stopped its child' });
  const counts = Object.fromEntries(['PASS', 'FAIL', 'BLOCKED'].map(status => [status, checks.filter(row => row.status === status).length]));
  const exitCode = checks.some(row => row.status !== 'PASS') ? 1 : 0;
  const report = { browser: 'Chrome ' + version, origin, mode: 'ACTUAL_TEACHER_UI_REAL_INDEXING_SERVICES',
    nativeDeviceExecution: 'NOT_RUN', externalRequestsBlocked, checks, counts, activation: completedActivation, recoveries: observations };
  const output = path.join(root, '.local/phase4/results/browser-indexing-checks.json');
  await fs.mkdir(path.dirname(output), { recursive: true });
  const content = JSON.stringify(report, null, 2) + '\n';
  await fs.writeFile(output, content); await fs.writeFile(output.replace('.json', '-' + Date.now() + '.json'), content);
  await checkpoint('complete', { counts, exitCode });
  console.log(JSON.stringify({ counts, evidence: output })); process.exitCode = exitCode;
}

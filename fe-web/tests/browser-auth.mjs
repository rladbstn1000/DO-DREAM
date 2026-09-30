/** Real Chrome + real local Spring/Redis. No trace/HAR/screenshots or credential output. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';

const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const origin = process.env.DODREAM_AUTH_BROWSER_ORIGIN || 'http://127.0.0.1:15174';
if (!['127.0.0.1', 'localhost'].includes(new URL(origin).hostname) || new URL(origin).protocol !== 'http:') throw new Error('Only loopback HTTP test origins allowed');
const env = Object.fromEntries((await fs.readFile(path.join(root, '.local/env'), 'utf8')).split('\n').filter(line => line && !line.startsWith('#')).map(line => { const i = line.indexOf('='); return [line.slice(0, i), line.slice(i + 1)]; }));
const password = env.LOCAL_TEACHER_PASSWORD;
if (!password) throw new Error('Generated local teacher credential unavailable');
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require(process.env.DODREAM_PLAYWRIGHT_PATH || '/Users/yoonsu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'); }
const checks = [];
const check = (name, passed, detail = '') => {
  const entry = { name, status: passed ? 'PASS' : 'FAIL', detail };
  checks.push(entry); console.log(JSON.stringify(entry));
  if (!passed) throw new Error('Assertion failed: ' + name);
};
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const within = (promise, ms = 15000) => {
  let timer;
  return Promise.race([promise, new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error('Browser coordination timed out')), ms);
  })]).finally(() => clearTimeout(timer));
};
let browser;
let blockedExternal = 0;
async function fresh() {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { blockedExternal++; return route.abort(); }
    return route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  let refreshes = 0; let logouts = 0; let expiredRequests = 0; let protectedSuccesses = 0;
  page.on('request', request => {
    if (request.url().endsWith('/api/auth/teacher/refresh')) refreshes++;
    if (request.url().endsWith('/api/auth/teacher/logout')) logouts++;
  });
  page.on('response', response => {
    if (/\/api\/(documents|classes|students)\//.test(response.url())) {
      if (response.status() === 401) expiredRequests++;
      if (response.status() === 200) protectedSuccesses++;
    }
  });
  await page.goto(origin);
  await page.getByText('로그인 하기', { exact: true }).click();
  await page.locator('form.sign-in input[name="email"]').fill('teacher@local.dodream.invalid');
  await page.locator('form.sign-in input[name="password"]').fill(password);
  const loginResponse = page.waitForResponse(r => r.url().endsWith('/api/auth/teacher/login'));
  await page.locator('form.sign-in button[type="submit"]').click();
  const response = await loginResponse;
  if (response.status() !== 200) throw Object.assign(new Error('Login unavailable'), { observation: { stage: 'login', status: response.status() } });
  assert.equal(Object.hasOwn(await response.json(), 'refreshToken'), false);
  await page.waitForURL('**/classrooms');
  await page.waitForLoadState('networkidle');
  // Let the existing login toast close before interacting with the underlying UI.
  await page.locator('.swal2-container').waitFor({ state: 'hidden' }).catch(() => {});
  assert.ok(protectedSuccesses >= 2, 'Login must reach two real protected API responses');
  return { context, page, counts: () => ({ refreshes, logouts, expiredRequests, protectedSuccesses }) };
}
async function run(name, action) {
  try { await action(); }
  catch (error) {
    if (!checks.some(row => row.name === name && row.status === 'FAIL')) {
      checks.push({ name, status: 'FAIL', detail: error.observation ?? error.name });
      console.log(JSON.stringify(checks.at(-1)));
    }
    if (name === 'browser_login_cookie_csrf_logout') throw error;
  }
}
async function enterClassroomBeforeExpiry(page, counts) {
  // A full reload now verifies /api/session/me before mounting teacher screens,
  // so it refreshes serially and no longer creates the old concurrent-401 race.
  // Real SPA navigation keeps that verified provider mounted. Returning through
  // the existing button remounts ClassroomList's independent document/class
  // fetch effects with the same expired AT and the actual shared auth client.
  await page.locator('.cl-classroom-card').first().click();
  await page.waitForURL(/\/classroom\/[1-9][0-9]*$/);
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: '목록으로', exact: true }).waitFor();
  assert.equal(counts().refreshes, 0, 'Classroom entry must finish before the short AT expires');
}
try {
  browser = await playwright.chromium.launch({
    executablePath: process.env.DODREAM_CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--disable-background-networking', '--disable-component-update', '--disable-sync', '--no-first-run'],
  });
  await run('browser_login_cookie_csrf_logout', async () => {
    const { context, page, counts } = await fresh();
    try {
      check('browser_ui_login_and_protected_page', page.url() === origin + '/classrooms' && counts().protectedSuccesses >= 2, JSON.stringify(counts()));
      const ttl = await page.evaluate(() => { const data = JSON.parse(atob(localStorage.getItem('accessToken').split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))); return data.exp - data.iat; });
      check('browser_short_at_test_profile', ttl === 2, 'observed lifetime=' + ttl + ' seconds');
      const cookies = await context.cookies();
      const refresh = cookies.find(c => c.name === 'refresh');
      check('browser_refresh_cookie_attributes', !!refresh && refresh.httpOnly && !refresh.secure && refresh.sameSite === 'Lax' && refresh.path === '/api/auth');
      const csrfCookie = cookies.find(c => c.name === 'XSRF-TOKEN');
      check('browser_csrf_cookie_attributes', !!csrfCookie && csrfCookie.httpOnly && !csrfCookie.secure && csrfCookie.sameSite === 'Lax' && csrfCookie.path === '/api/auth');
      check('browser_refresh_cookie_hidden_from_javascript', await page.evaluate(() => !document.cookie.split(';').some(c => c.trim().startsWith('refresh='))));
      const missing = await page.evaluate(async () => (await fetch('/api/auth/teacher/refresh', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: '{}' })).status);
      check('browser_cookie_post_without_csrf_denied', missing === 403, 'HTTP ' + missing);
      const incorrect = await page.evaluate(async () => (await fetch('/api/auth/teacher/refresh', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-XSRF-TOKEN': 'incorrect-synthetic-csrf' }, body: '{}' })).status);
      check('browser_cookie_post_wrong_csrf_denied', incorrect === 403, 'HTTP ' + incorrect);
      await delay(8000); // 2-second test AT plus documented 5-second clock skew.
      const renewed = await page.evaluate(async () => {
        const csrf = await (await fetch('/api/auth/csrf', { credentials: 'include' })).json();
        const response = await fetch('/api/auth/teacher/refresh', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', [csrf.headerName]: csrf.token, Authorization: 'Bearer ' + localStorage.getItem('accessToken') }, body: '{}' });
        const data = await response.json();
        if (response.ok) localStorage.setItem('accessToken', data.accessToken);
        return { status: response.status, hasAccess: typeof data.accessToken === 'string', hasRefresh: Object.hasOwn(data, 'refreshToken') };
      });
      check('browser_expired_at_and_valid_cookie_refresh', renewed.status === 200 && renewed.hasAccess && !renewed.hasRefresh, 'HTTP ' + renewed.status);
      await page.getByRole('button', { name: '로그아웃', exact: true }).click();
      const ended = page.waitForResponse(r => r.url().endsWith('/api/auth/teacher/logout'));
      await page.getByRole('button', { name: '로그아웃', exact: true }).last().click();
      assert.equal((await ended).status(), 200);
      await page.waitForURL(origin + '/');
      check('browser_logout_once_and_cookie_deleted', counts().logouts === 1 && !(await context.cookies()).some(c => c.name === 'refresh'));
      check('browser_logout_clears_local_state', await page.evaluate(() => !localStorage.getItem('accessToken') && !localStorage.getItem('isLoggedIn')));
    } finally { await context.close(); }
  });
  await run('browser_concurrent_expiration', async () => {
    const { context, page, counts } = await fresh();
    try {
      await enterClassroomBeforeExpiry(page, counts);
      await delay(8000);
      // SPA navigation does not reset the document's load-state history.
      // Register the actual expired/replayed responses before the UI action,
      // then wait for both independent requests and their single refresh.
      const responses = Promise.all([
        ['/api/documents/published', 401], ['/api/classes/teacher', 401],
        ['/api/auth/teacher/refresh', 200],
        ['/api/documents/published', 200], ['/api/classes/teacher', 200],
      ].map(([suffix, status]) => page.waitForResponse(r => r.url().endsWith(suffix) && r.status() === status)));
      await page.getByRole('button', { name: '목록으로', exact: true }).click();
      await page.waitForURL('**/classrooms');
      await responses;
      check('browser_concurrent_expiration_single_refresh', counts().expiredRequests >= 2 && counts().refreshes === 1, JSON.stringify(counts()));
      const status = await page.evaluate(async () => (await fetch('/api/teacher/me', { headers: { Authorization: 'Bearer ' + localStorage.getItem('accessToken') } })).status);
      check('browser_refreshed_protected_api_success', status === 200 && page.url().endsWith('/classrooms'), 'HTTP ' + status);
    } finally { await context.close(); }
  });
  await run('browser_late_401_reuses_refreshed_token', async () => {
    const { context, page, counts } = await fresh();
    try {
      await enterClassroomBeforeExpiry(page, counts);
      await delay(8000);
      let release; const gate = new Promise(resolve => { release = resolve; });
      let intercepted = false;
      await page.route('**/api/documents/published', async route => {
        if (intercepted) return route.continue();
        intercepted = true;
        const response = await route.fetch();
        assert.equal(response.status(), 401, 'The delayed document response must be a real expired-AT rejection');
        await gate;
        await route.fulfill({ response });
      });
      const refreshed = page.waitForResponse(r => r.url().endsWith('/api/auth/teacher/refresh') && r.status() === 200);
      const replayedClass = page.waitForResponse(r => r.url().endsWith('/api/classes/teacher') && r.status() === 200);
      await page.getByRole('button', { name: '목록으로', exact: true }).click();
      await refreshed;
      // The successful class replay proves the client saved and used the new AT
      // before the older document 401 reaches that same client.
      await replayedClass;
      release();
      await page.waitForLoadState('networkidle');
      check('browser_late_401_no_second_refresh', counts().refreshes === 1 && await page.evaluate(() => !!localStorage.getItem('accessToken')), JSON.stringify(counts()));
    } finally { await context.close(); }
  });
  await run('browser_403_does_not_refresh', async () => {
    const { context, page, counts } = await fresh();
    try {
      let injected = 0;
      await page.route('**/api/documents/published', route => { injected++; return route.fulfill({ status: 403, contentType: 'application/json', body: '{}' }); });
      await page.reload(); await page.waitForLoadState('networkidle');
      check('browser_403_preserves_session_without_refresh', injected === 1 && counts().refreshes === 0 && await page.evaluate(() => !!localStorage.getItem('accessToken')), '403 response injected at browser transport; requests=' + injected);
    } finally { await context.close(); }
  });
  await run('browser_refresh_failure', async () => {
    const { context, page, counts } = await fresh();
    try {
      await page.route('**/api/auth/teacher/refresh', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
      await delay(8000); await page.reload();
      await page.waitForURL(origin + '/'); await delay(500);
      check('browser_refresh_failure_no_loop_and_login_guidance', counts().refreshes === 1 && await page.evaluate(() => !localStorage.getItem('accessToken')), '503 injected at browser transport; ' + JSON.stringify(counts()));
    } finally { await context.close(); }
  });
  await run('browser_logout_refresh_race', async () => {
    const { context, page, counts } = await fresh();
    try {
      await enterClassroomBeforeExpiry(page, counts);
      await delay(8000);
      let arrived; const seen = new Promise(resolve => { arrived = resolve; });
      let release; const gate = new Promise(resolve => { release = resolve; });
      await page.route('**/api/auth/teacher/refresh', async route => {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        arrived(); await gate;
        await route.fulfill({ response }).catch(() => {}); // logout may abort delivery.
      });
      await page.getByRole('button', { name: '목록으로', exact: true }).click(); await within(seen);
      await page.getByRole('button', { name: '로그아웃', exact: true }).click();
      const ended = page.waitForResponse(r => r.url().endsWith('/api/auth/teacher/logout'));
      await page.getByRole('button', { name: '로그아웃', exact: true }).last().click();
      assert.equal((await ended).status(), 200);
      release(); await delay(500);
      check('browser_logout_during_refresh_no_resurrection', counts().logouts === 1 && await page.evaluate(() => !localStorage.getItem('accessToken') && !localStorage.getItem('isLoggedIn')));
      await page.unroute('**/api/auth/teacher/refresh');
      const status = await page.evaluate(async () => {
        const csrf = await (await fetch('/api/auth/csrf', { credentials: 'include' })).json();
        return (await fetch('/api/auth/teacher/refresh', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', [csrf.headerName]: csrf.token }, body: '{}' })).status;
      });
      check('browser_late_cookie_cannot_revive_server_session', status === 401, 'HTTP ' + status);
    } finally { await context.close(); }
  });
} catch (error) {
  if (!checks.some(row => row.status === 'FAIL')) checks.push({ name: 'browser_execution', status: browser ? 'FAIL' : 'BLOCKED', detail: error.name });
} finally {
  const version = browser ? browser.version() : 'unavailable';
  if (browser) await browser.close();
  const report = { browser: 'Chrome ' + version, origin, checks, externalRequestsBlocked: blockedExternal,
    nativeDeviceExecution: 'NOT_RUN', counts: Object.fromEntries(['PASS', 'FAIL', 'BLOCKED'].map(status => [status, checks.filter(row => row.status === status).length])) };
  const output = path.join(root, '.local/phase4/results/browser-checks.json');
  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n');
  await fs.writeFile(output.replace('.json', '-' + Date.now() + '.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ counts: report.counts, evidence: output }));
  process.exitCode = checks.some(row => row.status !== 'PASS') ? 1 : 0;
}

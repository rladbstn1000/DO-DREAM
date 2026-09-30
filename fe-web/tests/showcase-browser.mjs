/** Real Chrome against the built static artifact. No API mocks, backend, or user browser profile. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';
import { startShowcaseServer } from '../scripts/showcase-server.mjs';

const repository = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const artifact = path.join(repository, 'fe-web/dist-showcase');
const evidence = path.join(repository, '.local/static-showcase/results');
const stamp = new Date().toISOString().replaceAll(':', '').replaceAll('.', '');
const captureDirectory = path.join(evidence, `browser-${stamp}`);
const storageKey = 'dodream.showcase.v1.state';
const sentinel = 'SHOWCASE_AUTH_SENTINEL_NOT_A_TOKEN';
const syntheticDocumentQuery = '?mode=live&role=TEACHER&api=http%3A%2F%2F127.0.0.1%3A8080';
const malicious = '<img src="https://showcase-forbidden.invalid/pixel" onerror="window.__showcaseExecuted=true"> javascript:alert(1)';
const checks = [], network = { staticRequests: [], forbiddenRequests: [], apiAttempts: [], socketAttempts: [], cspViolations: [] };
const browserErrors = [], screenshots = [], speechObservations = [];
const startedAt = Date.now();
let server, browser, browserVersion, step = 'launch', artifactDigestBefore, sourceDigestBefore;

async function filesBelow(directory, prefix = '') {
  const entries = await fs.readdir(directory, { withFileTypes: true });
  const result = [];
  for (const entry of entries) {
    assert.ok(!entry.isSymbolicLink(), 'static artifact must not contain symlinks');
    const relative = prefix + entry.name;
    if (entry.isDirectory()) result.push(...await filesBelow(path.join(directory, entry.name), relative + '/'));
    else if (entry.isFile()) result.push(relative);
  }
  return result.sort();
}
async function digestFiles(directory) {
  const { createHash } = await import('node:crypto');
  const hash = createHash('sha256');
  for (const file of await filesBelow(directory)) hash.update(file).update('\0').update(await fs.readFile(path.join(directory, file))).update('\0');
  return hash.digest('hex');
}
function check(name, condition, category = 'ACTUAL_UI', details) {
  checks.push({ name, category, status: condition ? 'PASS' : 'FAIL', ...(details === undefined ? {} : { details }) });
  assert.ok(condition, name);
}
async function textShown(page, phrase) { await page.getByText(phrase, { exact: false }).first().waitFor(); }
async function heading(page, name) { await page.getByRole('heading', { name, exact: true }).waitFor(); }
async function capture(page, name) {
  const file = path.join(captureDirectory, name + '.png');
  await page.screenshot({ path: file, fullPage: true, animations: 'disabled' });
  screenshots.push(path.relative(repository, file));
}
async function stored(page) { return page.evaluate(key => JSON.parse(sessionStorage.getItem(key) || 'null'), storageKey); }
function submissions(state, sample = 'water-journey') { return state?.samples?.[sample]?.submissions ?? []; }
async function navigate(page, prefix, route) { await page.goto(server.origin + prefix + '#' + route); }

// APIs stay native. Instrumentation records attempts before CSP/route guards can reject them.
// The only fake platform below is the separately labelled speech-event probe.
async function newContext(label, options = {}) {
  const context = await browser.newContext({ serviceWorkers: 'block', viewport: options.viewport ?? { width: 1280, height: 920 }, reducedMotion: 'reduce' });
  await context.exposeBinding('__recordShowcaseAttempt', (_source, attempt) => network.apiAttempts.push({ context: label, ...attempt }));
  await context.exposeBinding('__recordShowcaseCsp', (_source, attempt) => network.cspViolations.push({ context: label, ...attempt }));
  await context.addInitScript(({ origin, label, storageKey, sentinel, state, storageUnavailable, speech }) => {
    if (location.origin !== origin) return;
    const record = (api, url) => void window.__recordShowcaseAttempt({ api, url: String(url ?? ''), page: location.href });
    const nativeFetch = window.fetch;
    window.fetch = function (input, init) { record('fetch', typeof input === 'string' ? input : input?.url); return nativeFetch.call(this, input, init); };
    const nativeOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url, ...rest) { record('XMLHttpRequest', url); return nativeOpen.call(this, method, url, ...rest); };
    for (const name of ['WebSocket', 'EventSource']) {
      const Original = window[name];
      if (Original) window[name] = class extends Original { constructor(url, ...args) { record(name, url); super(url, ...args); } };
    }
    const nativeBeacon = navigator.sendBeacon?.bind(navigator);
    if (nativeBeacon) navigator.sendBeacon = (url, data) => { record('sendBeacon', url); return nativeBeacon(url, data); };
    if (navigator.serviceWorker) {
      const nativeRegister = navigator.serviceWorker.register.bind(navigator.serviceWorker);
      navigator.serviceWorker.register = (url, options) => { record('serviceWorker.register', url); return nativeRegister(url, options); };
    }
    document.addEventListener('securitypolicyviolation', event => {
      void window.__recordShowcaseCsp({ directive: event.violatedDirective, blockedURI: event.blockedURI, page: location.href });
    });
    window.__showcaseExecuted = false;
    for (const storage of [localStorage, sessionStorage]) {
      for (const [key, value] of Object.entries({ accessToken: sentinel, refreshToken: sentinel, isLoggedIn: 'true', role: 'TEACHER', 'dodream.auth.pending': sentinel, unrelated: 'KEEP_' + label })) storage.setItem(key, value);
    }
    if (state !== undefined && !sessionStorage.getItem('__showcase_test_seeded')) {
      sessionStorage.setItem(storageKey, state);
      sessionStorage.setItem('__showcase_test_seeded', 'true');
    }
    if (storageUnavailable) Object.defineProperty(window, 'sessionStorage', { configurable: true, get() { throw new DOMException('Synthetic storage denial', 'SecurityError'); } });
    if (speech) {
      const events = { utterances: [], canceled: 0, paused: 0, resumed: 0, listeners: new Set() };
      const voices = speech === 'local' ? [{ name: 'Synthetic local Korean event engine', lang: 'ko-KR', localService: true }] : [{ name: 'Synthetic remote voice', lang: 'ko-KR', localService: false }];
      class SyntheticUtterance { constructor(text) { this.text = text; this.onend = null; this.onerror = null; } }
      Object.defineProperty(window, 'SpeechSynthesisUtterance', { configurable: true, value: SyntheticUtterance });
      Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
        getVoices: () => { if (speech === 'voices-throw') throw new Error('Synthetic voice enumeration failure'); return voices; }, speak: utterance => events.utterances.push(utterance),
        cancel: () => { events.canceled++; }, pause: () => { events.paused++; }, resume: () => { events.resumed++; },
        addEventListener: (_type, listener) => events.listeners.add(listener), removeEventListener: (_type, listener) => events.listeners.delete(listener),
      } });
      window.__showcaseSpeech = events;
    }
  }, { origin: server.origin, label, storageKey, sentinel, state: options.state, storageUnavailable: !!options.storageUnavailable, speech: options.speech });
  const allowedFiles = new Set(await filesBelow(artifact));
  const staticAllowed = raw => {
    const url = new URL(raw);
    if (url.origin !== server.origin) return false;
    let pathname = decodeURIComponent(url.pathname);
    if (pathname.startsWith('/DO-DREAM/')) pathname = pathname.slice('/DO-DREAM/'.length);
    else if (pathname.startsWith('/')) pathname = pathname.slice(1);
    if (url.search && !(url.search === syntheticDocumentQuery && (pathname === '' || pathname === 'index.html'))) return false;
    return pathname === '' || allowedFiles.has(pathname);
  };
  await context.route('**/*', route => {
    const request = route.request();
    const item = { context: label, url: request.url(), resourceType: request.resourceType(), method: request.method() };
    if (request.method() === 'GET' && staticAllowed(request.url())) { network.staticRequests.push(item); return route.continue(); }
    network.forbiddenRequests.push(item);
    return route.abort('blockedbyclient');
  });
  if (context.routeWebSocket) await context.routeWebSocket('**/*', socket => {
    network.socketAttempts.push({ context: label, url: socket.url() }); socket.close();
  });
  context.on('page', page => {
    page.on('pageerror', error => browserErrors.push({ context: label, type: error.name, message: error.message }));
    page.on('websocket', socket => network.socketAttempts.push({ context: label, url: socket.url() }));
    page.on('response', response => { if (response.status() >= 400) browserErrors.push({ context: label, type: 'HTTP_ERROR', status: response.status(), url: response.url() }); });
  });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  return { context, page };
}
async function assertNoOverflow(page, name) {
  const layout = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth,
    clipped: [...document.querySelectorAll('main button, main input, main textarea, main select, main p, main blockquote')].filter(element => {
      const box = element.getBoundingClientRect(); const style = getComputedStyle(element);
      return box.width > 0 && style.display !== 'none' && (box.left < -1 || box.right > innerWidth + 1);
    }).map(element => element.tagName + ':' + element.textContent?.slice(0, 30)) }));
  check(name, layout.scroll <= layout.width + 1 && layout.clipped.length === 0, 'LAYOUT_320_OR_DESKTOP', layout);
}
async function answerQuiz(page) {
  await page.locator('input[type=radio][value=ice]').check();
  await page.locator('input[type=radio][value=evaporate]').check();
}
async function normalJourney(prefix, screenshotsEnabled) {
  const label = prefix === '/' ? 'root' : 'subpath';
  const { context, page } = await newContext(label);
  step = label + ': start and library';
  await page.goto(server.origin + prefix + syntheticDocumentQuery + '#/?mode=live&role=TEACHER&api=http://127.0.0.1:8080');
  await page.getByRole('link', { name: '학생 체험 시작', exact: true }).waitFor();
  await textShown(page, '포트폴리오 체험용 데모');
  check(label + ': no credentials required', await page.locator('input[type=password]').count() === 0);
  check(label + ': outer and hash mode/role queries retain explicit sample UI', new URL(page.url()).searchParams.get('mode') === 'live'
    && await page.getByText('샘플 체험', { exact: true }).count() > 0, 'MODE_ISOLATION');
  if (screenshotsEnabled) {
    await capture(page, '01-start');
    await page.setViewportSize({ width: 320, height: 780 });
    await assertNoOverflow(page, label + ': 320px start');
    await page.setViewportSize({ width: 1280, height: 920 });
  }
  await page.getByRole('link', { name: '학생 체험 시작', exact: true }).click();
  await page.getByTestId('material-water-journey').click();
  await page.locator('.learn-reading-text').waitFor();
  check(label + ': readable authored material', (await page.locator('.learn-reading-text').innerText()).length > 50);
  await page.getByRole('button', { name: '아주 큰 글자', exact: true }).click();
  check(label + ': font size changes safely', await page.locator('.learn-reading-text').evaluate(element => getComputedStyle(element).fontSize) === '26px');
  await page.getByRole('button', { name: '기본 글자', exact: true }).click();
  await page.getByRole('button', { name: '다음 단원', exact: true }).click();
  check(label + ': section URL', page.url().includes('section=water-2'));
  await page.reload();
  await page.locator('.learn-reading-text').waitFor();
  check(label + ': direct section refresh', page.url().includes('section=water-2'));
  await page.goBack();
  await page.locator('.learn-reading-text').waitFor();
  check(label + ': browser back preserves hash route', page.url().includes('/learn/water-journey'));
  step = label + ': prepared answer and source dialog';
  await page.getByTestId('recommended-question-water-ice').click();
  await textShown(page, '준비된 답변');
  await page.getByTestId('sample-answer').first().waitFor();
  const sourceButton = page.getByRole('button', { name: '참고 구간 보기', exact: true }).first();
  await sourceButton.click();
  await page.locator('dialog[open] blockquote').waitFor();
  check(label + ': source is the authored sample text', await page.locator('dialog[open] blockquote').innerText() === '물이 충분히 차가워지면 단단한 얼음이 됩니다. 얼음을 따뜻한 곳에 두면 다시 물이 됩니다.');
  if (screenshotsEnabled) {
    await capture(page, '02-student-answer-reference');
    await page.setViewportSize({ width: 320, height: 780 });
    await assertNoOverflow(page, label + ': 320px reference dialog');
    await page.setViewportSize({ width: 1280, height: 920 });
  }
  await page.keyboard.press('Escape');
  await page.locator('dialog[open]').waitFor({ state: 'hidden' });
  check(label + ': modal returns focus', await sourceButton.evaluate(element => document.activeElement === element), 'KEYBOARD');
  await sourceButton.click();
  await page.getByRole('button', { name: '이 단원으로 이동', exact: true }).click();
  await page.locator('dialog[open]').waitFor({ state: 'hidden' });
  check(label + ': reference link stays within public sample', page.url().includes('/learn/water-journey') && page.url().includes('section=water-1'));
  await page.getByLabel('질문', { exact: true }).fill(malicious);
  await page.getByRole('button', { name: '질문 보내기', exact: true }).click();
  await textShown(page, '이 질문에는 준비된 답변이 없습니다. 아래 추천 질문 중 하나를 선택해주세요.');
  check(label + ': unsupported HTML/URL remains inert', !await page.evaluate(() => window.__showcaseExecuted)
    && await page.locator('img[src*="showcase-forbidden"], a[href^="javascript:"]').count() === 0, 'INPUT_BOUNDARY');
  const answerCount = await page.locator('[data-testid="sample-answer"]').count();
  check(label + ': unsupported question creates no fabricated answer', answerCount === 0, 'INPUT_BOUNDARY');
  await page.getByLabel('질문', { exact: true }).fill('젖은 수건이 마르는 까닭은 무엇인가요?');
  await page.getByRole('button', { name: '질문 보내기', exact: true }).click();
  await page.getByTestId('sample-answer').filter({ hasText: '수건 속 물이 수증기가 되어' }).waitFor();
  check(label + ': supported exact question gets its prepared answer', true);
  step = label + ': deterministic quiz and result';
  await page.getByRole('link', { name: '퀴즈 풀기', exact: true }).click();
  await answerQuiz(page);
  // Two native DOM activations in the same event turn model a duplicate submit intent.
  await page.getByRole('button', { name: '제출하기', exact: true }).evaluate(button => { button.click(); button.click(); });
  await heading(page, '체험 결과');
  check(label + ': duplicate submit has one result', submissions(await stored(page)).length === 1, 'STATE');
  check(label + ': deterministic result ID', page.url().endsWith('/results/run-1'), 'STATE');
  await page.reload();
  await heading(page, '체험 결과');
  check(label + ': result survives same-tab refresh', submissions(await stored(page)).length === 1, 'STATE');
  if (screenshotsEnabled) {
    await capture(page, '03-quiz-result');
    await page.setViewportSize({ width: 320, height: 780 });
    await assertNoOverflow(page, label + ': 320px result');
    await page.setViewportSize({ width: 1280, height: 920 });
  }
  await page.getByRole('link', { name: '교사 화면 보기', exact: true }).click();
  await heading(page, '교사 샘플 화면');
  await textShown(page, '같은 탭');
  check(label + ': teacher can see same-tab result', await page.getByTestId('teacher-results').innerText().then(text => text.includes('물') && text.includes('2')), 'STATE');
  if (screenshotsEnabled) await capture(page, '04-teacher-result');
  const isolated = await newContext(label + '-independent');
  await navigate(isolated.page, prefix, '/learn/water-journey/results/run-1');
  await textShown(isolated.page, '먼저');
  check(label + ': independent context has no first context result', submissions(await stored(isolated.page)).length === 0, 'STATE');
  await isolated.context.close();
  await navigate(page, prefix, '/learn/recycling-day/results/run-1');
  await textShown(page, '이 탭에 저장된 풀이 결과가 없습니다. 먼저 퀴즈를 풀어주세요.');
  check(label + ': one sample result cannot satisfy another sample URL', await page.getByTestId('result-attempt').count() === 0
    && submissions(await stored(page)).length === 1 && submissions(await stored(page), 'recycling-day').length === 0, 'STATE');
  step = label + ': explicit retry and reset';
  await navigate(page, prefix, '/learn/water-journey/results/run-1');
  await page.getByRole('button', { name: '다시 풀기', exact: true }).click();
  await answerQuiz(page);
  await page.getByRole('button', { name: '제출하기', exact: true }).click();
  await heading(page, '체험 결과');
  check(label + ': explicit retry is a new result', page.url().endsWith('/results/run-2') && submissions(await stored(page)).length === 2, 'STATE');
  await page.getByRole('button', { name: '데모 초기화', exact: true }).click();
  await page.getByRole('link', { name: '학생 체험 시작', exact: true }).waitFor();
  const resetState = await page.evaluate(({ storageKey, sentinel, label }) => ({ owned: sessionStorage.getItem(storageKey),
    other: [localStorage, sessionStorage].every(storage => storage.getItem('accessToken') === sentinel && storage.getItem('unrelated') === 'KEEP_' + label) }), { storageKey, sentinel, label });
  check(label + ': reset removes only owned state', resetState.owned === null && resetState.other, 'STATE', resetState);
  await navigate(page, prefix, '/learn/not-a-public-sample');
  await heading(page, '샘플 교재를 찾을 수 없어요');
  check(label + ': unknown material has no body', await page.locator('.learn-reading-text').count() === 0, 'INPUT_BOUNDARY');
  await navigate(page, prefix, '/learn/' + encodeURIComponent(malicious));
  await heading(page, '샘플 교재를 찾을 수 없어요');
  check(label + ': malicious route ID is not rendered as HTML or a link', !await page.evaluate(() => window.__showcaseExecuted)
    && await page.locator('img[src*="showcase-forbidden"], a[href^="javascript:"]').count() === 0, 'INPUT_BOUNDARY');
  await navigate(page, prefix, '/learn/water-journey?section=' + encodeURIComponent(malicious) + '&mode=live');
  await textShown(page, '이 단원을 찾을 수 없어 첫 단원을 보여드립니다.');
  check(label + ': unknown malicious section safely shows the first sample section', (await page.locator('.learn-reading-text').innerText()).includes('물이 충분히 차가워지면')
    && !await page.evaluate(() => window.__showcaseExecuted), 'INPUT_BOUNDARY');
  await navigate(page, prefix, '/learn/recycling-day/results/run-1');
  await textShown(page, '먼저');
  check(label + ': missing result for another sample is explicit', await page.getByTestId('result-attempt').count() === 0, 'STATE');
  await navigate(page, prefix, '/learn/recycling-day?section=recycling-3');
  await page.getByTestId('recommended-question-recycling-guide').click();
  await page.getByTestId('sample-answer').filter({ hasText: '거주 지역의 분리배출 안내' }).waitFor();
  check(label + ': second public sample has its own prepared answer', (await page.locator('.learn-reading-text').innerText()).includes('사는 곳마다'));
  await navigate(page, prefix, '/learn/water-journey');
  const capability = await page.evaluate(() => ({ apiAvailable: !!window.speechSynthesis, localKoreanVoices: window.speechSynthesis?.getVoices().filter(voice => voice.localService && /^ko(?:-|_|$)/i.test(voice.lang)).length ?? 0 }));
  speechObservations.push({ label, category: 'ACTUAL_BROWSER_CAPABILITY', ...capability, actualAudioListening: 'NOT_RUN', voiceOver: 'NOT_RUN' });
  if (screenshotsEnabled) {
    await page.setViewportSize({ width: 320, height: 780 });
    await page.getByTestId('recommended-question-water-ice').click();
    await assertNoOverflow(page, label + ': 320px reader and controls');
    await capture(page, '05-narrow-reader');
    await page.getByRole('link', { name: '퀴즈 풀기', exact: true }).click();
    await assertNoOverflow(page, label + ': 320px quiz');
    await navigate(page, prefix, '/teacher');
    await assertNoOverflow(page, label + ': 320px teacher');
  }
  await context.close();
}

async function quotaStorageBoundary() {
  step = 'storage: write failure then reset';
  const quota = await newContext('write-failure-storage');
  await navigate(quota.page, '/', '/learn/water-journey/quiz');
  await answerQuiz(quota.page);
  await quota.page.getByRole('button', { name: '제출하기', exact: true }).click();
  await heading(quota.page, '체험 결과');
  check('storage: quota probe starts from a genuinely saved result', submissions(await stored(quota.page)).length === 1, 'STATE');
  await quota.page.evaluate(storageKey => {
    const nativeSet = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (this === sessionStorage && key === storageKey) throw new DOMException('Synthetic quota exceeded', 'QuotaExceededError');
      return nativeSet.call(this, key, value);
    };
  }, storageKey);
  await quota.page.getByRole('button', { name: '다시 풀기', exact: true }).click();
  await textShown(quota.page, '현재 화면에서만 체험');
  await quota.page.getByRole('button', { name: '데모 초기화', exact: true }).click();
  check('storage: reset removes prior state after write-only failure', await quota.page.evaluate(key => sessionStorage.getItem(key), storageKey) === null, 'STATE');
  await navigate(quota.page, '/', '/learn/water-journey/results/run-1');
  await textShown(quota.page, '먼저');
  check('storage: old result cannot reappear after quota failure/reset', true, 'STATE');
  await quota.context.close();
}

async function storageBoundaries() {
  for (const [name, state] of [
    ['corrupt-json', '{'], ['old-version', JSON.stringify({ version: 0, sampleVersion: 'old', samples: {} })],
    ['oversize', 'x'.repeat(65537)], ['unknown-sample', JSON.stringify({ version: 1, sampleVersion: '2026-09-v1', samples: { 'private-sample': {} } })],
  ]) {
    step = 'storage: ' + name;
    const { context, page } = await newContext(name, { state });
    await navigate(page, '/DO-DREAM/', '/learn');
    await textShown(page, '저장된 체험 상태를 읽을 수 없어 처음부터 시작합니다.');
    await page.getByTestId('material-water-journey').click();
    await page.locator('.learn-reading-text').waitFor();
    check('storage: ' + name + ' recovers with notice and usable UI', true, 'STATE');
    await context.close();
  }
  step = 'storage: unavailable';
  const { context, page } = await newContext('unavailable-storage', { storageUnavailable: true });
  await navigate(page, '/', '/learn/water-journey/quiz');
  await textShown(page, '현재 화면에서만 체험');
  await answerQuiz(page);
  await page.getByRole('button', { name: '제출하기', exact: true }).click();
  await heading(page, '체험 결과');
  check('storage: denied sessionStorage permits in-memory journey', true, 'STATE');
  await page.reload();
  await textShown(page, '먼저');
  check('storage: unavailable persistence limitation is accurate', await page.getByTestId('result-attempt').count() === 0, 'STATE');
  await context.close();
}

async function tabTo(page, locator) {
  for (let index = 0; index < 80; index++) {
    // Observe focus and its visual treatment in the same browser task. A route
    // heading's focus effect may otherwise run between two separate observations.
    const focus = await locator.evaluate(element => {
      const style = getComputedStyle(element);
      return { active: document.activeElement === element, focusVisible: element.matches(':focus-visible'),
        outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, boxShadow: style.boxShadow,
        text: element.textContent?.slice(0, 50) ?? '' };
    });
    if (focus.active) {
      const visible = focus.outlineStyle !== 'none' && parseFloat(focus.outlineWidth) > 0 || focus.boxShadow !== 'none';
      check('keyboard visible focus: ' + focus.text, visible, 'KEYBOARD', focus);
      return;
    }
    await page.keyboard.press('Tab');
  }
  throw new Error('Keyboard target was unreachable using Tab');
}
async function keyboardJourney() {
  step = 'keyboard journey';
  const { context, page } = await newContext('keyboard');
  await navigate(page, '/', '/');
  const activate = async locator => { await tabTo(page, locator); await page.keyboard.press('Enter'); };
  await activate(page.getByRole('link', { name: '학생 체험 시작', exact: true }));
  await activate(page.getByTestId('material-water-journey'));
  await activate(page.getByTestId('recommended-question-water-ice'));
  const source = page.getByRole('button', { name: '참고 구간 보기', exact: true }).first();
  await activate(source);
  await page.locator('dialog[open]').waitFor();
  for (let index = 0; index < 4; index++) {
    await page.keyboard.press('Tab');
    assert.equal(await page.locator('dialog[open]').evaluate(dialog => dialog.contains(document.activeElement)), true, 'native dialog must retain keyboard focus');
  }
  for (let index = 0; index < 4; index++) {
    await page.keyboard.press('Shift+Tab');
    assert.equal(await page.locator('dialog[open]').evaluate(dialog => dialog.contains(document.activeElement)), true, 'reverse Tab must retain modal focus');
  }
  check('keyboard modal retains forward and reverse Tab focus', true, 'KEYBOARD');
  await page.keyboard.press('Escape');
  check('keyboard dialog Escape restores trigger focus', await source.evaluate(element => element === document.activeElement), 'KEYBOARD');
  await activate(page.getByRole('link', { name: '퀴즈 풀기', exact: true }));
  for (const value of ['ice', 'evaporate']) {
    const option = page.locator(`input[type=radio][value=${value}]`);
    // Native radio groups have one Tab stop; arrows select the remaining option.
    const name = await option.getAttribute('name');
    const group = page.locator(`input[type=radio][name="${name}"]`);
    await tabTo(page, group.first());
    for (let index = 0; index < await group.count(); index++) {
      if (await option.evaluate(element => document.activeElement === element)) break;
      await page.keyboard.press('ArrowRight');
    }
    await page.keyboard.press('Space');
    assert.equal(await option.isChecked(), true);
  }
  await activate(page.getByRole('button', { name: '제출하기', exact: true }));
  await heading(page, '체험 결과');
  await activate(page.getByRole('link', { name: '교사 화면 보기', exact: true }));
  await heading(page, '교사 샘플 화면');
  await activate(page.getByRole('button', { name: '데모 초기화', exact: true }));
  await page.getByRole('link', { name: '학생 체험 시작', exact: true }).waitFor();
  check('keyboard journey completed with Tab/Enter/Space/arrows/Escape', true, 'KEYBOARD');
  await context.close();
}

async function speechBoundary() {
  step = 'controlled local speech events';
  const { context, page } = await newContext('controlled-local-speech', { speech: 'local' });
  await navigate(page, '/', '/learn/water-journey');
  await page.getByRole('button', { name: '본문 듣기', exact: true }).click();
  await textShown(page, '읽는 중');
  let before = await page.evaluate(() => ({ spoken: window.__showcaseSpeech.utterances.length, canceled: window.__showcaseSpeech.canceled }));
  check('controlled speech chooses local Korean voice', before.spoken === 1 && await page.evaluate(() => window.__showcaseSpeech.utterances[0].voice.localService), 'CONTROLLED_SPEECH_EVENTS');
  await page.getByRole('button', { name: '듣기 일시정지', exact: true }).click();
  await page.getByRole('button', { name: '듣기 계속', exact: true }).click();
  check('controlled speech pause/resume events', await page.evaluate(() => window.__showcaseSpeech.paused === 1 && window.__showcaseSpeech.resumed === 1), 'CONTROLLED_SPEECH_EVENTS');
  await page.getByRole('button', { name: '다음 단원', exact: true }).click();
  await page.getByRole('heading', { name: '하늘로 올라가는 물', exact: true }).waitFor();
  await page.evaluate(() => { const utterance = window.__showcaseSpeech.utterances[0]; utterance.onend?.(); utterance.onerror?.(); });
  let after = await page.evaluate(() => ({ spoken: window.__showcaseSpeech.utterances.length, canceled: window.__showcaseSpeech.canceled }));
  check('late speech events cannot continue after section navigation', after.spoken === before.spoken && after.canceled > before.canceled, 'CONTROLLED_SPEECH_EVENTS', { before, after });
  await page.getByRole('button', { name: '본문 듣기', exact: true }).click();
  before = await page.evaluate(() => ({ spoken: window.__showcaseSpeech.utterances.length, canceled: window.__showcaseSpeech.canceled }));
  await page.evaluate(() => window.__showcaseSpeech.utterances[0].onerror?.());
  check('old speech error cannot cancel the new section playback', await page.getByRole('button', { name: '듣기 일시정지', exact: true }).isEnabled()
    && await page.evaluate(before => window.__showcaseSpeech.canceled === before.canceled && window.__showcaseSpeech.utterances.length === before.spoken, before), 'CONTROLLED_SPEECH_EVENTS');
  await page.getByRole('button', { name: '데모 초기화', exact: true }).click();
  await page.evaluate(() => { for (const utterance of window.__showcaseSpeech.utterances) { utterance.onend?.(); utterance.onerror?.(); } });
  after = await page.evaluate(() => ({ spoken: window.__showcaseSpeech.utterances.length, canceled: window.__showcaseSpeech.canceled }));
  check('late speech events cannot continue after reset', after.spoken === before.spoken && after.canceled > before.canceled, 'CONTROLLED_SPEECH_EVENTS', { before, after });
  await context.close();
  const absent = await newContext('controlled-remote-only-speech', { speech: 'remote-only' });
  await navigate(absent.page, '/DO-DREAM/', '/learn/water-journey');
  await textShown(absent.page, '로컬 한국어 음성이 없습니다');
  check('remote-only voice leaves readable text and disabled TTS', await absent.page.getByRole('button', { name: '본문 듣기', exact: true }).isDisabled()
    && await absent.page.evaluate(() => window.__showcaseSpeech.utterances.length === 0), 'CONTROLLED_SPEECH_EVENTS');
  await absent.context.close();
  const broken = await newContext('controlled-voices-error', { speech: 'voices-throw' });
  await navigate(broken.page, '/', '/learn/water-journey');
  await textShown(broken.page, '로컬 한국어 음성이 없습니다');
  check('voice enumeration error preserves text experience', await broken.page.getByRole('button', { name: '본문 듣기', exact: true }).isDisabled()
    && (await broken.page.locator('.learn-reading-text').innerText()).length > 50, 'CONTROLLED_SPEECH_EVENTS');
  await broken.context.close();
}

async function runAcceptance() {
  artifactDigestBefore = await digestFiles(artifact);
  sourceDigestBefore = await digestFiles(path.join(repository, 'fe-web/src'));
  server = await startShowcaseServer();
  browser = await chromium.launch({ channel: 'chrome', headless: true });
  browserVersion = browser.version();
  await normalJourney('/', true);
  await normalJourney('/DO-DREAM/', false);
  await storageBoundaries();
  await quotaStorageBoundary();
  await keyboardJourney();
  await speechBoundary();
  check('artifact unchanged during single acceptance', artifactDigestBefore === await digestFiles(artifact), 'ACCEPTANCE_INTEGRITY');
  check('application source unchanged during single acceptance', sourceDigestBefore === await digestFiles(path.join(repository, 'fe-web/src')), 'ACCEPTANCE_INTEGRITY');
  check('no browser application errors', browserErrors.length === 0, 'BROWSER', browserErrors);
  check('API/external/websocket/eventsource/beacon request attempts are zero', network.forbiddenRequests.length === 0 && network.apiAttempts.length === 0 && network.socketAttempts.length === 0 && network.cspViolations.length === 0, 'NETWORK');
  check('real static files were requested', network.staticRequests.length > 0, 'NETWORK');
}

await fs.mkdir(captureDirectory, { recursive: true });
let interrupt;
const interrupted = new Promise((_resolve, reject) => { interrupt = reject; });
const deadline = setTimeout(() => interrupt(new Error('Browser acceptance exceeded its 180 second limit')), 180000);
const terminate = () => interrupt(new Error('Browser acceptance interrupted; cleaning up only its own browser and static server'));
process.once('SIGTERM', terminate);
process.once('SIGINT', terminate);
try {
  await Promise.race([runAcceptance(), interrupted]);
} catch (error) {
  checks.push({ name: step, status: 'FAIL', category: 'HARNESS_OR_PRODUCT', errorType: error.constructor.name, message: error.message });
  process.exitCode = 1;
} finally {
  clearTimeout(deadline);
  process.removeListener('SIGTERM', terminate);
  process.removeListener('SIGINT', terminate);
  await browser?.close();
  await server?.close();
  const result = { status: process.exitCode ? 'FAIL' : 'PASS', timestamp: stamp, durationMs: Date.now() - startedAt,
    runtime: { node: process.version, platform: process.platform, browser: 'Google Chrome', browserVersion, channel: 'chrome', headless: true },
    localOrigin: server?.origin, artifactDigest: artifactDigestBefore, sourceDigest: sourceDigestBefore, checks, screenshots, speechObservations,
    counts: { checks: checks.length, staticRequests: network.staticRequests.length, forbiddenRequestAttempts: network.forbiddenRequests.length,
      apiAttemptsBeforeCsp: network.apiAttempts.length, webSocketAttempts: network.socketAttempts.length, cspViolations: network.cspViolations.length },
    network, browserErrors, scope: 'Built static artifact only; fresh independent Chrome contexts; no API responses mocked; no backend services started.',
    actualAudioListening: 'NOT_RUN', voiceOver: 'NOT_RUN', backendData: 'NOT_TOUCHED', remoteCiExecution: 'NOT_RUN' };
  const json = JSON.stringify(result, null, 2) + '\n';
  await fs.writeFile(path.join(evidence, `showcase-browser-${stamp}.json`), json, { flag: 'wx' });
  await fs.writeFile(path.join(evidence, 'showcase-browser-latest.json'), json);
  console.log(JSON.stringify({ status: result.status, ...result.counts, failed: checks.filter(check => check.status === 'FAIL'), evidence: path.relative(repository, path.join(evidence, `showcase-browser-${stamp}.json`)) }));
}

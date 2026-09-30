/** Public Pages acceptance, separate from local checks. No API mocks or user profile. */
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';
import { assertNoSymlinkChain, listFiles, REPO_ROOT, SHOWCASE_MIME, isShowcasePublicFile } from '../scripts/showcase-paths.mjs';
import { assertArtifactManifest } from '../scripts/showcase-audit.mjs';

const publicationRoot = path.join(REPO_ROOT, '.local/publication-pages');
const resultsRoot = path.join(publicationRoot, 'results');
const stateKeys = ['dodream.showcase.v1.state', 'dodream.showcase.original-ui.v1'];
const sha256 = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const digestOf = files => sha256(files.map(file => `${file.path}\0${file.bytes}\0${file.sha256}\n`).join(''));
const validFile = isShowcasePublicFile;

// This is a destination allowlist, not an assertion that the address is deployed.
// The caller must supply page_url observed from the successful Pages deployment.
export function validatePageUrl(value) {
  const url = new URL(value);
  assert.ok(url.protocol === 'https:' && url.hostname === 'rladbstn1000.github.io'
    && url.pathname === '/DO-DREAM/' && !url.port && !url.username && !url.password && !url.search && !url.hash,
  'Only the confirmed HTTPS Pages URL for rladbstn1000/DO-DREAM is allowed');
  return url.href;
}

export function validateReleaseManifest(manifest) {
  assert.equal(manifest?.schemaVersion, 1);
  assert.equal(manifest.repository, 'rladbstn1000/DO-DREAM');
  assert.match(manifest.sourceSha, /^[0-9a-f]{40}$/);
  assert.match(String(manifest.runId), /^[1-9][0-9]*$/);
  assert.match(String(manifest.runAttempt), /^[1-9][0-9]*$/);
  assert.equal(manifest.runUrl, `https://github.com/rladbstn1000/DO-DREAM/actions/runs/${manifest.runId}`);
  assert.equal(manifest.verification?.status, 'PASS');
  assert.equal(manifest.verification.forbiddenRequestAttempts, 0);
  assert.ok(Number.isInteger(manifest.verification.browserChecks) && manifest.verification.browserChecks > 0);
  const artifact = manifest.artifact;
  assertArtifactManifest(artifact);
  assert.ok(Array.isArray(artifact?.files) && artifact.files.length >= 3 && artifact.files.length <= 100);
  const names = artifact.files.map(file => file.path);
  assert.deepEqual(names, [...new Set(names)].sort(), 'Manifest paths must be unique and sorted');
  for (const file of artifact.files) {
    assert.ok(typeof file.path === 'string' && validFile(file.path), 'Only reviewed static asset paths are accepted');
    assert.ok(Number.isInteger(file.bytes) && file.bytes > 0 && file.bytes <= 5_000_000);
    assert.match(file.sha256, /^[0-9a-f]{64}$/);
  }
  assert.ok(names.includes('index.html') && names.some(name => name.endsWith('.js')) && names.some(name => name.endsWith('.css')));
  assert.equal(artifact.fileCount, artifact.files.length);
  assert.equal(artifact.totalBytes, artifact.files.reduce((sum, file) => sum + file.bytes, 0));
  assert.ok(artifact.totalBytes <= 20_000_000);
  assert.equal(artifact.manifestDigest, digestOf(artifact.files), 'Manifest digest does not match its file records');
  return manifest;
}

function ownInput(value, kind) {
  const absolute = path.resolve(value);
  assert.ok(absolute.startsWith(publicationRoot + path.sep), 'Downloaded inputs must be inside .local/publication-pages/');
  assertNoSymlinkChain(absolute);
  const stat = fs.statSync(absolute);
  assert.ok(kind === 'directory' ? stat.isDirectory() : stat.isFile() && stat.size <= 256 * 1024);
  if (kind === 'manifest') assert.equal(path.basename(absolute), 'release-manifest.json');
  return absolute;
}

function parseInputs(argv) {
  assert.equal(argv.length, 6, 'Usage: node fe-web/tests/showcase-public-browser.mjs --url ACTUAL_PAGE_URL --manifest DOWNLOADED_RELEASE_MANIFEST --artifact-dir DOWNLOADED_PAGES_FILES');
  const values = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    assert.ok(['--url', '--manifest', '--artifact-dir'].includes(argv[index]) && !values.has(argv[index]), 'Unexpected or duplicate option');
    values.set(argv[index], argv[index + 1]);
  }
  const pageUrl = validatePageUrl(values.get('--url'));
  const manifestPath = ownInput(values.get('--manifest'), 'manifest');
  const artifactDirectory = ownInput(values.get('--artifact-dir'), 'directory');
  return { pageUrl, manifestPath, artifactDirectory, manifest: validateReleaseManifest(JSON.parse(fs.readFileSync(manifestPath, 'utf8'))) };
}

function mimeMatches(name, contentType) {
  const type = (contentType ?? '').split(';')[0].trim().toLowerCase();
  const extension = path.extname(name);
  const expected = SHOWCASE_MIME[extension]?.split(';')[0];
  return type === expected || (extension === '.js' && type === 'application/javascript');
}

async function main(argv) {
  const stamp = new Date().toISOString().replaceAll(':', '').replaceAll('.', '');
  const startedAtUtc = new Date().toISOString();
  const checks = [], httpFiles = [], browserFiles = [], staticRequests = [], forbiddenRequests = [], apiAttempts = [], cspViolations = [], socketAttempts = [], microphoneAttempts = [];
  const consoleErrors = [], consoleWarnings = [], pageErrors = [], responseTasks = [], screenshots = [];
  const shutdown = new AbortController();
  let input, browser, browserVersion, observedUrl, step = 'input validation', status = 'FAIL', provenance = 'NOT_RUN';
  let deadline, terminate, interrupt;
  const check = (name, condition, category = 'PUBLIC_UI', details) => {
    checks.push({ name, category, status: condition ? 'PASS' : 'FAIL', ...(details === undefined ? {} : { details }) });
    assert.ok(condition, name);
  };
  assertNoSymlinkChain(resultsRoot);
  fs.mkdirSync(resultsRoot, { recursive: true });
  const screenshotDirectory = path.join(resultsRoot, `public-browser-${stamp}`);
  const screenshot = async (page, name) => {
    fs.mkdirSync(screenshotDirectory, { recursive: true });
    const destination = path.join(screenshotDirectory, name + '.png');
    await page.screenshot({ path: destination, fullPage: true, animations: 'disabled' });
    screenshots.push(path.relative(REPO_ROOT, destination));
  };
  async function acceptance() {
    input = parseInputs(argv);
    provenance = 'FAIL'; // Validation is now running; a mismatch must never be reported as NOT_RUN.
    const { manifest, pageUrl, artifactDirectory } = input;
    const downloadedPaths = listFiles(artifactDirectory);
    assert.deepEqual(downloadedPaths.map(filename => path.relative(artifactDirectory, filename).replaceAll(path.sep, '/')),
      manifest.artifact.files.map(file => file.path), 'Downloaded artifact must contain only the manifest-approved files');
    const downloadedFiles = downloadedPaths.map(filename => {
      assert.ok(fs.statSync(filename).size <= 5_000_000, 'Downloaded static asset is too large');
      const bytes = fs.readFileSync(filename);
      return { path: path.relative(artifactDirectory, filename).replaceAll(path.sep, '/'), bytes: bytes.length, sha256: sha256(bytes) };
    });
    const manifestFiles = manifest.artifact.files.map(({ path, bytes, sha256 }) => ({ path, bytes, sha256 }));
    check('downloaded Pages artifact matches the remote verified manifest', JSON.stringify(downloadedFiles) === JSON.stringify(manifestFiles)
      && digestOf(downloadedFiles) === manifest.artifact.manifestDigest, 'ARTIFACT_PROVENANCE');
    const expectedByUrl = new Map(manifest.artifact.files.map(file => [new URL(file.path, pageUrl).href, file]));
    expectedByUrl.set(pageUrl, manifest.artifact.files.find(file => file.path === 'index.html'));
    const approvedFile = rawUrl => {
      const url = new URL(rawUrl);
      if (url.protocol !== 'https:' || url.search) return undefined;
      url.hash = '';
      return expectedByUrl.get(url.href);
    };

    step = 'public artifact byte comparison';
    for (const expected of manifest.artifact.files) {
      const url = new URL(expected.path, pageUrl).href;
      const observation = { path: expected.path, url, observedAtUtc: new Date().toISOString() };
      httpFiles.push(observation);
      const response = await fetch(url, { redirect: 'error', credentials: 'omit', cache: 'no-store', signal: AbortSignal.any([shutdown.signal, AbortSignal.timeout(20000)]),
        headers: { Accept: '*/*', 'Accept-Encoding': 'identity' } });
      Object.assign(observation, { status: response.status, contentType: response.headers.get('content-type'), etag: response.headers.get('etag') });
      assert.equal(response.status, 200, 'Public artifact response must be HTTP 200');
      assert.ok(mimeMatches(expected.path, observation.contentType), 'Public asset content type mismatch');
      const chunks = []; let length = 0;
      for await (const chunk of response.body) {
        length += chunk.length;
        assert.ok(length <= expected.bytes, 'Public response exceeds the verified artifact size');
        chunks.push(chunk);
      }
      Object.assign(observation, { bytes: length, sha256: sha256(Buffer.concat(chunks)) });
      check(`public bytes match remote artifact: ${expected.path}`, length === expected.bytes && observation.sha256 === expected.sha256, 'ARTIFACT_PROVENANCE');
    }
    check('public file-set digest matches remote verified artifact', digestOf(httpFiles) === manifest.artifact.manifestDigest, 'ARTIFACT_PROVENANCE');
    provenance = 'PASS';
    step = 'anonymous public Chrome journey';
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    browserVersion = browser.version();
    async function context(label, viewport = { width: 1280, height: 920 }) {
      const context = await browser.newContext({ serviceWorkers: 'block', viewport, reducedMotion: 'reduce' });
      await context.exposeBinding('__publicAttempt', (_source, event) => apiAttempts.push({ context: label, ...event }));
      await context.exposeBinding('__publicMicrophone', (_source, event) => microphoneAttempts.push({ context: label, ...event }));
      await context.exposeBinding('__publicCsp', (_source, event) => cspViolations.push({ context: label, ...event }));
      await context.addInitScript(() => {
        const record = (api, url) => void window.__publicAttempt({ api, url: String(url ?? '') });
        const nativeFetch = window.fetch;
        window.fetch = function (value, options) { record('fetch', typeof value === 'string' ? value : value?.url); return nativeFetch.call(this, value, options); };
        const nativeOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function (method, url, ...rest) { record('XMLHttpRequest', url); return nativeOpen.call(this, method, url, ...rest); };
        for (const name of ['WebSocket', 'EventSource']) {
          const Native = window[name];
          if (Native) window[name] = class extends Native { constructor(url, ...rest) { record(name, url); super(url, ...rest); } };
        }
        const beacon = navigator.sendBeacon?.bind(navigator);
        if (beacon) navigator.sendBeacon = (url, data) => { record('sendBeacon', url); return beacon(url, data); };
        if (navigator.serviceWorker) {
          const register = navigator.serviceWorker.register.bind(navigator.serviceWorker);
          navigator.serviceWorker.register = (url, options) => { record('serviceWorker.register', url); return register(url, options); };
        }
        // Any microphone/recognition attempt fails acceptance and is denied
        // before permission can be requested. No simulated recording is returned.
        if (navigator.mediaDevices?.getUserMedia) {
          navigator.mediaDevices.getUserMedia = () => { void window.__publicMicrophone({ api: 'getUserMedia' }); throw new Error('Microphone request forbidden in showcase acceptance'); };
        }
        for (const name of ['getUserMedia', 'webkitGetUserMedia', 'mozGetUserMedia']) {
          const native = navigator[name]?.bind(navigator);
          if (native) navigator[name] = () => { void window.__publicMicrophone({ api: name }); throw new Error('Microphone request forbidden in showcase acceptance'); };
        }
        for (const name of ['SpeechRecognition', 'webkitSpeechRecognition']) {
          const Native = window[name];
          if (Native) window[name] = class extends Native { start() { void window.__publicMicrophone({ api: name + '.start' }); throw new Error('Speech recognition forbidden in showcase acceptance'); } };
        }
        document.addEventListener('securitypolicyviolation', event => void window.__publicCsp({ directive: event.violatedDirective, blockedURI: event.blockedURI }));
      });
      await context.route('**/*', route => {
        const request = route.request();
        const event = { context: label, url: request.url(), method: request.method(), resourceType: request.resourceType() };
        if (request.method() === 'GET' && approvedFile(request.url())) { staticRequests.push(event); return route.continue(); }
        forbiddenRequests.push(event); return route.abort('blockedbyclient');
      });
      if (context.routeWebSocket) await context.routeWebSocket('**/*', socket => { socketAttempts.push({ context: label, url: socket.url() }); socket.close(); });
      context.on('page', page => {
        page.setDefaultTimeout(20000);
        page.on('console', message => {
          if (message.type() === 'error') consoleErrors.push({ context: label, text: message.text() });
          if (message.type() === 'warning') consoleWarnings.push({ context: label, text: message.text() });
        });
        page.on('pageerror', error => pageErrors.push({ context: label, name: error.name, message: error.message }));
        page.on('websocket', socket => socketAttempts.push({ context: label, url: socket.url() }));
        page.on('response', response => responseTasks.push((async () => {
          const expected = approvedFile(response.url());
          assert.ok(expected, 'Unapproved response URL');
          const contentType = (await response.allHeaders())['content-type'];
          assert.equal(response.status(), 200);
          assert.ok(mimeMatches(expected.path, contentType));
          const bytes = await response.body();
          assert.equal(bytes.length, expected.bytes); assert.equal(sha256(bytes), expected.sha256);
          browserFiles.push({ context: label, path: expected.path, status: response.status(), contentType, sha256: expected.sha256 });
        })().catch(error => { pageErrors.push({ context: label, name: 'ResponseIntegrityError', message: error.message }); })));
      });
      return { context, page: await context.newPage() };
    }
    async function keyboardActivate(page, target) {
      for (let count = 0; count < 80; count++) {
        const state = await target.evaluate(element => {
          const style = getComputedStyle(element);
          return { focused: document.activeElement === element, visible: style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0 || style.boxShadow !== 'none' };
        });
        if (state.focused) { check('keyboard target has visible focus', state.visible, 'PUBLIC_KEYBOARD'); await page.keyboard.press('Enter'); return; }
        await page.keyboard.press('Tab');
      }
      throw new Error('Public keyboard target cannot be reached');
    }
    const desktop = await context('desktop'); const page = desktop.page;
    const response = await page.goto(pageUrl);
    observedUrl = page.url();
    await page.getByText('샘플 체험', { exact: true }).waitFor();
    check('anonymous HTTPS entry has expected URL and HTML', response?.status() === 200 && observedUrl === pageUrl && await page.getByText('샘플 체험', { exact: true }).count() === 1);
    await keyboardActivate(page, page.getByTestId('start-student'));
    await keyboardActivate(page, page.getByTestId('material-water-journey'));
    await page.getByRole('button', { name: '처음부터 듣기 챕터 처음부터', exact: true }).click();
    await page.getByRole('heading', { name: '1. 얼음과 물', exact: true }).waitFor();
    await page.getByRole('button', { name: '다음 섹션', exact: true }).click();
    await page.getByRole('button', { name: '학습 완료', exact: true }).click();
    await page.getByRole('heading', { name: '2. 하늘로 올라가는 물', exact: true }).waitFor();
    check('original app library, playback choice and player navigation work', page.url().includes('/app/material/water-journey/player?section=water-2'));
    await page.reload(); await page.getByRole('heading', { name: '2. 하늘로 올라가는 물', exact: true }).waitFor();
    check('nested hash player route survives refresh', page.url().includes('section=water-2'));
    await page.goBack(); await page.getByRole('heading', { name: '1. 얼음과 물', exact: true }).waitFor();
    check('browser back restores the earlier chapter and paragraph', page.url().includes('section=water-1&paragraph=1'));
    await page.getByRole('link', { name: '질문하기', exact: true }).click();
    await page.getByRole('button', { name: '말하기', exact: true }).click();
    const exampleDialog = page.getByRole('dialog', { name: '예시 질문 선택', exact: true });
    await exampleDialog.getByRole('button', { name: '물이 충분히 차가워지면 무엇이 되나요?', exact: true }).click();
    await page.getByRole('button', { name: '확인', exact: true }).click();
    await page.getByText('준비된 예시 답변', { exact: true }).waitFor();
    check('question uses explicit example selection with no microphone', (await page.locator('.app-answer-bubble').innerText()).replace(/\s+/g, ' ').includes('물이 충분히 차가워지면 단단한 얼음이 됩니다. 얼음을 따뜻한 곳에 두면 다시 물로 바뀝니다.'));
    const source = page.getByRole('button', { name: '참고 구간 보기', exact: true });
    await source.click();
    const sourceDialog = page.getByRole('dialog', { name: '참고 구간 · 얼음과 물', exact: true });
    await sourceDialog.waitFor();
    check('source excerpt matches the same public lesson', await sourceDialog.locator('p').first().innerText() === '물이 충분히 차가워지면 단단한 얼음이 됩니다. 얼음을 따뜻한 곳에 두면 다시 물이 됩니다.');
    check('source modal stays inside the phone frame', await sourceDialog.evaluate(element => {
      const modal = element.getBoundingClientRect(), phone = document.querySelector('[data-testid="student-phone"]').getBoundingClientRect();
      return modal.left >= phone.left && modal.right <= phone.right && modal.top >= phone.top && modal.bottom <= phone.bottom;
    }), 'PUBLIC_LAYOUT');
    await page.keyboard.press('Escape'); await sourceDialog.waitFor({ state: 'hidden' });
    check('source closes by keyboard and returns focus', await source.evaluate(element => element === document.activeElement), 'PUBLIC_KEYBOARD');
    await page.getByRole('link', { name: '뒤로가기', exact: true }).click();
    await page.getByRole('link', { name: '뒤로가기', exact: true }).click();
    await page.getByRole('link', { name: '퀴즈 풀기 학습 내용 확인', exact: true }).click();
    await page.getByRole('link', { name: '1. 물이 충분히 차가워지면 무엇이 되나요? 단답형', exact: true }).click();
    await page.getByRole('textbox', { name: '답 입력란', exact: true }).fill('얼음');
    await page.getByRole('button', { name: '다음 문제', exact: true }).click();
    await page.getByRole('textbox', { name: '답 입력란', exact: true }).fill('증발');
    await page.getByRole('button', { name: '채점하기', exact: true }).click();
    await page.getByRole('heading', { name: '퀴즈 완료!', exact: true }).waitFor();
    check('original written quiz produces its deterministic example result', page.url().endsWith('/app/material/water-journey/result') && (await page.getByTestId('quiz-score').innerText()).replace(/\s+/g, '') === '2/2');
    await page.reload(); await page.getByTestId('quiz-score').waitFor();
    check('result direct URL and refresh preserve same-tab state', await page.getByText('예시 판정 · 1회차', { exact: true }).count() === 1);
    await screenshot(page, 'public-result');
    await page.getByRole('link', { name: '교사 웹', exact: true }).click();
    await page.locator('a[href="#/teacher/classroom/1-1"]').click();
    await page.locator('a[href="#/teacher/student/demo-student"]').click();
    const resultCard = page.locator('.sr-quiz-card').filter({ hasText: '물의 여행 · 1회' });
    await resultCard.waitFor();
    check('original teacher student screen shows the same-tab written result', (await resultCard.innerText()).includes('2개 정답'));
    await page.locator('a[href="#/teacher/history/water-journey"]').click();
    await page.getByText('준비된 샘플 답변', { exact: true }).waitFor();
    check('teacher conversation screen shows the same-tab question', (await page.locator('.ch-user .ch-bubble').innerText()).includes('물이 충분히 차가워지면 무엇이 되나요?'));
    const mobile = await context('narrow-independent', { width: 320, height: 780 });
    await mobile.page.goto(pageUrl + '#/app/material/water-journey/result');
    await mobile.page.getByRole('heading', { name: '아직 풀이 결과가 없습니다.', exact: true }).waitFor();
    check('independent anonymous context has no first context result', await mobile.page.getByTestId('quiz-score').count() === 0);
    await mobile.page.goto(pageUrl + '#/app/material/water-journey/player?section=water-2');
    await mobile.page.getByRole('heading', { name: '2. 하늘로 올라가는 물', exact: true }).waitFor();
    await mobile.page.getByRole('link', { name: '질문하기', exact: true }).click();
    await mobile.page.getByRole('textbox', { name: '질문 입력창', exact: true }).fill('젖은 수건이 마르는 까닭은 무엇인가요?');
    await mobile.page.getByRole('button', { name: '확인', exact: true }).click();
    await mobile.page.getByText('준비된 예시 답변', { exact: true }).waitFor();
    const layout = await mobile.page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth,
      clipped: [...document.querySelectorAll('.app-screen button, .app-screen input, .app-screen textarea, .app-screen p')].filter(element => {
        const box = element.getBoundingClientRect(); return box.width > 0 && (box.left < -1 || box.right > innerWidth + 1);
      }).length }));
    check('320 CSS px public phone reading and question controls fit', layout.scroll <= layout.width + 1 && layout.clipped === 0, 'PUBLIC_LAYOUT', layout);
    await screenshot(mobile.page, 'public-narrow');
    await Promise.all(responseTasks);
    await mobile.context.close();
    await page.evaluate(() => sessionStorage.setItem('publication.unrelated', 'keep'));
    await page.getByTestId('reset-demo').click();
    await page.getByTestId('start-student').waitFor();
    check('public reset clears both showcase-owned stores only', await page.evaluate(keys => keys.every(key => sessionStorage.getItem(key) === null) && sessionStorage.getItem('publication.unrelated') === 'keep', stateKeys));
    await page.goto(pageUrl + '#/app/material/water-journey/result');
    await page.getByRole('heading', { name: '아직 풀이 결과가 없습니다.', exact: true }).waitFor();
    check('reset result remains absent after a new document navigation', await page.getByTestId('quiz-score').count() === 0);
    await Promise.all(responseTasks);
    await desktop.context.close();
    const browserIntegrity = browserFiles.length === staticRequests.length && browserFiles.length > 0;
    if (!browserIntegrity) provenance = 'FAIL';
    check('all browser responses match the approved remote artifact', browserIntegrity, 'ARTIFACT_PROVENANCE');
    check('no public console or application errors', consoleErrors.length === 0 && pageErrors.length === 0, 'PUBLIC_BROWSER', { consoleErrors, pageErrors });
    check('no backend/external/API/microphone/WebSocket/EventSource/beacon attempts or CSP violations', forbiddenRequests.length === 0 && apiAttempts.length === 0 && microphoneAttempts.length === 0 && socketAttempts.length === 0 && cspViolations.length === 0, 'PUBLIC_NETWORK');
    status = 'PASS';
  }
  try {
    const interrupted = new Promise((_resolve, reject) => { interrupt = reject; });
    deadline = setTimeout(() => { shutdown.abort(); interrupt(new Error('Public acceptance exceeded its 180 second limit')); }, 180000);
    terminate = () => { shutdown.abort(); interrupt(new Error('Public acceptance interrupted; closing only its own test browser')); };
    process.once('SIGTERM', terminate); process.once('SIGINT', terminate);
    await Promise.race([acceptance(), interrupted]);
  } catch (error) {
    checks.push({ name: step, status: 'FAIL', category: 'PUBLIC_ACCEPTANCE', errorType: error.constructor.name, message: error.message,
      ...(error.cause?.code || error.code ? { code: error.cause?.code ?? error.code } : {}) });
    process.exitCode = 1;
  } finally {
    shutdown.abort();
    clearTimeout(deadline); process.removeListener('SIGTERM', terminate); process.removeListener('SIGINT', terminate);
    await browser?.close();
    const report = { status, publicSiteAcceptance: status, releaseArtifactProvenance: provenance, startedAtUtc, finishedAtUtc: new Date().toISOString(),
      actualPageUrl: input?.pageUrl, observedUrl, sourceSha: input?.manifest.sourceSha, remoteRunId: input?.manifest.runId, remoteRunUrl: input?.manifest.runUrl,
      remoteArtifactDigest: input?.manifest.artifact.manifestDigest, runtime: { node: process.version, platform: process.platform, browserVersion, channel: 'chrome', headless: true },
      counts: { checks: checks.length, provenanceStaticRequests: httpFiles.length, browserStaticRequests: staticRequests.length,
        forbiddenRequestAttempts: forbiddenRequests.length, apiAttemptsBeforeCsp: apiAttempts.length, webSocketAttempts: socketAttempts.length, cspViolations: cspViolations.length, microphoneAttempts: microphoneAttempts.length },
      checks, httpFiles, browserFiles, staticRequests, forbiddenRequests, apiAttempts, microphoneAttempts, socketAttempts, cspViolations, consoleErrors, consoleWarnings, pageErrors, screenshots,
      scope: 'Confirmed public HTTPS Pages URL; downloaded remote artifact; anonymous fresh Chrome contexts; no API response mocks; public checks are not added to local checks.',
      actualAudioListening: 'NOT_RUN', voiceOver: 'NOT_RUN', backendData: 'NOT_TOUCHED' };
    const json = JSON.stringify(report, null, 2) + '\n';
    const filename = path.join(resultsRoot, `showcase-public-browser-${stamp}.json`);
    assertNoSymlinkChain(filename); fs.writeFileSync(filename, json, { flag: 'wx' });
    const latest = path.join(resultsRoot, 'showcase-public-browser-latest.json');
    assertNoSymlinkChain(latest); fs.writeFileSync(latest, json);
    console.log(JSON.stringify({ status, releaseArtifactProvenance: provenance, actualPageUrl: input?.pageUrl, ...report.counts, failed: checks.filter(check => check.status === 'FAIL'), evidence: path.relative(REPO_ROOT, filename) }));
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main(process.argv.slice(2));

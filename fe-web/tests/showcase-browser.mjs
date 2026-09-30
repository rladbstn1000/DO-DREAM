/** Real Chrome against the built static artifact. No API mocks, backend, or user browser profile. */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';
import { RESULTS_DIR } from '../scripts/showcase-paths.mjs';
import { startShowcaseServer } from '../scripts/showcase-server.mjs';

const repository = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../..',
);
const artifact = path.join(repository, 'fe-web/dist-showcase');
const evidence = RESULTS_DIR;
const stamp = new Date().toISOString().replaceAll(':', '').replaceAll('.', '');
const captureDirectory = path.join(evidence, `browser-${stamp}`);
const storageKey = 'dodream.showcase.v1.state';
const sentinel = 'SHOWCASE_AUTH_SENTINEL_NOT_A_TOKEN';
const syntheticDocumentQuery =
  '?mode=live&role=TEACHER&api=http%3A%2F%2F127.0.0.1%3A8080';
const malicious =
  '<img src="https://showcase-forbidden.invalid/pixel" onerror="window.__showcaseExecuted=true"> javascript:alert(1)';
const checks = [],
  network = {
    staticRequests: [],
    forbiddenRequests: [],
    apiAttempts: [],
    socketAttempts: [],
    microphoneAttempts: [],
    cspViolations: [],
  };
const browserErrors = [],
  screenshots = [],
  speechObservations = [];
const startedAt = Date.now();
let server,
  browser,
  browserVersion,
  step = 'launch',
  artifactDigestBefore,
  sourceDigestBefore;

async function filesBelow(directory, prefix = '') {
  const entries = await fs.readdir(directory, { withFileTypes: true });
  const result = [];
  for (const entry of entries) {
    assert.ok(
      !entry.isSymbolicLink(),
      'static artifact must not contain symlinks',
    );
    const relative = prefix + entry.name;
    if (entry.isDirectory())
      result.push(
        ...(await filesBelow(path.join(directory, entry.name), relative + '/')),
      );
    else if (entry.isFile()) result.push(relative);
  }
  return result.sort();
}
async function digestFiles(directory) {
  const { createHash } = await import('node:crypto');
  const hash = createHash('sha256');
  for (const file of await filesBelow(directory))
    hash
      .update(file)
      .update('\0')
      .update(await fs.readFile(path.join(directory, file)))
      .update('\0');
  return hash.digest('hex');
}
function check(name, condition, category = 'ACTUAL_UI', details) {
  checks.push({
    name,
    category,
    status: condition ? 'PASS' : 'FAIL',
    ...(details === undefined ? {} : { details }),
  });
  assert.ok(condition, name);
}
async function textShown(page, phrase) {
  await page.getByText(phrase, { exact: false }).first().waitFor();
}
async function heading(page, name) {
  await page.getByRole('heading', { name, exact: true }).waitFor();
}
async function capture(page, name) {
  const file = path.join(captureDirectory, name + '.png');
  await page.screenshot({ path: file, fullPage: true, animations: 'disabled' });
  screenshots.push(path.relative(repository, file));
}
async function stored(page) {
  return page.evaluate(
    (key) => JSON.parse(sessionStorage.getItem(key) || 'null'),
    storageKey,
  );
}
function submissions(state, sample = 'water-journey') {
  return state?.samples?.[sample]?.submissions ?? [];
}
async function navigate(page, prefix, route) {
  await page.goto(server.origin + prefix + '#' + route);
}

// APIs stay native. Instrumentation records attempts before CSP/route guards can reject them.
// The only fake platform below is the separately labelled speech-event probe.
async function newContext(label, options = {}) {
  const context = await browser.newContext({
    serviceWorkers: 'block',
    viewport: options.viewport ?? { width: 1280, height: 920 },
    reducedMotion: 'reduce',
  });
  await context.exposeBinding('__recordShowcaseAttempt', (_source, attempt) =>
    network.apiAttempts.push({ context: label, ...attempt }),
  );
  await context.exposeBinding('__recordShowcaseMic', (_source, attempt) =>
    network.microphoneAttempts.push({ context: label, ...attempt }),
  );
  await context.exposeBinding('__recordShowcaseCsp', (_source, attempt) =>
    network.cspViolations.push({ context: label, ...attempt }),
  );
  await context.addInitScript(
    ({
      origin,
      label,
      storageKey,
      sentinel,
      state,
      stateKey,
      storageUnavailable,
      speech,
    }) => {
      if (location.origin !== origin) return;
      const record = (api, url) =>
        void window.__recordShowcaseAttempt({
          api,
          url: String(url ?? ''),
          page: location.href,
        });
      const nativeFetch = window.fetch;
      window.fetch = function (input, init) {
        record('fetch', typeof input === 'string' ? input : input?.url);
        return nativeFetch.call(this, input, init);
      };
      const nativeOpen = XMLHttpRequest.prototype.open;
      XMLHttpRequest.prototype.open = function (method, url, ...rest) {
        record('XMLHttpRequest', url);
        return nativeOpen.call(this, method, url, ...rest);
      };
      for (const name of ['WebSocket', 'EventSource']) {
        const Original = window[name];
        if (Original)
          window[name] = class extends Original {
            constructor(url, ...args) {
              record(name, url);
              super(url, ...args);
            }
          };
      }
      const nativeBeacon = navigator.sendBeacon?.bind(navigator);
      if (nativeBeacon)
        navigator.sendBeacon = (url, data) => {
          record('sendBeacon', url);
          return nativeBeacon(url, data);
        };
      if (navigator.serviceWorker) {
        const nativeRegister = navigator.serviceWorker.register.bind(
          navigator.serviceWorker,
        );
        navigator.serviceWorker.register = (url, options) => {
          record('serviceWorker.register', url);
          return nativeRegister(url, options);
        };
      }
      document.addEventListener('securitypolicyviolation', (event) => {
        void window.__recordShowcaseCsp({
          directive: event.violatedDirective,
          blockedURI: event.blockedURI,
          page: location.href,
        });
      });
      window.__showcaseExecuted = false;
      if (navigator.mediaDevices)
        navigator.mediaDevices.getUserMedia = (constraints) => {
          void window.__recordShowcaseMic({ api: 'getUserMedia' });
          return Promise.reject(new Error('Microphone forbidden'));
        };
      for (const name of ['SpeechRecognition', 'webkitSpeechRecognition'])
        if (window[name])
          window[name] = class {
            constructor() {
              void window.__recordShowcaseMic({ api: name });
              throw new Error('Recognition forbidden');
            }
          };
      for (const storage of [localStorage, sessionStorage]) {
        for (const [key, value] of Object.entries({
          accessToken: sentinel,
          refreshToken: sentinel,
          isLoggedIn: 'true',
          role: 'TEACHER',
          'dodream.auth.pending': sentinel,
          unrelated: 'KEEP_' + label,
        }))
          storage.setItem(key, value);
      }
      if (
        state !== undefined &&
        !sessionStorage.getItem('__showcase_test_seeded')
      ) {
        sessionStorage.setItem(stateKey ?? storageKey, state);
        sessionStorage.setItem('__showcase_test_seeded', 'true');
      }
      if (storageUnavailable)
        Object.defineProperty(window, 'sessionStorage', {
          configurable: true,
          get() {
            throw new DOMException('Synthetic storage denial', 'SecurityError');
          },
        });
      if (speech) {
        const events = {
          utterances: [],
          canceled: 0,
          paused: 0,
          resumed: 0,
          listeners: new Set(),
        };
        const voices =
          speech === 'local'
            ? [
                {
                  name: 'Synthetic local Korean event engine',
                  lang: 'ko-KR',
                  localService: true,
                },
              ]
            : [
                {
                  name: 'Synthetic remote voice',
                  lang: 'ko-KR',
                  localService: false,
                },
              ];
        class SyntheticUtterance {
          constructor(text) {
            this.text = text;
            this.onend = null;
            this.onerror = null;
          }
        }
        Object.defineProperty(window, 'SpeechSynthesisUtterance', {
          configurable: true,
          value: SyntheticUtterance,
        });
        Object.defineProperty(window, 'speechSynthesis', {
          configurable: true,
          value: {
            getVoices: () => {
              if (speech === 'voices-throw')
                throw new Error('Synthetic voice enumeration failure');
              return voices;
            },
            speak: (utterance) => events.utterances.push(utterance),
            cancel: () => {
              events.canceled++;
            },
            pause: () => {
              events.paused++;
            },
            resume: () => {
              events.resumed++;
            },
            addEventListener: (_type, listener) =>
              events.listeners.add(listener),
            removeEventListener: (_type, listener) =>
              events.listeners.delete(listener),
          },
        });
        window.__showcaseSpeech = events;
      }
    },
    {
      origin: server.origin,
      label,
      storageKey,
      sentinel,
      state: options.state,
      stateKey: options.stateKey,
      storageUnavailable: !!options.storageUnavailable,
      speech: options.speech,
    },
  );
  const allowedFiles = new Set(await filesBelow(artifact));
  const staticAllowed = (raw) => {
    const url = new URL(raw);
    if (url.origin !== server.origin) return false;
    let pathname = decodeURIComponent(url.pathname);
    if (pathname.startsWith('/DO-DREAM/'))
      pathname = pathname.slice('/DO-DREAM/'.length);
    else if (pathname.startsWith('/')) pathname = pathname.slice(1);
    if (
      url.search &&
      !(
        url.search === syntheticDocumentQuery &&
        (pathname === '' || pathname === 'index.html')
      )
    )
      return false;
    return pathname === '' || allowedFiles.has(pathname);
  };
  await context.route('**/*', (route) => {
    const request = route.request();
    const item = {
      context: label,
      url: request.url(),
      resourceType: request.resourceType(),
      method: request.method(),
    };
    if (request.method() === 'GET' && staticAllowed(request.url())) {
      network.staticRequests.push(item);
      return route.continue();
    }
    network.forbiddenRequests.push(item);
    return route.abort('blockedbyclient');
  });
  if (context.routeWebSocket)
    await context.routeWebSocket('**/*', (socket) => {
      network.socketAttempts.push({ context: label, url: socket.url() });
      socket.close();
    });
  context.on('page', (page) => {
    page.on('console', (message) => {
      if (message.type() === 'error')
        browserErrors.push({
          context: label,
          type: 'CONSOLE_ERROR',
          message: message.text(),
        });
    });
    page.on('pageerror', (error) =>
      browserErrors.push({
        context: label,
        type: error.name,
        message: error.message,
      }),
    );
    page.on('websocket', (socket) =>
      network.socketAttempts.push({ context: label, url: socket.url() }),
    );
    page.on('response', (response) => {
      if (response.status() >= 400)
        browserErrors.push({
          context: label,
          type: 'HTTP_ERROR',
          status: response.status(),
          url: response.url(),
        });
    });
  });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  return { context, page };
}
async function assertNoOverflow(page, name) {
  const layout = await page.evaluate(() => ({
    width: innerWidth,
    scroll: document.documentElement.scrollWidth,
    clipped: [
      ...document.querySelectorAll(
        'main button, main input, main textarea, main select, main p, main blockquote',
      ),
    ]
      .filter((element) => {
        const box = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return (
          box.width > 0 &&
          style.display !== 'none' &&
          (box.left < -1 || box.right > innerWidth + 1)
        );
      })
      .map(
        (element) => element.tagName + ':' + element.textContent?.slice(0, 30),
      ),
  }));
  check(
    name,
    layout.scroll <= layout.width + 1 && layout.clipped.length === 0,
    'LAYOUT_320_OR_DESKTOP',
    layout,
  );
}
const uiStorageKey = 'dodream.showcase.original-ui.v1';
const app = (screen, sample = 'water-journey') =>
  `/app/material/${sample}/${screen}`;
const uiStored = (page) =>
  page.evaluate(
    (key) => JSON.parse(sessionStorage.getItem(key) || 'null'),
    uiStorageKey,
  );
async function answerQuiz(page, first = '얼음', second = '증발') {
  await page.getByRole('textbox', { name: '답 입력란' }).fill(first);
  await page.getByRole('button', { name: '다음 문제', exact: true }).click();
  await heading(page, '문제 2');
  await page.getByRole('textbox', { name: '답 입력란' }).fill(second);
  await page.getByRole('button', { name: '채점하기', exact: true }).click();
  await heading(page, '퀴즈 완료!');
}
async function askExample(page) {
  await page.getByRole('button', { name: '말하기', exact: true }).click();
  await page.getByRole('dialog').waitFor();
  await page
    .getByRole('button', {
      name: '물이 충분히 차가워지면 무엇이 되나요?',
      exact: true,
    })
    .click();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByRole('button', { name: '참고 구간 보기' }).waitFor();
}
async function assertPhoneModal(page, label) {
  const bounded = await page.evaluate(() => {
    const a = document.querySelector('.app-viewport').getBoundingClientRect(),
      b = document.querySelector('[role=dialog]').getBoundingClientRect();
    return (
      b.left >= a.left - 1 &&
      b.right <= a.right + 1 &&
      b.top >= a.top - 1 &&
      b.bottom <= a.bottom + 1
    );
  });
  check(label + ': modal stays inside phone', bounded, 'PHONE_MODAL');
  await page.keyboard.press('Shift+Tab');
  check(
    label + ': modal keyboard focus contained',
    await page.evaluate(
      () => !!document.activeElement?.closest('[role=dialog]'),
    ),
    'KEYBOARD',
  );
  await page.keyboard.press('Tab');
  await page.keyboard.press('Escape');
  check(
    label + ': modal Escape closes',
    (await page.getByRole('dialog').count()) === 0,
    'KEYBOARD',
  );
}
async function normalJourney(prefix, screenshotsEnabled) {
  const label = prefix === '/' ? 'root' : 'subpath';
  const { context, page } = await newContext(label);
  step = label + ': original entry';
  await page.goto(
    server.origin +
      prefix +
      syntheticDocumentQuery +
      '#/?mode=live&role=TEACHER',
  );
  await page.getByTestId('start-student').filter({ visible: true }).waitFor();
  check(
    label + ': entry has no credentials',
    (await page.locator('input[type=password]').count()) === 0,
    'MODE_ISOLATION',
  );
  check(
    label + ': auth/query cannot change sample mode',
    (await page.getByText('샘플 체험', { exact: true }).count()) === 1,
    'MODE_ISOLATION',
  );
  if (screenshotsEnabled) await capture(page, '01-teacher-start');
  await page.getByTestId('start-student').filter({ visible: true }).click();
  await page.getByTestId('material-water-journey').waitFor();
  check(
    label + ': original app frame and two sample materials',
    (await page.getByTestId('student-phone').count()) === 1 &&
      (await page.locator('.app-material').count()) === 2,
  );
  if (screenshotsEnabled) await capture(page, '02-app-library');
  await page.getByTestId('material-water-journey').click();
  await heading(page, '물의 여행');
  await page.getByRole('button', { name: '다음 챕터', exact: true }).click();
  await page
    .getByRole('button', { name: '처음부터 듣기 챕터 처음부터', exact: true })
    .click();
  await textShown(page, '2. 하늘로 올라가는 물');
  check(
    label + ': selected chapter shared and persisted',
    (await uiStored(page)).positions['water-journey'] === 'water-2',
  );
  await page.reload();
  await textShown(page, '2. 하늘로 올라가는 물');
  await navigate(page, prefix, app('player') + '?section=water-1');
  const first = await page.getByTestId('player-paragraph').innerText();
  await page.getByRole('button', { name: '다음 섹션', exact: true }).click();
  await page.waitForFunction(
    (first) =>
      document.querySelector('[data-testid=player-paragraph]')?.textContent !==
      first,
    first,
  );
  check(
    label + ': next section changes actual text',
    (await page.getByTestId('player-paragraph').innerText()) !== first,
  );
  await page.goBack();
  await page.waitForFunction(
    (first) =>
      document.querySelector('[data-testid=player-paragraph]')?.textContent ===
      first,
    first,
  );
  check(
    label + ': browser back restores section',
    (await page.getByTestId('player-paragraph').innerText()) === first,
  );
  await page
    .getByRole('button', { name: '현재 챕터 저장하기', exact: true })
    .click();
  check(
    label + ': bookmark stored',
    (await uiStored(page)).bookmarks['water-journey'].includes('water-1'),
  );
  if (screenshotsEnabled) await capture(page, '03-app-player');
  await page.getByRole('link', { name: '질문하기', exact: true }).click();
  await askExample(page);
  check(
    label + ': question recorded for teacher',
    (await stored(page)).samples['water-journey'].questionIds.includes(
      'water-ice',
    ),
  );
  await page.getByRole('button', { name: '참고 구간 보기' }).click();
  await assertPhoneModal(page, label);
  check(
    label + ': modal returns focus',
    await page
      .getByRole('button', { name: '참고 구간 보기' })
      .evaluate((el) => el === document.activeElement),
    'KEYBOARD',
  );
  await page.getByRole('textbox', { name: '질문 입력창' }).fill(malicious);
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await textShown(page, '이 체험은 준비된 질문에만 답합니다.');
  check(
    label + ': unprepared/malicious question stays inert',
    (await page.evaluate(() => !window.__showcaseExecuted)) &&
      !(await stored(page)).samples['water-journey'].questionIds.includes(
        malicious,
      ),
    'INPUT_SAFETY',
  );
  if (screenshotsEnabled) await capture(page, '04-app-question');
  await navigate(page, prefix, app('questions'));
  await textShown(page, '총 1개의 질문');
  await navigate(page, prefix, app('quizzes'));
  await page.locator('.app-choice').first().click();
  await answerQuiz(page);
  check(
    label + ': written score two, no multiple choice',
    (await page.getByTestId('quiz-score').innerText()) === '2 / 2' &&
      (await page.locator('input[type=radio]').count()) === 0,
  );
  const result = (await uiStored(page)).quizzes['water-journey'].submissions[0];
  await page.reload();
  await heading(page, '퀴즈 완료!');
  check(
    label + ': result reload no duplicate',
    (await uiStored(page)).quizzes['water-journey'].submissions.length === 1,
  );
  await navigate(page, prefix, app('quiz') + '?question=2');
  await page.getByRole('button', { name: '결과 확인', exact: true }).click();
  check(
    label + ': duplicate submit immutable',
    JSON.stringify(
      (await uiStored(page)).quizzes['water-journey'].submissions,
    ) == JSON.stringify([result]),
  );
  if (screenshotsEnabled) await capture(page, '05-app-result');
  await navigate(page, prefix, '/teacher');
  await textShown(page, '내 자료 (2개)');
  if (screenshotsEnabled) await capture(page, '06-teacher-list');
  await navigate(page, prefix, '/teacher/student/demo-student');
  await textShown(page, '2개 정답');
  check(
    label + ': teacher sees shared written result',
    (await page.locator('.original-teacher').innerText()).includes('물의 여행'),
  );
  if (screenshotsEnabled) await capture(page, '07-teacher-results');
  await navigate(page, prefix, '/teacher/history/water-journey');
  await textShown(page, '물이 충분히 차가워지면 무엇이 되나요?');
  if (screenshotsEnabled) await capture(page, '08-teacher-chat');
  await navigate(page, prefix, '/teacher/editor/water-journey');
  const editor = page.getByRole('textbox', { name: '샘플 본문 편집' });
  await editor.fill(malicious);
  await page.getByRole('button', { name: '임시 저장', exact: true }).click();
  await textShown(page, '현재 탭에 본문을 임시 저장');
  check(
    label + ': editor markup remains text',
    (await editor.innerText()) === malicious &&
      (await editor.locator('img,script,a').count()) === 0,
    'INPUT_SAFETY',
  );
  await editor.fill(
    '같은 탭에서 고친 안전한 샘플 본문입니다.\n\n다음 문단입니다.',
  );
  await page.getByRole('button', { name: '임시 저장', exact: true }).click();
  await textShown(page, '현재 탭에 본문을 임시 저장');
  if (screenshotsEnabled) await capture(page, '09-teacher-editor');
  await navigate(page, prefix, app('player') + '?section=water-1');
  await textShown(page, '같은 탭에서 고친 안전한 샘플 본문입니다.');
  check(label + ': teacher edit appears in student', true);
  await navigate(page, prefix, '/app/settings');
  await page
    .getByRole('button', { name: '재생 속도 늘리기', exact: true })
    .click();
  await page.getByRole('checkbox', { name: '고대비 모드' }).check();
  await page
    .getByRole('button', { name: '글자 크기 늘리기', exact: true })
    .click();
  await page.locator('.app-high-contrast.app-font-12').waitFor();
  check(
    label + ': original settings active',
    (await uiStored(page)).settings.rate === 1.1 &&
      (await page.locator('.app-high-contrast.app-font-12').count()) === 1,
  );
  await page.getByRole('button', { name: '기본값으로 되돌리기' }).click();
  await navigate(page, prefix, app('result'));
  await page.getByRole('button', { name: '다시 풀기', exact: true }).click();
  await answerQuiz(page, '모래', '증발');
  check(
    label + ': explicit retry creates independent result',
    (await uiStored(page)).quizzes['water-journey'].submissions.length === 2 &&
      (await page.getByTestId('quiz-score').innerText()) === '1 / 2',
  );
  const independent = await newContext(label + '-independent');
  await navigate(independent.page, prefix, app('result'));
  await heading(independent.page, '아직 풀이 결과가 없습니다.');
  check(
    label + ': separate context has no shared history',
    true,
    'TAB_ISOLATION',
  );
  await independent.context.close();
  for (const [route, expected] of [
    ['/learn', '샘플'],
    ['/learn/water-journey?section=water-2', '2. 하늘로 올라가는 물'],
    ['/learn/water-journey/quiz', '문제 1'],
    ['/learn/water-journey/results/run-1', '이전 선택형 체험 기록'],
    ['/learn/__proto__/results/run-1', '이 탭에 저장된 이전 결과가 없습니다.'],
    [
      '/learn/constructor/results/run-1',
      '이 탭에 저장된 이전 결과가 없습니다.',
    ],
    [app('player', '__proto__'), '샘플 교재를 찾을 수 없습니다.'],
    [app('player', 'missing'), '샘플 교재를 찾을 수 없습니다.'],
    ['/unknown', '이 체험 화면을 찾을 수 없습니다.'],
  ]) {
    await navigate(page, prefix, route);
    await textShown(page, expected);
    check(label + ': route compatibility ' + route, true, 'ROUTING');
  }
  await navigate(
    page,
    prefix,
    app('player') + '?section=unknown&paragraph=javascript:alert(1)',
  );
  check(
    label + ': invalid chapter/index uses safe first content',
    (await page.getByTestId('player-paragraph').innerText()).includes(
      '고친 안전한',
    ),
    'INPUT_SAFETY',
  );
  await navigate(page, prefix, app('playback', 'recycling-day'));
  await heading(page, '생활 속 분리배출');
  check(
    label + ': second material remains independent',
    (await uiStored(page)).quizzes['recycling-day'].submissions.length === 0,
  );
  if (screenshotsEnabled) {
    await page.setViewportSize({ width: 320, height: 640 });
    await navigate(page, prefix, '/app/library');
    await assertNoOverflow(page, '320px original library');
    await capture(page, '10-mobile-library');
    await navigate(page, prefix, app('question'));
    await page.getByRole('button', { name: '말하기', exact: true }).click();
    await assertPhoneModal(page, '320px');
    await assertNoOverflow(page, '320px question');
    await page.setViewportSize({ width: 1280, height: 600 });
    await navigate(page, prefix, app('player'));
    await assertNoOverflow(page, 'short desktop player');
    await capture(page, '11-short-desktop-player');
  }
  await page.getByTestId('reset-demo').click();
  await page.getByTestId('start-student').filter({ visible: true }).waitFor();
  check(
    label + ': reset removes only both owned sample keys',
    await page.evaluate(
      ({ a, b, sentinel }) =>
        sessionStorage.getItem(a) === null &&
        sessionStorage.getItem(b) === null &&
        sessionStorage.getItem('accessToken') === sentinel &&
        localStorage.getItem('accessToken') === sentinel &&
        !!sessionStorage.getItem('unrelated'),
      { a: storageKey, b: uiStorageKey, sentinel },
    ),
    'OWNED_STORAGE',
  );
  check(
    label + ': no payload execution',
    await page.evaluate(() => !window.__showcaseExecuted),
    'INPUT_SAFETY',
  );
  await context.close();
}
async function storageBoundaries() {
  for (const key of [storageKey, uiStorageKey])
    for (const [label, state] of [
      ['json', '{broken'],
      ['version', '{"version":999}'],
      ['oversize', 'x'.repeat(150000)],
      ['unknown', '{"version":1,"samples":{"unknown":{}}}'],
    ]) {
      step = 'storage ' + key + label;
      const { context, page } = await newContext(step, {
        state,
        stateKey: key,
      });
      await navigate(page, '/DO-DREAM/', '/app/library');
      await textShown(page, '처음부터');
      check(
        step,
        (await page.locator('.app-material').count()) === 2,
        'STORAGE_RECOVERY',
      );
      await context.close();
    }
  const { context, page } = await newContext('storage denied', {
    storageUnavailable: true,
  });
  await navigate(page, '/', app('quiz'));
  await answerQuiz(page);
  await textShown(page, '임시 저장소');
  check(
    'denied storage completes written journey',
    (await page.getByTestId('quiz-score').innerText()) === '2 / 2',
    'STORAGE_RECOVERY',
  );
  await page.getByTestId('reset-demo').click();
  await context.close();
}
async function quotaStorageBoundary() {
  const { context, page } = await newContext('quota');
  await navigate(page, '/', app('quiz'));
  await page.getByRole('textbox', { name: '답 입력란' }).fill('얼음');
  await page.evaluate(() => {
    const native = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (key.startsWith('dodream.showcase.'))
        throw new DOMException('Synthetic quota', 'QuotaExceededError');
      return native.call(this, key, value);
    };
  });
  await page.getByRole('button', { name: '다음 문제', exact: true }).click();
  await heading(page, '문제 2');
  await page.getByRole('textbox', { name: '답 입력란' }).fill('증발');
  await page.getByRole('button', { name: '채점하기', exact: true }).click();
  await heading(page, '퀴즈 완료!');
  await textShown(page, '임시 저장소');
  check('quota failure keeps memory journey usable', true, 'STORAGE_RECOVERY');
  await page.getByTestId('reset-demo').click();
  check(
    'quota reset removes stale owned storage',
    (await uiStored(page)) === null,
    'OWNED_STORAGE',
  );
  await context.close();
}
async function keyboardJourney() {
  step = 'keyboard';
  const { context, page } = await newContext('keyboard');
  await navigate(page, '/', '/app/library');
  await page.getByTestId('material-water-journey').focus();
  await page.keyboard.press('Enter');
  await heading(page, '물의 여행');
  check('keyboard enters app material', true, 'KEYBOARD');
  await navigate(page, '/', app('question'));
  await page.getByRole('button', { name: '말하기', exact: true }).focus();
  await page.keyboard.press('Enter');
  await assertPhoneModal(page, 'keyboard');
  await navigate(page, '/', app('quiz'));
  await page.getByRole('textbox', { name: '답 입력란' }).fill('얼음');
  await page.keyboard.press('Enter');
  await heading(page, '문제 2');
  await page.getByRole('textbox', { name: '답 입력란' }).fill('증발');
  await page.keyboard.press('Enter');
  await heading(page, '퀴즈 완료!');
  check('keyboard written answer and submit', true, 'KEYBOARD');
  await context.close();
}
async function speechBoundary() {
  step = 'controlled speech';
  const { context, page } = await newContext('controlled-local-speech', {
    speech: 'local',
  });
  await navigate(page, '/', app('player'));
  await page.getByRole('button', { name: '재생', exact: true }).click();
  let before = await page.evaluate(() => ({
    spoken: window.__showcaseSpeech.utterances.length,
    canceled: window.__showcaseSpeech.canceled,
  }));
  check(
    'controlled local-only speech starts',
    before.spoken === 1,
    'CONTROLLED_SPEECH_EVENTS',
  );
  await page.getByRole('button', { name: '일시정지', exact: true }).click();
  await page.getByRole('button', { name: '재생', exact: true }).click();
  check(
    'controlled pause/resume',
    await page.evaluate(
      () =>
        window.__showcaseSpeech.paused === 1 &&
        window.__showcaseSpeech.resumed === 1,
    ),
    'CONTROLLED_SPEECH_EVENTS',
  );
  await page.getByRole('button', { name: '다음 섹션', exact: true }).click();
  await page.waitForFunction(
    (before) => window.__showcaseSpeech.canceled > before.canceled,
    before,
  );
  await page.evaluate(() => {
    window.__showcaseSpeech.utterances[0].onend?.();
    window.__showcaseSpeech.utterances[0].onerror?.();
  });
  check(
    'late speech cannot continue after paragraph navigation',
    await page.evaluate(
      (before) =>
        window.__showcaseSpeech.utterances.length === before.spoken &&
        window.__showcaseSpeech.canceled > before.canceled,
      before,
    ),
    'CONTROLLED_SPEECH_EVENTS',
  );
  await page.getByRole('button', { name: '재생', exact: true }).click();
  before = await page.evaluate(() => ({
    spoken: window.__showcaseSpeech.utterances.length,
    canceled: window.__showcaseSpeech.canceled,
  }));
  await page.evaluate(() => window.__showcaseSpeech.utterances[0].onerror?.());
  check(
    'old speech error cannot stop current playback',
    await page
      .getByRole('button', { name: '일시정지', exact: true })
      .isEnabled(),
    'CONTROLLED_SPEECH_EVENTS',
  );
  await page.getByTestId('reset-demo').click();
  await page.evaluate(() => {
    for (const u of window.__showcaseSpeech.utterances) {
      u.onend?.();
      u.onerror?.();
    }
  });
  check(
    'late speech cannot continue after reset',
    await page.evaluate(
      (before) =>
        window.__showcaseSpeech.utterances.length === before.spoken &&
        window.__showcaseSpeech.canceled > before.canceled,
      before,
    ),
    'CONTROLLED_SPEECH_EVENTS',
  );
  await context.close();
  for (const speech of ['remote-only', 'voices-throw']) {
    const probe = await newContext('controlled-' + speech, { speech });
    await navigate(probe.page, '/DO-DREAM/', app('player'));
    await probe.page.getByRole('button', { name: '재생', exact: true }).click();
    await probe.page.getByRole('dialog').waitFor();
    check(
      speech + ' shows honest limit without invoking speech',
      await probe.page.evaluate(
        () => window.__showcaseSpeech.utterances.length === 0,
      ),
      'CONTROLLED_SPEECH_EVENTS',
    );
    await probe.context.close();
  }
  speechObservations.push({
    actualAudioListening: 'NOT_RUN',
    scope:
      'Synthetic platform events only; no microphone and no audible output claimed.',
  });
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
  check(
    'artifact unchanged during single acceptance',
    artifactDigestBefore === (await digestFiles(artifact)),
    'ACCEPTANCE_INTEGRITY',
  );
  check(
    'application source unchanged during single acceptance',
    sourceDigestBefore ===
      (await digestFiles(path.join(repository, 'fe-web/src'))),
    'ACCEPTANCE_INTEGRITY',
  );
  check(
    'no browser application errors',
    browserErrors.length === 0,
    'BROWSER',
    browserErrors,
  );
  check(
    'API/external/websocket/eventsource/beacon request attempts are zero',
    network.forbiddenRequests.length === 0 &&
      network.apiAttempts.length === 0 &&
      network.socketAttempts.length === 0 &&
      network.cspViolations.length === 0 &&
      network.microphoneAttempts.length === 0,
    'NETWORK',
  );
  check(
    'real static files were requested',
    network.staticRequests.length > 0,
    'NETWORK',
  );
}

await fs.mkdir(captureDirectory, { recursive: true });
let interrupt;
const interrupted = new Promise((_resolve, reject) => {
  interrupt = reject;
});
const deadline = setTimeout(
  () =>
    interrupt(new Error('Browser acceptance exceeded its 180 second limit')),
  180000,
);
const terminate = () =>
  interrupt(
    new Error(
      'Browser acceptance interrupted; cleaning up only its own browser and static server',
    ),
  );
process.once('SIGTERM', terminate);
process.once('SIGINT', terminate);
try {
  await Promise.race([runAcceptance(), interrupted]);
} catch (error) {
  checks.push({
    name: step,
    status: 'FAIL',
    category: 'HARNESS_OR_PRODUCT',
    errorType: error.constructor.name,
    message: error.message,
  });
  process.exitCode = 1;
} finally {
  clearTimeout(deadline);
  process.removeListener('SIGTERM', terminate);
  process.removeListener('SIGINT', terminate);
  await browser?.close();
  await server?.close();
  const result = {
    status: process.exitCode ? 'FAIL' : 'PASS',
    timestamp: stamp,
    durationMs: Date.now() - startedAt,
    runtime: {
      node: process.version,
      platform: process.platform,
      browser: 'Google Chrome',
      browserVersion,
      channel: 'chrome',
      headless: true,
    },
    localOrigin: server?.origin,
    artifactDigest: artifactDigestBefore,
    sourceDigest: sourceDigestBefore,
    checks,
    screenshots,
    speechObservations,
    counts: {
      checks: checks.length,
      staticRequests: network.staticRequests.length,
      forbiddenRequestAttempts: network.forbiddenRequests.length,
      apiAttemptsBeforeCsp: network.apiAttempts.length,
      webSocketAttempts: network.socketAttempts.length,
      cspViolations: network.cspViolations.length,
      microphoneAttempts: network.microphoneAttempts.length,
    },
    network,
    browserErrors,
    scope:
      'Built static artifact only; fresh independent Chrome contexts; no API responses mocked; no backend services started.',
    actualAudioListening: 'NOT_RUN',
    voiceOver: 'NOT_RUN',
    backendData: 'NOT_TOUCHED',
    remoteCiExecution: 'NOT_RUN',
  };
  const json = JSON.stringify(result, null, 2) + '\n';
  await fs.writeFile(
    path.join(evidence, `showcase-browser-${stamp}.json`),
    json,
    { flag: 'wx' },
  );
  await fs.writeFile(path.join(evidence, 'showcase-browser-latest.json'), json);
  console.log(
    JSON.stringify({
      status: result.status,
      ...result.counts,
      failed: checks.filter((check) => check.status === 'FAIL'),
      evidence: path.relative(
        repository,
        path.join(evidence, `showcase-browser-${stamp}.json`),
      ),
    }),
  );
}

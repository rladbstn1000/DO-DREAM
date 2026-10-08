/** UI-only journey shared by local rehearsal and real public acceptance. No response mocks. */
import { checkPortfolioPolish } from './showcase-portfolio-polish.mjs';

const stateKeys = [
  'dodream.showcase.v1.state',
  'dodream.showcase.original-ui.v1',
];

export async function runPublicUiAcceptance({
  context,
  pageUrl,
  check,
  screenshot,
  settleResponses = async () => {},
}) {
  const material = (screen) => `/app/material/water-journey/${screen}`;
  const navigate = async (page, route) => {
    await page.goto(pageUrl + '#' + route);
    await page.locator('#showcase-main').waitFor();
  };
  async function wordLayout(page, selector, label) {
    await page.locator(selector).first().waitFor();
    await page.evaluate(() => document.fonts.ready);
    const result = await page.locator(selector).evaluateAll((elements) =>
      elements.map((element) => {
        const style = getComputedStyle(element),
          split = [];
        const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode()))
          for (const match of node.textContent.matchAll(/[가-힣]{2,8}/g)) {
            const range = document.createRange();
            range.setStart(node, match.index);
            range.setEnd(node, match.index + match[0].length);
            const lines = new Set(
              [...range.getClientRects()]
                .filter((r) => r.width > 0)
                .map((r) => Math.round(r.top)),
            );
            const parent = node.parentElement,
              computed = getComputedStyle(parent),
              measure = document.createElement('canvas').getContext('2d');
            measure.font = `${computed.fontWeight} ${computed.fontSize} ${computed.fontFamily}`;
            const available =
              parent.clientWidth -
              parseFloat(computed.paddingLeft) -
              parseFloat(computed.paddingRight);
            if (
              lines.size > 1 &&
              measure.measureText(match[0]).width <= available + 1
            )
              split.push(match[0]);
          }
        return {
          keepAll: style.wordBreak === 'keep-all',
          fallback: style.overflowWrap === 'anywhere',
          split,
          overflow: element.scrollWidth > element.clientWidth + 1,
        };
      }),
    );
    check(
      label + ': Korean words keep together with an overlong-word fallback',
      result.length > 0 &&
        result.every(
          (r) => r.keepAll && r.fallback && !r.overflow && r.split.length === 0,
        ),
      'PUBLIC_WORD_WRAP',
      result,
    );
  }
  async function quizLayout(page, label) {
    await wordLayout(page, '.app-quiz-choice strong', label);
    const cards = await page.locator('.app-quiz-choice').evaluateAll((cards) =>
      cards.map((card) => {
        const title = card.querySelector('strong'),
          badge = card.querySelector('.app-quiz-badge');
        const t = title.getBoundingClientRect(),
          b = badge.getBoundingClientRect(),
          c = card.getBoundingClientRect(),
          style = getComputedStyle(title);
        return {
          fullTitle:
            style.textOverflow !== 'ellipsis' &&
            style.webkitLineClamp === 'none',
          separate: t.right <= b.left + 1,
          contained: t.bottom <= c.bottom && b.right <= c.right,
          badgeWidth: b.width,
        };
      }),
    );
    check(
      label + ': complete quiz titles and badges have separate space',
      cards.length === 2 &&
        cards.every(
          (c) => c.fullTitle && c.separate && c.contained && c.badgeWidth >= 50,
        ),
      'PUBLIC_LAYOUT',
      cards,
    );
  }
  async function playbackBottom(page, label, capture = false) {
    await navigate(page, material('playback'));
    const scroller = page.locator('.app-playback-content');
    await scroller.waitFor();
    await scroller.evaluate((el) => {
      el.scrollTop = el.scrollHeight;
    });
    const bottom = await scroller.evaluate((el) => {
      const box = el.getBoundingClientRect();
      return {
        atEnd: Math.abs(el.scrollHeight - el.clientHeight - el.scrollTop) < 2,
        menus: [...el.querySelectorAll('.app-choice')].slice(-2).map((menu) => {
          const r = menu.getBoundingClientRect();
          return {
            text: menu.textContent,
            visible: r.top >= box.top - 1 && r.bottom <= box.bottom + 1,
          };
        }),
      };
    });
    check(
      label +
        ': saved and final quiz menu are fully available at scroll bottom',
      bottom.atEnd &&
        bottom.menus.length === 2 &&
        bottom.menus.every((m) => m.visible) &&
        bottom.menus[0].text.includes('저장 목록') &&
        bottom.menus[1].text.includes('퀴즈 풀기'),
      'PUBLIC_SCROLL',
      bottom,
    );
    if (capture) await screenshot(page, 'public-playback-bottom');
    await page
      .getByRole('link', { name: '저장 목록 저장한 내용 보기', exact: true })
      .click();
    await page
      .getByRole('heading', { name: '저장 목록', exact: true })
      .waitFor();
    await navigate(page, material('playback'));
    await page
      .getByRole('button', { name: '이어서 듣기 마지막 위치부터', exact: true })
      .focus();
    for (let n = 0; n < 4; n++) await page.keyboard.press('Tab');
    const focus = await page.evaluate(() => {
      const el = document.activeElement,
        r = el.getBoundingClientRect(),
        scroller = el.closest('.app-scroll')?.getBoundingClientRect(),
        style = getComputedStyle(el);
      return {
        text: el.textContent,
        visible:
          !!scroller &&
          r.top >= Math.max(40, scroller.top) - 1 &&
          r.bottom <= Math.min(innerHeight, scroller.bottom) + 1,
        outlined:
          (style.outlineStyle !== 'none' &&
            parseFloat(style.outlineWidth) > 0) ||
          style.boxShadow !== 'none',
      };
    });
    check(
      label + ': Tab reveals the full final menu with visible focus',
      focus.text.includes('퀴즈 풀기') && focus.visible && focus.outlined,
      'PUBLIC_KEYBOARD',
      focus,
    );
    await page.keyboard.press('Enter');
    await page.getByText('전체 퀴즈 목록', { exact: true }).waitFor();
    check(
      label + ': final menu accepts keyboard activation',
      page.url().endsWith(material('quizzes')),
      'PUBLIC_KEYBOARD',
    );
  }
  async function keyboardActivate(page, target) {
    for (let count = 0; count < 80; count++) {
      const state = await target.evaluate((element) => {
        const style = getComputedStyle(element);
        return {
          focused: document.activeElement === element,
          visible:
            (style.outlineStyle !== 'none' &&
              parseFloat(style.outlineWidth) > 0) ||
            style.boxShadow !== 'none',
        };
      });
      if (state.focused) {
        check(
          'keyboard target has visible focus',
          state.visible,
          'PUBLIC_KEYBOARD',
        );
        await page.keyboard.press('Enter');
        return;
      }
      await page.keyboard.press('Tab');
    }
    throw new Error('Public keyboard target cannot be reached');
  }
  const desktop = await context('desktop');
  const page = desktop.page;
  const response = await page.goto(pageUrl);
  const observedUrl = page.url();
  await page.getByText('샘플 체험', { exact: true }).waitFor();
  check(
    'anonymous HTTPS entry has expected URL and HTML',
    response?.status() === 200 &&
      observedUrl === pageUrl &&
      (await page.getByText('샘플 체험', { exact: true }).count()) === 1,
  );
  check(
    'original teacher start uses sample entry without credentials',
    (await page.locator('.original-teacher.original-join').count()) === 1 &&
      (await page.locator('input[type=password]').count()) === 0,
  );
  await screenshot(page, 'public-teacher-start');
  await keyboardActivate(
    page,
    page.getByTestId('start-teacher').filter({ visible: true }),
  );
  await page.getByText('내 자료 (2개)', { exact: true }).waitFor();
  check(
    'original teacher material list retains the two public sample rows',
    (await page.locator('.cl-material-item').count()) === 2,
  );
  await screenshot(page, 'public-teacher-materials');
  for (const width of [1280, 1366, 1440]) {
    await page.setViewportSize({ width, height: 920 });
    await navigate(page, '/teacher/classroom/1-1');
    await page
      .getByRole('heading', { name: '공유된 학습 자료', exact: true })
      .waitFor();
    await page.evaluate(() => document.fonts.ready);
    const headers = await page
      .locator('.classroom-page .cl-card-head')
      .evaluateAll((heads) =>
        heads.map((head) => {
          const title = head.querySelector('h3'),
            search = head.querySelector('.cl-input-wrap'),
            sort = head.querySelector('.cl-sort-btn');
          const lines = (el) => {
            const range = document.createRange();
            range.selectNodeContents(el);
            return new Set(
              [...range.getClientRects()]
                .filter((r) => r.width > 0)
                .map((r) => Math.round(r.top)),
            ).size;
          };
          const boxes = [title, search, sort].map((el) =>
              el.getBoundingClientRect(),
            ),
            panel = head.closest('.cl-card').getBoundingClientRect();
          const overlap = (a, b) =>
            a.left < b.right - 1 &&
            a.right > b.left + 1 &&
            a.top < b.bottom - 1 &&
            a.bottom > b.top + 1;
          return {
            text: title.textContent,
            titleLines: lines(title),
            sortLines: lines(sort.querySelector('span')),
            fontSize: getComputedStyle(title).fontSize,
            contained: boxes.every(
              (r) => r.left >= panel.left && r.right <= panel.right,
            ),
            overlap:
              overlap(boxes[0], boxes[1]) ||
              overlap(boxes[0], boxes[2]) ||
              overlap(boxes[1], boxes[2]),
          };
        }),
      );
    check(
      `teacher ${width}: title, student count, search and sort fit without splitting`,
      headers.length === 2 &&
        headers.every(
          (h) =>
            h.titleLines === 1 &&
            h.sortLines === 1 &&
            h.fontSize === '18px' &&
            h.contained &&
            !h.overlap,
        ),
      'PUBLIC_LAYOUT',
      headers,
    );
    if (width === 1280) await screenshot(page, 'public-teacher-classroom');
  }
  await page.setViewportSize({ width: 1280, height: 920 });
  await navigate(page, '/teacher/editor/water-journey');
  await page
    .getByRole('textbox', { name: '샘플 본문 편집', exact: true })
    .waitFor();
  check(
    'original teacher editor has the public lesson and save controls',
    (await page
      .getByRole('button', { name: '물의 여행', exact: true })
      .count()) === 1 &&
      (await page
        .getByRole('button', { name: '임시 저장', exact: true })
        .count()) === 1,
  );
  await screenshot(page, 'public-teacher-editor');
  await navigate(page, '/teacher/student/demo-student');
  await page
    .getByText('퀴즈 결과가 없습니다. 학생 앱 체험에서 문제를 풀어보세요.', {
      exact: true,
    })
    .waitFor();
  check(
    'fresh sample has no fabricated results and zero progress',
    (await page.locator('.sr-quiz-card').count()) === 0 &&
      (await page.locator('.sr-sidebar-stats').innerText()).includes('0%'),
  );
  await navigate(page, '/');
  await keyboardActivate(
    page,
    page.getByTestId('start-student').filter({ visible: true }),
  );
  // /app mounts its phone before the index route redirects to /app/library.
  // Wait for the destination card before checking the unchanged layout/count.
  await page.getByTestId('material-water-journey').waitFor();
  check(
    'student library is inside the original 392px phone',
    (await page
      .locator('.app-viewport')
      .evaluate(
        (el) =>
          el.clientWidth === 392 && getComputedStyle(el).transform === 'none',
      )) && (await page.locator('.app-material').count()) === 2,
    'PUBLIC_LAYOUT',
  );
  await screenshot(page, 'public-student-library');
  await keyboardActivate(page, page.getByTestId('material-water-journey'));
  await playbackBottom(page, '392px', true);
  await quizLayout(page, '392px');
  await screenshot(page, 'public-student-quizzes');
  await navigate(page, material('playback'));
  await page
    .getByRole('button', { name: '처음부터 듣기 챕터 처음부터', exact: true })
    .click();
  await page
    .getByRole('heading', { name: '1. 얼음과 물', exact: true })
    .waitFor();
  await wordLayout(page, '.app-paragraph', '392px player');
  await screenshot(page, 'public-student-player');
  await page.getByRole('button', { name: '다음 섹션', exact: true }).click();
  await page.getByRole('button', { name: '학습 완료', exact: true }).click();
  await page
    .getByRole('heading', { name: '2. 하늘로 올라가는 물', exact: true })
    .waitFor();
  check(
    'original app library, playback choice and player navigation work',
    page.url().includes('/app/material/water-journey/player?section=water-2'),
  );
  await page.reload();
  await page
    .getByRole('heading', { name: '2. 하늘로 올라가는 물', exact: true })
    .waitFor();
  check(
    'nested hash player route survives refresh',
    page.url().includes('section=water-2'),
  );
  await page.goBack();
  await page
    .getByRole('heading', { name: '1. 얼음과 물', exact: true })
    .waitFor();
  check(
    'browser back restores the earlier chapter and paragraph',
    page.url().includes('section=water-1&paragraph=1'),
  );
  await page.getByRole('link', { name: '질문하기', exact: true }).click();
  await wordLayout(page, '.app-welcome', '392px question');
  await page.getByRole('button', { name: '말하기', exact: true }).click();
  const exampleDialog = page.getByRole('dialog', {
    name: '예시 질문 선택',
    exact: true,
  });
  await exampleDialog
    .getByRole('button', {
      name: '물이 충분히 차가워지면 무엇이 되나요?',
      exact: true,
    })
    .click();
  await page.getByRole('button', { name: '확인', exact: true }).click();
  await page.getByText('준비된 예시 답변', { exact: true }).waitFor();
  check(
    'question uses explicit example selection with no microphone',
    (await page.locator('.app-answer-bubble').innerText())
      .replace(/\s+/g, ' ')
      .includes(
        '물이 충분히 차가워지면 단단한 얼음이 됩니다. 얼음을 따뜻한 곳에 두면 다시 물로 바뀝니다.',
      ),
  );
  const source = page.getByRole('button', {
    name: '참고 구간 보기',
    exact: true,
  });
  await source.click();
  const sourceDialog = page.getByRole('dialog', {
    name: '참고 구간 · 얼음과 물',
    exact: true,
  });
  await sourceDialog.waitFor();
  check(
    'source excerpt matches the same public lesson',
    (await sourceDialog.locator('p').first().innerText()) ===
      '물이 충분히 차가워지면 단단한 얼음이 됩니다. 얼음을 따뜻한 곳에 두면 다시 물이 됩니다.',
  );
  check(
    'source modal stays inside the phone frame',
    await sourceDialog.evaluate((element) => {
      const modal = element.getBoundingClientRect(),
        phone = document
          .querySelector('[data-testid="student-phone"]')
          .getBoundingClientRect();
      return (
        modal.left >= phone.left &&
        modal.right <= phone.right &&
        modal.top >= phone.top &&
        modal.bottom <= phone.bottom
      );
    }),
    'PUBLIC_LAYOUT',
  );
  await page.keyboard.press('Escape');
  await sourceDialog.waitFor({ state: 'hidden' });
  check(
    'source closes by keyboard and returns focus',
    await source.evaluate((element) => element === document.activeElement),
    'PUBLIC_KEYBOARD',
  );
  await screenshot(page, 'public-student-question');
  await page.getByRole('link', { name: '뒤로가기', exact: true }).click();
  await page.getByRole('link', { name: '뒤로가기', exact: true }).click();
  await page
    .getByRole('link', { name: '퀴즈 풀기 학습 내용 확인', exact: true })
    .click();
  await page
    .getByRole('link', {
      name: '1. 물이 충분히 차가워지면 무엇이 되나요? 단답형',
      exact: true,
    })
    .click();
  await wordLayout(page, '.app-quiz-prompt', '392px quiz prompt');
  await page
    .getByRole('button', { name: '음성으로 답하기', exact: true })
    .click();
  await page
    .getByText(
      '마이크를 사용하지 않습니다. 예시 답을 입력한 뒤 직접 수정할 수 있습니다.',
      { exact: true },
    )
    .waitFor();
  await page.keyboard.press('Escape');
  await page
    .getByRole('textbox', { name: '답 입력란', exact: true })
    .fill('얼음');
  await page.getByRole('button', { name: '다음 문제', exact: true }).click();
  await page.getByRole('heading', { name: '문제 2', exact: true }).waitFor();
  await page
    .getByRole('textbox', { name: '답 입력란', exact: true })
    .fill('증발');
  await page.getByRole('button', { name: '채점하기', exact: true }).click();
  await page
    .getByRole('heading', { name: '퀴즈 완료!', exact: true })
    .waitFor();
  check(
    'original written quiz produces its deterministic example result',
    page.url().endsWith('/app/material/water-journey/result') &&
      (await page.getByTestId('quiz-score').innerText()).replace(/\s+/g, '') ===
        '2/2',
  );
  await page.reload();
  await page.getByTestId('quiz-score').waitFor();
  check(
    'result direct URL and refresh preserve same-tab state',
    (await page.getByText('예시 판정 · 1회차', { exact: true }).count()) === 1,
  );
  await screenshot(page, 'public-result');
  await page.getByRole('link', { name: '교사 웹', exact: true }).click();
  await page.locator('a[href="#/teacher/classroom/1-1"]').click();
  await page.locator('a[href="#/teacher/student/demo-student"]').click();
  const resultCard = page
    .locator('.sr-quiz-card')
    .filter({ hasText: '물의 여행 · 1회' });
  await resultCard.waitFor();
  check(
    'original teacher student screen shows the same-tab written result',
    (await resultCard.innerText()).includes('2개 정답'),
  );
  check(
    'one question and one quiz keep the existing partial progress definition',
    (await page.locator('.sr-qa-item').count()) === 1 &&
      (await page.locator('.sr-quiz-card').count()) === 1 &&
      (await page.locator('.sr-sidebar-stats').innerText()).includes('50%'),
  );
  await screenshot(page, 'public-teacher-student-history');
  await page.locator('a[href="#/teacher/history/water-journey"]').click();
  await page.getByText('준비된 샘플 답변', { exact: true }).waitFor();
  check(
    'teacher conversation screen shows the same-tab question',
    (await page.locator('.ch-user .ch-bubble').innerText()).includes(
      '물이 충분히 차가워지면 무엇이 되나요?',
    ),
  );
  const mobile = await context('narrow-independent', {
    width: 320,
    height: 780,
  });
  await mobile.page.goto(pageUrl + '#/app/material/water-journey/result');
  await mobile.page
    .getByRole('heading', { name: '아직 풀이 결과가 없습니다.', exact: true })
    .waitFor();
  check(
    'independent anonymous context has no first context result',
    (await mobile.page.getByTestId('quiz-score').count()) === 0,
  );
  await mobile.page.goto(
    pageUrl + '#/app/material/water-journey/player?section=water-2',
  );
  await mobile.page
    .getByRole('heading', { name: '2. 하늘로 올라가는 물', exact: true })
    .waitFor();
  await mobile.page
    .getByRole('link', { name: '질문하기', exact: true })
    .click();
  await mobile.page
    .getByRole('textbox', { name: '질문 입력창', exact: true })
    .fill('젖은 수건이 마르는 까닭은 무엇인가요?');
  await mobile.page.getByRole('button', { name: '확인', exact: true }).click();
  await mobile.page.getByText('준비된 예시 답변', { exact: true }).waitFor();
  const layout = await mobile.page.evaluate(() => ({
    width: innerWidth,
    scroll: document.documentElement.scrollWidth,
    clipped: [
      ...document.querySelectorAll(
        '.app-screen button, .app-screen input, .app-screen textarea, .app-screen p',
      ),
    ].filter((element) => {
      const box = element.getBoundingClientRect();
      return box.width > 0 && (box.left < -1 || box.right > innerWidth + 1);
    }).length,
  }));
  check(
    '320 CSS px public phone reading and question controls fit',
    layout.scroll <= layout.width + 1 && layout.clipped === 0,
    'PUBLIC_LAYOUT',
    layout,
  );
  await screenshot(mobile.page, 'public-narrow');
  const malicious =
    '<img src="https://showcase-forbidden.invalid/pixel" onerror="window.__showcaseExecuted=true"> javascript:alert(1)';
  await mobile.page
    .getByRole('textbox', { name: '질문 입력창', exact: true })
    .fill(malicious);
  await mobile.page.getByRole('button', { name: '확인', exact: true }).click();
  await mobile.page
    .getByText('이 체험은 준비된 질문에만 답합니다.', { exact: false })
    .waitFor();
  check(
    'public question markup is displayed as inert user input without execution',
    (await mobile.page
      .getByRole('textbox', { name: '질문 입력창', exact: true })
      .inputValue()) === malicious &&
      (await mobile.page.evaluate(
        () =>
          !window.__showcaseExecuted &&
          !document.querySelector('img[src*="showcase-forbidden"]'),
      )),
    'PUBLIC_INPUT_SAFETY',
  );
  await settleResponses();
  await mobile.context.close();
  for (const [label, viewport, large] of [
    ['392px-large', { width: 1280, height: 920 }, true],
    ['320px', { width: 320, height: 640 }, false],
    ['320px-large', { width: 320, height: 640 }, true],
  ]) {
    const focused = await context(label, viewport);
    if (large) {
      await navigate(focused.page, '/app/settings');
      await focused.page
        .getByRole('button', { name: '글자 크기 늘리기', exact: true })
        .click();
      await focused.page.locator('.app-font-12').waitFor();
      await focused.page
        .getByRole('button', { name: '글자 크기 늘리기', exact: true })
        .click();
      await focused.page.locator('.app-font-15').waitFor();
    }
    for (const [screen, selector] of [
      ['player', '.app-paragraph'],
      ['question', '.app-welcome'],
      ['quiz', '.app-quiz-prompt'],
    ]) {
      await navigate(focused.page, material(screen));
      await wordLayout(focused.page, selector, label + ' ' + screen);
    }
    await navigate(focused.page, material('quizzes'));
    await quizLayout(focused.page, label);
    check(
      label + ': phone contents fit without horizontal overflow or scaling',
      await focused.page
        .locator('.app-viewport')
        .evaluate(
          (el) =>
            el.scrollWidth <= el.clientWidth + 1 &&
            document.documentElement.scrollWidth <= innerWidth + 1 &&
            getComputedStyle(el).transform === 'none',
        ),
      'PUBLIC_LAYOUT',
    );
    await playbackBottom(focused.page, label);
    await focused.page.setViewportSize({ width: viewport.width, height: 500 });
    await playbackBottom(focused.page, label + '-short');
    await settleResponses();
    await focused.context.close();
  }
  await navigate(page, '/teacher/editor/water-journey');
  const editor = page.getByRole('textbox', {
    name: '샘플 본문 편집',
    exact: true,
  });
  await editor.fill(malicious);
  await page.getByRole('button', { name: '임시 저장', exact: true }).click();
  await page
    .getByText('현재 탭에 본문을 임시 저장', { exact: false })
    .waitFor();
  check(
    'public editor persists markup as plain text only',
    (await editor.innerText()) === malicious &&
      (await editor.locator('img,script,a').count()) === 0 &&
      (await page.evaluate(() => !window.__showcaseExecuted)),
    'PUBLIC_INPUT_SAFETY',
  );
  for (const [route, expected, destination] of [
    ['/learn', '샘플', '/app/library'],
    [
      '/learn/water-journey?section=water-2',
      '2. 하늘로 올라가는 물',
      material('player') + '?section=water-2',
    ],
    ['/learn/water-journey/quiz', '문제 1', material('quiz')],
    [
      '/learn/water-journey/results/run-1',
      '이전 선택형 체험 기록',
      '/learn/water-journey/results/run-1',
    ],
  ]) {
    await navigate(page, route);
    await page.getByRole('heading', { name: expected, exact: true }).waitFor();
    await page.waitForURL(pageUrl + '#' + destination);
    check(
      'legacy public hash route remains accessible: ' + route,
      new URL(page.url()).hash === '#' + destination &&
        (route !== '/learn' ||
          (await page.locator('.app-material').count()) === 2),
      'PUBLIC_ROUTING',
    );
  }
  await page.evaluate(() =>
    sessionStorage.setItem('publication.unrelated', 'keep'),
  );
  await page.getByTestId('reset-demo').click();
  await page.getByTestId('start-student').filter({ visible: true }).waitFor();
  // Reset mounts CSS background artwork after the document's original load event.
  // Wait for these actual static images before leaving the entry route, otherwise
  // navigation can cancel an in-flight public response before its bytes are read.
  await page.locator('.original-join .container').evaluate(async (element) => {
    const backgrounds = [
      getComputedStyle(element).backgroundImage,
      getComputedStyle(element, '::after').backgroundImage,
    ];
    const urls = [
      ...new Set(
        backgrounds.flatMap((background) =>
          [...background.matchAll(/url\(["']?([^"')]+)["']?\)/g)].map(
            (match) => match[1],
          ),
        ),
      ),
    ];
    await Promise.all(
      urls.map(async (url) => {
        const image = new Image();
        image.src = url;
        await image.decode();
      }),
    );
  });
  await settleResponses();
  check(
    'public reset clears both showcase-owned stores only',
    await page.evaluate(
      (keys) =>
        keys.every((key) => sessionStorage.getItem(key) === null) &&
        sessionStorage.getItem('publication.unrelated') === 'keep',
      stateKeys,
    ),
  );
  await page.goto(pageUrl + '#/app/material/water-journey/result');
  await page
    .getByRole('heading', { name: '아직 풀이 결과가 없습니다.', exact: true })
    .waitFor();
  check(
    'reset result remains absent after a new document navigation',
    (await page.getByTestId('quiz-score').count()) === 0,
  );
  await settleResponses();
  await desktop.context.close();
  await checkPortfolioPolish({
    newContext: async (label, options = {}) => {
      const guarded = await context(label, options.viewport, options);
      return {
        page: guarded.page,
        context: {
          newCDPSession: (page) => guarded.context.newCDPSession(page),
          close: async () => {
            // Finish real response integrity checks before closing this context.
            // The shared helper owns its contexts and also closes them on failure.
            try {
              await guarded.page.waitForLoadState('networkidle');
              await settleResponses();
            } finally {
              await guarded.context.close();
            }
          },
        },
      };
    },
    // The shared helper's base is only a local-build path. All navigation here
    // uses the confirmed Pages URL (or the explicit local rehearsal URL).
    navigate: (page, _base, route) => navigate(page, route),
    check: (name, condition, category, details) =>
      check(name, condition, category.replace('PORTFOLIO_', 'PUBLIC_POLISH_'), details),
    capture: (page, name) => screenshot(page, 'public-' + name),
  });
  return observedUrl;
}

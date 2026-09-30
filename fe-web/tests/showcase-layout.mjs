/** Targeted visual-review regression, using the existing isolated Chrome/network harness. */
export async function checkShowcaseLayout({
  newContext,
  navigate,
  check,
  capture,
  heading,
  textShown,
  askExample,
  answerQuiz,
}) {
  const base = '/DO-DREAM/';
  const material = (screen) => `/app/material/water-journey/${screen}`;
  async function ready(page) {
    await page.evaluate(() => document.fonts.ready);
  }
  async function teacherGeometry(page, name) {
    const rows = await page
      .locator('.classroom-page .cl-card-head')
      .evaluateAll((heads) =>
        heads.map((head) => {
          const rect = (element) => {
            const r = element.getBoundingClientRect();
            return {
              left: r.left,
              right: r.right,
              top: r.top,
              bottom: r.bottom,
              width: r.width,
              height: r.height,
            };
          };
          const lineCount = (element) => {
            const range = document.createRange();
            range.selectNodeContents(element);
            return new Set(
              [...range.getClientRects()]
                .filter((r) => r.width > 0)
                .map((r) => Math.round(r.top)),
            ).size;
          };
          const title = head.querySelector('h3'),
            input = head.querySelector('.cl-input-wrap'),
            sort = head.querySelector('.cl-sort-btn'),
            panel = head.closest('.cl-card');
          const bounds = rect(panel),
            a = rect(title),
            b = rect(input),
            c = rect(sort);
          const overlap = (x, y) =>
            x.left < y.right - 1 &&
            x.right > y.left + 1 &&
            x.top < y.bottom - 1 &&
            x.bottom > y.top + 1;
          return {
            title: title.textContent,
            titleLines: lineCount(title),
            sortLines: lineCount(sort.querySelector('span')),
            fontSize: getComputedStyle(title).fontSize,
            contained: [a, b, c].every(
              (r) => r.left >= bounds.left && r.right <= bounds.right,
            ),
            overlap: overlap(a, b) || overlap(a, c) || overlap(b, c),
            inputWidth: b.width,
          };
        }),
      );
    check(
      name,
      rows.length === 2 &&
        rows.every(
          (r) =>
            r.titleLines === 1 &&
            r.sortLines === 1 &&
            r.fontSize === '18px' &&
            r.contained &&
            !r.overlap &&
            r.inputWidth >= 140,
        ),
      'VISUAL_POLISH',
      rows,
    );
  }
  async function phoneGeometry(page, name) {
    const result = await page
      .locator('.app-viewport')
      .evaluate((phone) => ({
        width: phone.clientWidth,
        scroll: phone.scrollWidth,
        overflow: [
          ...phone.querySelectorAll(
            '.app-choice,.app-paragraph,.app-welcome,.app-quiz-prompt,.app-quiz-badge',
          ),
        ]
          .filter((el) => el.scrollWidth > el.clientWidth + 1)
          .map((el) => el.className),
        pageOverflow: document.documentElement.scrollWidth > innerWidth + 1,
        scale: getComputedStyle(phone).transform,
      }));
    check(
      name,
      !result.pageOverflow &&
        result.scroll <= result.width + 1 &&
        result.overflow.length === 0 &&
        result.scale === 'none',
      'VISUAL_POLISH',
      result,
    );
  }
  async function wordLines(page, selector, name) {
    const split = await page.locator(selector).evaluateAll((elements) =>
      elements.flatMap((element) => {
        const broken = [];
        const walk = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walk.nextNode()))
          for (const match of node.textContent.matchAll(/[가-힣]{2,8}/g)) {
            const r = document.createRange();
            r.setStart(node, match.index);
            r.setEnd(node, match.index + match[0].length);
            const lines = new Set(
              [...r.getClientRects()]
                .filter((rect) => rect.width > 0)
                .map((rect) => Math.round(rect.top)),
            );
            const parent = node.parentElement,
              style = getComputedStyle(parent);
            const canvas = document.createElement('canvas'),
              ctx = canvas.getContext('2d');
            ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
            const available =
              parent.clientWidth -
              parseFloat(style.paddingLeft) -
              parseFloat(style.paddingRight);
            if (
              lines.size > 1 &&
              ctx.measureText(match[0]).width <= available + 1
            )
              broken.push(match[0]);
          }
        return broken;
      }),
    );
    check(name, split.length === 0, 'KOREAN_WORD_WRAP', split);
  }
  const teacher = await newContext('visual-polish-teacher');
  try {
    for (const width of [1280, 1366, 1440]) {
      await teacher.page.setViewportSize({ width, height: 920 });
      await navigate(teacher.page, base, '/teacher');
      await textShown(teacher.page, '내 자료 (2개)');
      await ready(teacher.page);
      check(
        `teacher ${width}: list retains original rows`,
        (await teacher.page.locator('.cl-material-item').count()) === 2,
        'VISUAL_POLISH',
      );
      await teacher.page
        .getByRole('link', { name: '1학년 1반', exact: false })
        .first()
        .click();
      await heading(teacher.page, '공유된 학습 자료');
      await teacherGeometry(
        teacher.page,
        `teacher ${width}: headings/search/sort do not overlap or split`,
      );
      for (const button of await teacher.page
        .locator('.classroom-page .cl-sort-btn')
        .all())
        await button.click();
      await teacherGeometry(
        teacher.page,
        `teacher ${width}: alternate sort labels remain one line`,
      );
      for (const label of ['자료 제목 검색', '학생 검색']) {
        const input = teacher.page.getByRole('textbox', {
          name: label,
          exact: true,
        });
        await input.fill('띄어쓰기가없는아주긴검색어'.repeat(20));
        await teacherGeometry(
          teacher.page,
          `teacher ${width}: long ${label} remains contained`,
        );
        await input.fill('');
      }
      if (width === 1280 || width === 1366)
        await capture(teacher.page, `polish-teacher-classroom-${width}`);
    }
    await navigate(teacher.page, base, '/teacher/editor/water-journey');
    const editor = teacher.page.getByRole('textbox', {
      name: '샘플 본문 편집',
    });
    await editor.waitFor();
    await ready(teacher.page);
    await teacher.page
      .getByRole('button', { name: '물의 여행', exact: true })
      .click();
    const title = teacher.page.getByRole('textbox', {
      name: '자료 제목',
      exact: true,
    });
    await title.fill('띄어쓰기없는매우긴공개샘플자료이름'.repeat(6));
    await title.press('Enter');
    await teacher.page
      .getByRole('button', { name: '임시 저장', exact: true })
      .click();
    await textShown(teacher.page, '현재 탭에 본문을 임시 저장');
    for (const width of [1280, 1366, 1440]) {
      await teacher.page.setViewportSize({ width, height: 920 });
      await navigate(teacher.page, base, '/teacher/classroom/1-1');
      await heading(teacher.page, '공유된 학습 자료');
      const overflow = await teacher.page
        .locator('.classroom-page .cl-material-item')
        .evaluateAll((items) =>
          items.some((item) => {
            const box = item.getBoundingClientRect(),
              panel = item.closest('.cl-card').getBoundingClientRect();
            return (
              box.left < panel.left ||
              box.right > panel.right ||
              item.scrollWidth > item.clientWidth + 1
            );
          }),
        );
      check(
        `teacher ${width}: long edited material name stays within its clickable row`,
        !overflow,
        'VISUAL_POLISH',
      );
    }
  } finally {
    await teacher.context.close();
  }
  for (const [viewport, label] of [
    [{ width: 1280, height: 920 }, '392'],
    [{ width: 320, height: 640 }, '320'],
  ])
    for (const large of [false, true]) {
      const suffix = `${label}-${large ? '150' : '100'}`,
        { context, page } = await newContext(
          'visual-polish-student-' + suffix,
          { viewport },
        );
      try {
        if (large) {
          await navigate(page, base, '/app/settings');
          await page
            .getByRole('button', { name: '글자 크기 늘리기', exact: true })
            .click();
          await page.locator('.app-font-12').waitFor();
          await page
            .getByRole('button', { name: '글자 크기 늘리기', exact: true })
            .click();
          await page.locator('.app-font-15').waitFor();
        }
        await navigate(page, base, '/app/library');
        await page.getByTestId('material-water-journey').waitFor();
        await phoneGeometry(page, `${suffix}: library unchanged bounds`);
        for (const [screen, selector] of [
          ['player', '.app-paragraph'],
          ['question', '.app-welcome'],
          ['quizzes', '.app-choice strong'],
          ['quiz', '.app-quiz-prompt'],
        ]) {
          await navigate(page, base, material(screen));
          await page.locator(selector).first().waitFor();
          await ready(page);
          await wordLines(
            page,
            selector,
            `${suffix}: ${screen} Korean words stay together`,
          );
          await phoneGeometry(
            page,
            `${suffix}: ${screen} remains within phone`,
          );
          if (screen === 'quizzes') {
            const cards = await page
              .locator('.app-choice')
              .evaluateAll((cards) =>
                cards.map((card) => {
                  const t = card
                      .querySelector('strong')
                      .getBoundingClientRect(),
                    b = card
                      .querySelector('.app-quiz-badge')
                      .getBoundingClientRect(),
                    c = card.getBoundingClientRect();
                  return {
                    separate: t.right <= b.left + 1 || t.bottom <= b.top + 1,
                    badge: b.width,
                    title: t.width,
                    contained: t.bottom <= c.bottom && b.right <= c.right,
                  };
                }),
              );
            check(
              `${suffix}: complete quiz titles and badges have separate space`,
              cards.every((c) => c.separate && c.contained && c.badge >= 50),
              'VISUAL_POLISH',
              cards,
            );
            if (!large && label === '392')
              await capture(page, 'polish-student-quizzes-392-100');
            // A layout-only stress probe, never persisted or represented as generated quiz content.
            await page
              .locator(selector)
              .first()
              .evaluate((el) => {
                el.textContent = '한글공백없는긴단일문자열'.repeat(25);
              });
            await phoneGeometry(
              page,
              `${suffix}: long single quiz token wraps instead of overflowing`,
            );
          }
        }
        for (const short of [false, true]) {
          if (short)
            await page.setViewportSize({ width: viewport.width, height: 500 });
          await navigate(page, base, material('playback'));
          const scroller = page.locator('.app-playback-content');
          await scroller.waitFor();
          await scroller.evaluate((el) => {
            el.scrollTop = el.scrollHeight;
          });
          const bottom = await scroller.evaluate((el) => {
            const b = el.getBoundingClientRect();
            const controls = [...el.querySelectorAll('.app-choice')].slice(-2);
            return {
              atEnd:
                Math.abs(el.scrollHeight - el.clientHeight - el.scrollTop) < 2,
              menus: controls.map((c) => ({
                text: c.textContent,
                visible:
                  c.getBoundingClientRect().top >= b.top &&
                  c.getBoundingClientRect().bottom <= b.bottom + 1,
              })),
            };
          });
          check(
            `${suffix}${short ? '-short' : ''}: playback bottom includes saved and final quiz menu`,
            bottom.atEnd &&
              bottom.menus.length === 2 &&
              bottom.menus.every((m) => m.visible) &&
              bottom.menus[1].text.includes('퀴즈 풀기'),
            'PLAYBACK_SCROLL',
            bottom,
          );
          if (!large && label === '392' && !short)
            await capture(page, 'polish-playback-bottom-392-100');
          await page
            .getByRole('link', {
              name: '저장 목록 저장한 내용 보기',
              exact: true,
            })
            .click();
          await heading(page, '저장 목록');
          await navigate(page, base, material('playback'));
          await page
            .getByRole('button', {
              name: '이어서 듣기 마지막 위치부터',
              exact: true,
            })
            .focus();
          for (let n = 0; n < 4; n++) await page.keyboard.press('Tab');
          const focus = await page.evaluate(() => {
            const el = document.activeElement,
              r = el.getBoundingClientRect(),
              s = el.closest('.app-scroll').getBoundingClientRect();
            return {
              text: el.textContent,
              visible:
                r.top >= Math.max(40, s.top) - 1 &&
                r.bottom <= Math.min(innerHeight, s.bottom) + 1,
            };
          });
          check(
            `${suffix}${short ? '-short' : ''}: Tab reveals complete final menu`,
            focus.text.includes('퀴즈 풀기') && focus.visible,
            'PLAYBACK_SCROLL',
            focus,
          );
          await page.keyboard.press('Enter');
          await textShown(page, '전체 퀴즈 목록');
        }
      } finally {
        await context.close();
      }
    }
  // A fresh sample tab, with no fabricated achievements or preloaded results.
  const { context, page } = await newContext(
    'visual-polish-demonstrated-history',
  );
  try {
    await navigate(page, base, '/teacher/student/demo-student');
    await textShown(page, '퀴즈 결과가 없습니다.');
    const progress = () => page.locator('.sr-sidebar-stats').innerText();
    check(
      'fresh sample has zero progress and empty results',
      (await progress()).includes('0%') &&
        (await page.locator('.sr-quiz-card').count()) === 0,
      'DEMONSTRATED_STATE',
    );
    await navigate(page, base, material('question'));
    await askExample(page);
    await navigate(page, base, material('quiz'));
    await page
      .getByRole('button', { name: '음성으로 답하기', exact: true })
      .click();
    await textShown(page, '마이크를 사용하지 않습니다.');
    await page.keyboard.press('Escape');
    await answerQuiz(page);
    await navigate(page, base, '/teacher/student/demo-student');
    await textShown(page, '2개 정답');
    check(
      'one real sample question and quiz appear without marking all learning complete',
      (await page.locator('.sr-qa-item').count()) === 1 &&
        (await page.locator('.sr-quiz-card').count()) === 1 &&
        (await progress()).includes('50%'),
      'DEMONSTRATED_STATE',
    );
    await capture(page, 'polish-teacher-student-history');
  } finally {
    await context.close();
  }
}

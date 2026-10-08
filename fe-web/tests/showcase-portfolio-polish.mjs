/** Submission polish checks on the built artifact, using the guarded Chrome harness. */
export async function checkPortfolioPolish({
  newContext,
  navigate,
  check,
  capture,
}) {
  const base = '/DO-DREAM/';
  async function artworkReady(page) {
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all([...document.images].map((image) => image.decode()));
      const urls = new Set();
      for (const element of document.querySelectorAll(
        '.original-teacher, .original-teacher *',
      )) {
        for (const pseudo of [null, '::before', '::after']) {
          for (const match of getComputedStyle(
            element,
            pseudo,
          ).backgroundImage.matchAll(/url\(["']?([^"')]+)["']?\)/g))
            urls.add(match[1]);
        }
      }
      await Promise.all(
        [...urls].map(async (url) => {
          const image = new Image();
          image.src = url;
          await image.decode();
        }),
      );
    });
  }
  async function axNodes(context, page) {
    const session = await context.newCDPSession(page);
    try {
      return (await session.send('Accessibility.getFullAXTree')).nodes.filter(
        (node) => !node.ignored,
      );
    } finally {
      await session.detach();
    }
  }
  for (const width of [1280, 375]) {
    const { context, page } = await newContext(`portfolio-entry-${width}`, {
      viewport: { width, height: width === 375 ? 812 : 920 },
    });
    try {
      await navigate(page, base, '/');
      for (const mode of ['sign-in', 'sign-up']) {
        await page.locator(`.container.${mode}`).waitFor();
        await artworkReady(page);
        const active = page.locator('.form:not([inert])');
        const nodes = await axNodes(context, page);
        const headings = nodes
          .filter((node) => node.role?.value === 'heading')
          .map((node) => ({
            name: node.name?.value,
            level: node.properties?.find(
              (property) => property.name === 'level',
            )?.value.value,
          }));
        check(
          `${width}/${mode}: native accessibility tree exposes one meaningful h1 and no decorative headings`,
          headings.length === 1 &&
            headings[0].name === 'DO:DREAM 체험 시작' &&
            headings[0].level === 1,
          'PORTFOLIO_AX',
          headings,
        );
        check(
          `${width}/${mode}: introduction is exposed and inactive controls are excluded from AX`,
          nodes.some(
            (node) =>
              node.role?.value === 'StaticText' &&
              node.name?.value.includes('시각장애 학생이 교재를 읽고 질문하며'),
          ) &&
            [
              '교사 체험',
              '학생 앱 체험',
              'GitHub 소스',
              '다른 시작 배경 보기',
            ].every(
              (name) =>
                nodes.filter(
                  (node) =>
                    ['button', 'link'].includes(node.role?.value) &&
                    node.name?.value === name,
                ).length === 1,
            ),
          'PORTFOLIO_AX',
        );
        const appearance = await active.evaluate((form) => {
          const title = form.querySelector('h1'),
            style = getComputedStyle(title);
          const mobile = innerWidth === 375;
          const shape = (element) => {
            const css = getComputedStyle(element),
              rect = element.getBoundingClientRect();
            return {
              width: rect.width,
              height: rect.height,
              font: css.fontSize,
              family: css.fontFamily,
              weight: css.fontWeight,
              lineHeight: css.lineHeight,
              padding: css.padding,
              margin: css.margin,
              borderWidths: [
                css.borderTopWidth,
                css.borderRightWidth,
                css.borderBottomWidth,
                css.borderLeftWidth,
              ],
              borderStyles: [
                css.borderTopStyle,
                css.borderRightStyle,
                css.borderBottomStyle,
                css.borderLeftStyle,
              ],
              radius: css.borderRadius,
              boxSizing: css.boxSizing,
              display: css.display,
            };
          };
          return {
            titleFont: style.fontSize,
            titleWeight: style.fontWeight,
            titleColor: style.color,
            buttons: [...form.querySelectorAll('.join-demo-button')].map(
              (button) => {
                // Original CSS is identical in bce567b and approved ac08ba1.
                // `normal` line height varies with the OS system font. Compare
                // against these reviewed constants in the same browser instead
                // of imposing the macOS sample's 50px absolute minimum.
                const reference = document.createElement('a');
                reference.setAttribute('aria-hidden', 'true');
                reference.inert = true;
                reference.textContent = button.textContent;
                reference.style.cssText = `all: initial; position: fixed; left: -10000px; top: 0; visibility: hidden; pointer-events: none; display: block; box-sizing: border-box; width: ${mobile ? 319 : 416}px; margin: ${mobile ? 10 : 16}px 0; padding: 0.8rem 1rem; border: 2px solid transparent; border-radius: 0.5rem; font: 600 ${mobile ? '17px' : '1.2rem'}/normal -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;`;
                document.body.append(reference);
                try {
                  return { actual: shape(button), original: shape(reference) };
                } finally {
                  reference.remove();
                }
              },
            ),
            overflow: document.documentElement.scrollWidth > innerWidth + 1,
          };
        });
        check(
          `${width}/${mode}: title appearance and original button sizes remain`,
          appearance.titleFont === (width === 375 ? '13px' : '16px') &&
            appearance.titleWeight === '800' &&
            appearance.titleColor === 'rgb(117, 117, 117)' &&
            !appearance.overflow &&
            appearance.buttons.length === 2 &&
            appearance.buttons.every(
              (button) =>
                button.actual.font === (width === 375 ? '17px' : '19.2px') &&
                JSON.stringify(button.actual) ===
                  JSON.stringify(button.original),
            ),
          'PORTFOLIO_LAYOUT',
          appearance,
        );
        const source = active.getByRole('link', {
          name: 'GitHub 소스',
          exact: true,
        });
        check(
          `${width}/${mode}: source is an explicit safe external link, not a preload`,
          (await source.getAttribute('href')) ===
            'https://github.com/rladbstn1000/DO-DREAM' &&
            (await source.getAttribute('target')) === '_blank' &&
            (await source.getAttribute('rel'))
              .split(/\s+/)
              .includes('noopener') &&
            (await source.getAttribute('rel'))
              .split(/\s+/)
              .includes('noreferrer') &&
            (await page
              .locator(
                'link[rel=prefetch],link[rel=preconnect],link[rel=dns-prefetch]',
              )
              .count()) === 0,
          'PORTFOLIO_LINK',
        );
        await active.getByRole('heading', { level: 1 }).focus();
        const order = [];
        for (const expected of [
          '교사 체험',
          '학생 앱 체험',
          'GitHub 소스',
          '다른 시작 배경 보기',
        ]) {
          await page.keyboard.press('Tab');
          const focus = await page.evaluate(() => {
            const element = document.activeElement,
              r = element.getBoundingClientRect();
            return {
              name: element.textContent.trim(),
              inert: !!element.closest('[inert],[aria-hidden=true]'),
              visible:
                r.width > 0 &&
                r.height > 0 &&
                r.top >= 0 &&
                r.bottom <= innerHeight,
              outline: getComputedStyle(element).outlineStyle,
            };
          });
          order.push(focus);
          check(
            `${width}/${mode}: Tab reaches visible ${expected} only`,
            focus.name === expected &&
              !focus.inert &&
              focus.visible &&
              focus.outline !== 'none',
            'PORTFOLIO_KEYBOARD',
            focus,
          );
        }
        await capture(page, `portfolio-start-${width}-${mode}`);
        await page.keyboard.press('Enter');
        const next = mode === 'sign-in' ? 'sign-up' : 'sign-in';
        await page.locator(`.container.${next}`).waitFor();
        check(
          `${width}/${mode}: background switch focuses the active title`,
          await page.evaluate(
            () =>
              document.activeElement?.matches('.form:not([inert]) h1') &&
              !document.activeElement.closest('[aria-hidden=true]'),
          ),
          'PORTFOLIO_KEYBOARD',
          order,
        );
      }
    } finally {
      await context.close();
    }
  }
  const motion = await newContext('portfolio-entry-normal-motion', {
    reducedMotion: 'no-preference',
  });
  try {
    await navigate(motion.page, base, '/');
    for (const mode of ['sign-in', 'sign-up']) {
      await motion.page.waitForFunction(
        () =>
          getComputedStyle(document.querySelector('.form:not([inert])'))
            .transform === 'matrix(1, 0, 0, 1, 0, 0)',
      );
      const active = motion.page.locator('.form:not([inert])');
      await active.getByRole('heading', { level: 1 }).focus();
      for (let index = 0; index < 4; index++)
        await motion.page.keyboard.press('Tab');
      check(
        `normal motion/${mode}: keyboard reaches the active background switch`,
        await motion.page.evaluate(() =>
          document.activeElement.matches('.form:not([inert]) .join-toggle'),
        ),
        'PORTFOLIO_KEYBOARD',
      );
      await motion.page.keyboard.press('Enter');
      await motion.page.waitForFunction(() =>
        document.activeElement.matches('.form:not([inert]) h1'),
      );
      check(
        `normal motion/${mode}: focus transfers to active h1 during the transition`,
        await motion.page.evaluate(
          () => !document.activeElement.closest('[inert],[aria-hidden=true]'),
        ),
        'PORTFOLIO_KEYBOARD',
      );
    }
  } finally {
    await motion.context.close();
  }

  const { context, page } = await newContext('portfolio-memo');
  try {
    for (const width of [1023, 1024, 1025, 1280, 375]) {
      await page.setViewportSize({ width, height: 920 });
      await navigate(page, base, '/teacher');
      await artworkReady(page);
      const nodes = await axNodes(context, page);
      const geometry = await page.locator('.cl-memo').evaluate((memo) => {
        const rect = (element) => element.getBoundingClientRect().toJSON();
        const label = memo.querySelector('label'),
          input = memo.querySelector('textarea'),
          board = memo.querySelector('.cl-memo-zoom');
        return {
          shown: getComputedStyle(memo).display !== 'none',
          label: rect(label),
          input: rect(input),
          board: rect(board),
          image: getComputedStyle(board, '::before').backgroundImage,
          labelsMatch:
            input.labels.length === 1 &&
            input.labels[0] === label &&
            input.getAttribute('aria-labelledby') === label.id,
          overflow: document.documentElement.scrollWidth > innerWidth + 1,
        };
      });
      if (width === 375) {
        check(
          '375: preserve existing mobile memo policy without hidden keyboard/AX targets or overflow',
          !geometry.shown &&
            !geometry.overflow &&
            !nodes.some(
              (node) =>
                node.role?.value === 'textbox' &&
                node.name?.value === '현재 탭의 메모',
            ),
          'PORTFOLIO_LAYOUT',
          geometry,
        );
      } else {
        // The existing memo PNG's clip occupies the top 16% of its image box.
        // Keep visible text below that region and inside the same paper image.
        check(
          `${width}: memo label clears the clip and input stays below the label`,
          geometry.shown &&
            geometry.image.includes('memo-') &&
            geometry.label.top >=
              geometry.board.top + geometry.board.height * 0.16 &&
            geometry.label.bottom + 2 <= geometry.input.top &&
            geometry.input.bottom <= geometry.board.bottom &&
            geometry.label.left >= geometry.board.left &&
            geometry.label.right <= geometry.board.right &&
            !geometry.overflow,
          'PORTFOLIO_LAYOUT',
          geometry,
        );
        check(
          `${width}: visible memo label is connected to the native AX textbox`,
          geometry.labelsMatch &&
            nodes.filter(
              (node) =>
                node.role?.value === 'textbox' &&
                node.name?.value === '현재 탭의 메모',
            ).length === 1,
          'PORTFOLIO_AX',
        );
        await page.getByText('현재 탭의 메모', { exact: true }).click();
        check(
          `${width}: label focuses the memo input`,
          await page
            .getByRole('textbox', { name: '현재 탭의 메모', exact: true })
            .evaluate((input) => document.activeElement === input),
          'PORTFOLIO_KEYBOARD',
        );
        await page.keyboard.press('Tab');
        await page.keyboard.press('Shift+Tab');
        check(
          `${width}: keyboard returns to visible memo input`,
          await page
            .getByRole('textbox', { name: '현재 탭의 메모', exact: true })
            .evaluate(
              (input) =>
                document.activeElement === input &&
                getComputedStyle(input).outlineStyle !== 'none',
            ),
          'PORTFOLIO_KEYBOARD',
        );
      }
      await capture(page, `portfolio-teacher-${width}`);
    }
    await page.setViewportSize({ width: 1024, height: 920 });
    await navigate(page, base, '/teacher');
    const memo = page.getByRole('textbox', {
      name: '현재 탭의 메모',
      exact: true,
    });
    await memo.fill('오늘 수업 준비: 물의 여행');
    await page.getByRole('link', { name: '학생 앱', exact: true }).click();
    await page.getByRole('heading', { name: '샘플', exact: true }).waitFor();
    await page.getByRole('link', { name: '교사 웹', exact: true }).click();
    check(
      'memo survives teacher/student navigation in the same tab',
      (await memo.inputValue()) === '오늘 수업 준비: 물의 여행',
      'PORTFOLIO_STATE',
    );
    await page.reload();
    check(
      'memo survives reload in the same tab',
      (await memo.inputValue()) === '오늘 수업 준비: 물의 여행',
      'PORTFOLIO_STATE',
    );
    await page.getByTestId('reset-demo').click();
    await page
      .getByRole('heading', { name: 'DO:DREAM 체험 시작', level: 1 })
      .waitFor();
    await artworkReady(page);
    await page.getByRole('link', { name: '교사 웹', exact: true }).click();
    check(
      'reset clears the entered memo',
      (await memo.inputValue()) === '',
      'PORTFOLIO_STATE',
    );
  } finally {
    await context.close();
  }
}

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { launchChrome } from './chrome-launch.mjs';

// These are controlled launch-policy tests. They do not count as browser or API execution.
test('unset executable selects installed Chrome and preserves launch arguments', async () => {
  const options = { headless: true, timeout: 15000, args: ['--disable-background-networking'] };
  const browser = {};
  const chromium = { async launch(actual) { assert.deepEqual(actual, { ...options, channel: 'chrome' }); return browser; } };
  assert.equal(await launchChrome(chromium, options, {}), browser);
  assert.equal(Object.hasOwn(options, 'channel'), false);
});

test('explicit executable takes precedence without shell parsing or channel fallback', async () => {
  const chromium = { async launch(actual) {
    assert.deepEqual(actual, { headless: true, executablePath: process.execPath });
    return 'controlled launch';
  } };
  // Node is only a known executable fixture here; the launch method is controlled, not real Chrome.
  assert.equal(await launchChrome(chromium, { headless: true, channel: 'ignored' }, {
    DODREAM_CHROME_EXECUTABLE: process.execPath,
  }), 'controlled launch');
});

test('invalid explicit paths fail before launch, including empty, relative, missing and directory paths', async () => {
  const directory = await mkdtemp(path.join(tmpdir(), 'dodream-chrome-policy-'));
  let launches = 0;
  const chromium = { async launch() { launches++; throw new Error('Must not launch'); } };
  try {
    for (const executablePath of ['', 'chrome', path.join(directory, 'missing-browser'), directory]) {
      await assert.rejects(launchChrome(chromium, {}, { DODREAM_CHROME_EXECUTABLE: executablePath }), {
        name: 'ChromeExecutableConfigurationError',
      });
    }
    assert.equal(launches, 0);
  } finally { await rm(directory, { recursive: true }); }
});

test('missing installed Chrome is reported separately and is not retried or downloaded', async () => {
  let launches = 0;
  const cause = new Error("Chromium distribution 'chrome' is not found");
  const chromium = { async launch() { launches++; throw cause; } };
  await assert.rejects(launchChrome(chromium, {}, {}), error =>
    error.name === 'ChromeUnavailableError' && error.cause === cause && /No browser was downloaded/.test(error.message));
  assert.equal(launches, 1);
});

test('other browser launch failures retain their cause and are not labelled missing Chrome', async () => {
  const cause = new Error('Browser exited unexpectedly');
  await assert.rejects(launchChrome({ async launch() { throw cause; } }, {}, {}), error =>
    error.name === 'ChromeLaunchError' && error.cause === cause);
});

test('affected harnesses use the declared package and shared executable policy', async () => {
  const names = ['auth', 'authorization', 'grading', 'indexing', 'student', 'demo-disabled', 'hardening'];
  for (const name of names) {
    const filename = `browser-${name}.mjs`;
    const source = await readFile(new URL(filename, import.meta.url), 'utf8');
    assert.match(source, /import\s*\{\s*chromium\s*\}\s*from\s*['"]playwright-core['"]/, filename);
    assert.match(source, /await launchChrome\(chromium,/, filename);
    assert.doesNotMatch(source, /(?:require\(|from\s+|import\()['"]playwright['"]/, filename);
    assert.doesNotMatch(source, /DODREAM_PLAYWRIGHT_PATH|codex-runtimes|\/Users\/|\/Applications\/Google Chrome|\/home\/[^/]+\//, filename);
    assert.doesNotMatch(source, /chromium\.launch\(|launchPersistentContext\(/, filename);
  }
  const helper = await readFile(new URL('chrome-launch.mjs', import.meta.url), 'utf8');
  assert.doesNotMatch(helper, /DODREAM_PLAYWRIGHT_PATH|codex-runtimes|\/Users\/|\/Applications\/Google Chrome|launchPersistentContext|child_process/);
  const pkg = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'));
  const lock = JSON.parse(await readFile(new URL('../package-lock.json', import.meta.url), 'utf8'));
  assert.equal(pkg.devDependencies['playwright-core'], lock.packages['node_modules/playwright-core'].version);
  assert.equal(pkg.dependencies?.playwright ?? pkg.devDependencies.playwright, undefined);
});

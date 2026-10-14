import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { readFile } from 'node:fs/promises';
import childProcess from 'node:child_process';
import net from 'node:net';
import http from 'node:http';
import https from 'node:https';
import { syncBuiltinESMExports } from 'node:module';
import { loadIsolatedRuntime, readTrialFixture, readTrialCredentials, readTrialBrowserPlan } from './isolated-runtime.mjs';

// Entirely in-memory synthetic file metadata/content. No service, browser, socket or real credential access.
const repository = '/synthetic/DO-DREAM';
const manifestPath = path.join(repository, 'scripts/local/isolated-trial.json');
const trialId = 'evidence-portability-20261014';
const trialRoot = path.join(repository, '.local/isolated', trialId);
const project = 'dodream-evidence-20261014';
const runId = '00000000-0000-4000-8000-000000000001';
const manifest = () => ({ schema: 1, id: trialId, project, root: `.local/isolated/${trialId}`, credentials: 'credentials.env',
  origins: { main: 'http://127.0.0.1:25173', short: 'http://127.0.0.1:25174' } });
const environment = { DODREAM_ISOLATED_MANIFEST: manifestPath };
function fixture(suite = 'auth') {
  return { trialId, project, runId, suite, syntheticOnly: true,
    origin: manifest().origins[['auth', 'demo-disabled'].includes(suite) ? 'short' : 'main'],
    teacherEmail: 'synthetic-teacher@trial.invalid', ownerEmail: 'synthetic-owner@trial.invalid', otherEmail: 'synthetic-other@trial.invalid',
    studentDeviceId: 'synthetic-new-device', lessonTitle: '[SYNTHETIC] new material', unauthorizedStudentId: 90210 };
}
function memory(files = {}, specialMetadata = {}) {
  const contents = new Map(Object.entries({ [manifestPath]: JSON.stringify(manifest()), ...files }));
  const reads = [];
  return { reads,
    async lstat(filename) {
      if (specialMetadata[filename]) return specialMetadata[filename];
      const file = contents.has(filename);
      const prefix = filename.endsWith(path.sep) ? filename : filename + path.sep;
      if (!file && ![...contents.keys()].some(target => target.startsWith(prefix))) throw Object.assign(new Error('Synthetic missing path'), { code: 'ENOENT' });
      return { isSymbolicLink: () => false, isFile: () => file, isDirectory: () => !file, nlink: 1 };
    },
    async readFile(filename) {
      reads.push(filename);
      if (!contents.has(filename)) throw new Error('Unexpected file access');
      return contents.get(filename);
    },
  };
}
const forbiddenExecutor = () => assert.fail('No browser or service executor may run in pure policy tests');
const restored = [];
before(() => {
  for (const [object, keys] of [[childProcess, ['spawn', 'spawnSync', 'exec', 'execSync', 'execFile', 'execFileSync', 'fork']],
    [net, ['connect', 'createConnection']], [net.Socket.prototype, ['connect']], [http, ['request', 'get']], [https, ['request', 'get']],
    [globalThis, ['fetch']]]) {
    for (const key of keys) {
      restored.push([object, key, object[key]]);
      object[key] = forbiddenExecutor;
    }
  }
  syncBuiltinESMExports();
});
after(() => {
  for (const [object, key, value] of restored) object[key] = value;
  syncBuiltinESMExports();
});

test('explicit isolated manifest resolves each suite without reading credentials or launching', async () => {
  const io = memory();
  for (const suite of ['auth', 'authorization', 'grading', 'indexing', 'student', 'demo-disabled', 'hardening']) {
    const runtime = await loadIsolatedRuntime(suite, repository, environment, io);
    assert.equal(runtime.origin, manifest().origins[['auth', 'demo-disabled'].includes(suite) ? 'short' : 'main']);
    assert.equal(runtime.credentialsPath, path.join(trialRoot, 'credentials.env'));
    assert.equal(runtime.resultsDir, path.join(trialRoot, 'results'));
    assert.equal(runtime.planDir, path.join(trialRoot, 'browser-ui'));
    assert.equal(runtime.fixtureDir, path.join(trialRoot, 'fixtures'));
  }
  assert.deepEqual(new Set(io.reads), new Set([manifestPath]));
});

test('missing, relative, legacy manifest and legacy overrides fail before any data reads', async () => {
  for (const env of [{}, { DODREAM_ISOLATED_MANIFEST: 'relative.json' },
    { DODREAM_ISOLATED_MANIFEST: path.join(repository, '.local/env') },
    ...['DODREAM_RESULTS_DIR', 'DODREAM_AUTH_BROWSER_ORIGIN', 'DODREAM_AUTHZ_BROWSER_ORIGIN', 'DODREAM_GRADING_BROWSER_ORIGIN',
      'DODREAM_INDEX_BROWSER_ORIGIN', 'DODREAM_AUTHZ_BROWSER_TITLE', 'DODREAM_GRADING_BROWSER_TITLE'].map(key => ({ ...environment, [key]: '' }))]) {
    const io = memory();
    await assert.rejects(async () => { await loadIsolatedRuntime('auth', repository, env, io); forbiddenExecutor(); }, { name: 'IsolatedRuntimeConfigurationError' });
    assert.deepEqual(io.reads, []);
  }
});

test('unknown suite and mismatched root/project/credential settings reject without fallback', async () => {
  await assert.rejects(loadIsolatedRuntime('unknown', repository, environment, memory()), /Unknown isolated/);
  for (const patch of [{ schema: 2 }, { id: '../legacy' }, { id: [trialId] }, { project: 'dodream-phase1' }, { root: '.local' }, { unexpected: true },
    { root: '.local/isolated/../phase5' }, { credentials: '../../env' }, { credentials: '/synthetic/old.env' }]) {
    const io = memory({ [manifestPath]: JSON.stringify({ ...manifest(), ...patch }) });
    await assert.rejects(loadIsolatedRuntime('auth', repository, environment, io), { name: 'IsolatedRuntimeConfigurationError' });
    assert.deepEqual(io.reads, [manifestPath]);
  }
  const incomplete = manifest(); delete incomplete.credentials;
  await assert.rejects(loadIsolatedRuntime('auth', repository, environment, memory({ [manifestPath]: JSON.stringify(incomplete) })), /Missing or unknown/);
});

test('old endpoint, remote host, userinfo and same-port origins reject', async () => {
  for (const origins of [{ main: 'http://127.0.0.1:15173', short: 'http://127.0.0.1:25174' },
    { main: 'http://old-database:25173', short: 'http://127.0.0.1:25174' },
    { main: 'http://user@127.0.0.1:25173', short: 'http://127.0.0.1:25174' },
    { main: 'http://127.0.0.1:25173/', short: 'http://127.0.0.1:25174' },
    { main: 'http://127.0.0.1:25173', short: 'http://127.0.0.1:25173' },
    { ...manifest().origins, old: 'http://127.0.0.1:15173' }, {}]) {
    await assert.rejects(loadIsolatedRuntime('student', repository, environment,
      memory({ [manifestPath]: JSON.stringify({ ...manifest(), origins }) })), { name: 'IsolatedRuntimeConfigurationError' });
  }
});

test('symlinked trial root, output directory or credentials reject before reading linked content', async () => {
  for (const target of [trialRoot, path.join(trialRoot, 'results'), path.join(trialRoot, 'credentials.env')]) {
    const io = memory({ [path.join(trialRoot, 'fixtures/auth.json')]: JSON.stringify(fixture()) }, {
      [target]: { isSymbolicLink: () => true, isFile: () => false, isDirectory: () => false, nlink: 1 },
    });
    await assert.rejects(loadIsolatedRuntime('auth', repository, environment, io), /symlinks/);
    assert.deepEqual(io.reads, [manifestPath]);
  }
  const io = memory({}, { '/synthetic': { isSymbolicLink: () => true, isFile: () => false, isDirectory: () => false, nlink: 1 } });
  await assert.rejects(loadIsolatedRuntime('auth', repository, environment, io), /symlinks/);
  assert.deepEqual(io.reads, []);
});

test('fresh fixture receipt is mandatory before a future browser execution', async () => {
  const io = memory();
  const runtime = await loadIsolatedRuntime('auth', repository, environment, io);
  await assert.rejects(async () => { await readTrialFixture(runtime, io); forbiddenExecutor(); }, /Required isolated trial path/);
  for (const patch of [{ trialId: 'old-trial' }, { project: 'dodream-phase1' }, { runId: 'old' }, { suite: 'grading' },
    { origin: 'http://127.0.0.1:15174' }, { syntheticOnly: false }, { teacherEmail: '' }]) {
    await assert.rejects(readTrialFixture(runtime, memory({ [path.join(trialRoot, 'fixtures/auth.json')]: JSON.stringify({ ...fixture(), ...patch }) })),
      { name: 'IsolatedRuntimeConfigurationError' });
  }
});

test('fresh fixture text and foreign-subject identifier are explicit inputs', async () => {
  for (const suite of ['auth', 'authorization', 'grading', 'indexing', 'student', 'demo-disabled', 'hardening']) {
    const io = memory({ [path.join(trialRoot, `fixtures/${suite}.json`)]: JSON.stringify(fixture(suite)) });
    const runtime = await loadIsolatedRuntime(suite, repository, environment, io);
    assert.deepEqual(await readTrialFixture(runtime, io), fixture(suite));
  }
  const runtime = await loadIsolatedRuntime('hardening', repository, environment, memory());
  await assert.rejects(readTrialFixture(runtime, memory({ [path.join(trialRoot, 'fixtures/hardening.json')]: JSON.stringify({ ...fixture('hardening'), unauthorizedStudentId: 0 }) })), /identifier/);
});

test('credential reads are separate, confined and bound to the synthetic fixture run', async () => {
  const runtime = await loadIsolatedRuntime('auth', repository, environment, memory());
  const credentials = `DODREAM_TRIAL_ID=${trialId}\nDODREAM_TRIAL_RUN_ID=${runId}\nISOLATED_TEACHER_PASSWORD=SYNTHETIC_NOT_A_SECRET\n`;
  const io = memory({ [runtime.credentialsPath]: credentials });
  const settings = await readTrialCredentials(runtime, fixture(), io);
  assert.equal(settings.LOCAL_TEACHER_PASSWORD, 'SYNTHETIC_NOT_A_SECRET');
  assert.deepEqual(io.reads, [runtime.credentialsPath]);
  for (const text of ['ISOLATED_TEACHER_PASSWORD=SYNTHETIC_NOT_A_SECRET\n', credentials.replace(runId, 'old-run')]) {
    await assert.rejects(readTrialCredentials(runtime, fixture(), memory({ [runtime.credentialsPath]: text })), /this new trial run/);
  }
  await assert.rejects(readTrialCredentials(runtime, fixture(), memory({ [runtime.credentialsPath]: credentials.replace('ISOLATED_TEACHER_PASSWORD', 'LOCAL_TEACHER_PASSWORD') })), /Unexpected or duplicate/);
  await assert.rejects(readTrialCredentials(runtime, fixture(), memory({ [runtime.credentialsPath]: credentials }, {
    [runtime.credentialsPath]: { isSymbolicLink: () => false, isFile: () => true, isDirectory: () => false, nlink: 2 },
  })), /hard link/);
});

test('handshake plan must be in the new trial and have matching ownership/run binding', async () => {
  for (const suite of ['indexing', 'student']) {
    const runtime = await loadIsolatedRuntime(suite, repository, environment, memory());
    const filename = path.join(runtime.planDir, suite + '.json');
    const key = suite === 'indexing' ? 'DODREAM_INDEX_BROWSER_PLAN' : 'DODREAM_STUDENT_BROWSER_PLAN';
    const io = memory({ [filename]: JSON.stringify(fixture(suite)) });
    assert.deepEqual((await readTrialBrowserPlan(runtime, fixture(suite), { [key]: filename }, io)).plan, fixture(suite));
    for (const target of [undefined, '', path.join(repository, '.local/phase5/browser-ui/old.json'), path.join(runtime.planDir, '../old.json')]) {
      await assert.rejects(readTrialBrowserPlan(runtime, fixture(suite), { [key]: target }, io), /Explicit browser plan/);
    }
    for (const patch of [{ trialId: 'old' }, { runId: '00000000-0000-4000-8000-000000000002' }]) {
      await assert.rejects(readTrialBrowserPlan(runtime, fixture(suite), { [key]: filename },
        memory({ [filename]: JSON.stringify({ ...fixture(suite), ...patch }) })), { name: 'IsolatedRuntimeConfigurationError' });
    }
  }
});

test('all affected harnesses gate launch with explicit isolated fixture configuration', async () => {
  for (const suite of ['auth', 'authorization', 'grading', 'indexing', 'student', 'demo-disabled', 'hardening']) {
    const source = await readFile(new URL(`browser-${suite}.mjs`, import.meta.url), 'utf8');
    assert.ok(source.indexOf('await loadIsolatedRuntime(') < source.indexOf('await launchChrome('));
    assert.ok(source.indexOf('await readTrialFixture(') < source.indexOf('await launchChrome('));
    assert.doesNotMatch(source, /\.local\/env|\.local\/phase5|\.local\/portfolio-hardening|127\.0\.0\.1:1517[34]|DODREAM_RESULTS_DIR|DODREAM_\w+_BROWSER_ORIGIN|DODREAM_\w+_BROWSER_TITLE/);
    if (suite !== 'demo-disabled') assert.match(source, /await readTrialCredentials\(runtime, fixture\)/);
  }
  const helper = await readFile(new URL('isolated-runtime.mjs', import.meta.url), 'utf8');
  assert.doesNotMatch(helper, /from ['"](?:node:child_process|playwright-core|node:net|node:http|node:https)['"]|\bfetch\(|\.launch\(/);
  const boundaries = await readFile(new URL('browser-student-boundaries.mjs', import.meta.url), 'utf8');
  assert.doesNotMatch(boundaries, /127\.0\.0\.1:1517[34]/);
  assert.match(boundaries, /context\(shortOrigin\)/);
});

test('follow-up attempt keeps original fixtures plans and results outside its writable paths', async () => {
  const attemptId = 'fixed-01', attemptRoot = path.join(trialRoot, 'attempts', attemptId);
  const receiptPath = path.join(attemptRoot, 'attempt.json');
  const receipt = { schema: 1, attemptId, trialId, project, runId };
  const env = { ...environment, DODREAM_ISOLATED_ATTEMPT: attemptId };
  const data = { ...fixture('student'), attemptId };
  const io = memory({ [receiptPath]: JSON.stringify(receipt),
    [path.join(attemptRoot, 'fixtures/student.json')]: JSON.stringify(data) });
  const runtime = await loadIsolatedRuntime('student', repository, env, io);
  assert.equal(runtime.resultsDir, path.join(attemptRoot, 'results'));
  assert.equal(runtime.fixtureDir, path.join(attemptRoot, 'fixtures'));
  assert.equal(runtime.planDir, path.join(attemptRoot, 'browser-ui'));
  assert.equal(runtime.credentialsPath, path.join(trialRoot, 'credentials.env'));
  assert.deepEqual(await readTrialFixture(runtime, io), data);
  for (const patch of [{ attemptId: 'old-attempt' }, { attemptId: null },
    { runId: '00000000-0000-4000-8000-000000000002' }]) {
    await assert.rejects(readTrialFixture(runtime, memory({
      [path.join(runtime.fixtureDir, 'student.json')]: JSON.stringify({ ...data, ...patch }),
    })), /another attempt/);
  }
  const filename = path.join(runtime.planDir, 'student.json');
  await assert.rejects(readTrialBrowserPlan(runtime, data, { DODREAM_STUDENT_BROWSER_PLAN:
    path.join(trialRoot, 'browser-ui/student.json') }, io), /Explicit browser plan/);
  await assert.rejects(readTrialBrowserPlan(runtime, data, { DODREAM_STUDENT_BROWSER_PLAN: filename },
    memory({ [filename]: JSON.stringify({ ...data, attemptId: 'other' }) })), /another attempt/);
});

test('follow-up refuses missing mismatched or aliased attempt receipt without legacy fallback', async () => {
  for (const attemptId of ['', '../results', '/tmp/results', 'x'.repeat(49), 'UPPER']) {
    await assert.rejects(loadIsolatedRuntime('auth', repository,
      { ...environment, DODREAM_ISOLATED_ATTEMPT: attemptId }, memory()), /attempt identifier/);
  }
  const attemptId = 'fixed-01', env = { ...environment, DODREAM_ISOLATED_ATTEMPT: attemptId };
  const filename = path.join(trialRoot, 'attempts', attemptId, 'attempt.json');
  await assert.rejects(loadIsolatedRuntime('auth', repository, env, memory()), /Required isolated trial path/);
  for (const patch of [{ schema: 2 }, { attemptId: 'other' }, { project: 'dodream-phase1' },
    { trialId: 'old' }, { runId: 'not-a-run-id' }]) {
    await assert.rejects(loadIsolatedRuntime('auth', repository, env, memory({
      [filename]: JSON.stringify({ schema: 1, attemptId, trialId, project, runId, ...patch }),
    })), /Matching isolated attempt/);
  }
  await assert.rejects(loadIsolatedRuntime('auth', repository, env, memory({
    [filename]: JSON.stringify({ schema: 1, attemptId, trialId, project, runId }),
  }, { [path.dirname(filename)]: { isSymbolicLink: () => true } })), /symlinks/);
});

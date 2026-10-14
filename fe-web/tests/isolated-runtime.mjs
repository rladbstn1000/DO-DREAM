/** File-only configuration for a future isolated integration run; never starts a service or browser. */
import fs from 'node:fs/promises';
import path from 'node:path';

const suites = new Set(['auth', 'authorization', 'grading', 'indexing', 'student', 'demo-disabled', 'hardening']);
const legacyOverrides = ['DODREAM_RESULTS_DIR', 'DODREAM_AUTH_BROWSER_ORIGIN', 'DODREAM_AUTHZ_BROWSER_ORIGIN',
  'DODREAM_GRADING_BROWSER_ORIGIN', 'DODREAM_INDEX_BROWSER_ORIGIN', 'DODREAM_AUTHZ_BROWSER_TITLE', 'DODREAM_GRADING_BROWSER_TITLE'];
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function requireValue(condition, message) {
  if (!condition) throw Object.assign(new Error(message), { name: 'IsolatedRuntimeConfigurationError' });
}
function within(directory, target) {
  const relative = path.relative(directory, target);
  return relative === '' || (!path.isAbsolute(relative) && relative !== '..' && !relative.startsWith('..' + path.sep));
}
function exactKeys(value, expected) {
  return value !== null && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).length === expected.length && expected.every(key => Object.hasOwn(value, key));
}

// Check existing ancestors even when a future result/fixture directory is not yet present.
// Refusing symlinks and multiply linked input files avoids following legacy data through aliases.
async function confinedPath(directory, target, io, mustExist = false) {
  requireValue(within(directory, target), 'Path must remain inside its declared trial directory');
  const relative = path.relative(directory, target);
  const parts = relative ? relative.split(path.sep) : [];
  let current = directory;
  for (let index = 0; index <= parts.length; index++) {
    let stat;
    try { stat = await io.lstat(current); }
    catch (error) {
      if (error.code !== 'ENOENT') throw error;
      requireValue(!mustExist, 'Required isolated trial path is missing');
      return target;
    }
    requireValue(!stat.isSymbolicLink(), 'Isolated trial paths may not use symlinks');
    requireValue(!stat.isFile() || stat.nlink === 1, 'Isolated trial input may not share a hard link');
    if (index < parts.length) {
      requireValue(stat.isDirectory(), 'Isolated trial ancestor must be a directory');
      current = path.join(current, parts[index]);
    }
  }
  return target;
}

export async function loadIsolatedRuntime(suite, repositoryRoot, environment = process.env, io = fs) {
  requireValue(suites.has(suite), 'Unknown isolated browser suite');
  requireValue(path.isAbsolute(repositoryRoot), 'Explicit repository root required');
  for (const key of legacyOverrides) requireValue(!Object.hasOwn(environment, key), `Legacy override ${key} is not allowed`);
  const manifestPath = environment.DODREAM_ISOLATED_MANIFEST;
  requireValue(typeof manifestPath === 'string' && path.isAbsolute(manifestPath), 'Explicit absolute DODREAM_ISOLATED_MANIFEST required');
  const repository = path.resolve(repositoryRoot);
  requireValue(path.resolve(manifestPath) === path.join(repository, 'scripts/local/isolated-trial.json'), 'Use the reviewed isolated trial manifest');
  await confinedPath(path.parse(repository).root, repository, io, true);
  await confinedPath(repository, manifestPath, io, true);
  const manifest = JSON.parse(await io.readFile(manifestPath, 'utf8'));
  requireValue(exactKeys(manifest, ['schema', 'id', 'project', 'root', 'credentials', 'origins']), 'Missing or unknown manifest settings');
  requireValue(manifest.schema === 1 && typeof manifest.id === 'string' && /^evidence-portability-[0-9]{8}$/.test(manifest.id), 'Unsupported isolated trial identity');
  const date = manifest.id.slice(-8);
  requireValue(manifest.project === `dodream-evidence-${date}`, 'Unexpected isolated project');
  requireValue(manifest.root === `.local/isolated/${manifest.id}`, 'Trial root must use the isolated trial namespace');
  requireValue(manifest.credentials === 'credentials.env', 'Credentials must be newly generated inside the trial root');
  requireValue(exactKeys(manifest.origins, ['main', 'short']), 'Both explicit origins are required');
  for (const key of ['main', 'short']) {
    let origin;
    try { origin = new URL(manifest.origins?.[key]); } catch { requireValue(false, 'Explicit isolated browser endpoint required'); }
    requireValue(origin.protocol === 'http:' && origin.hostname === '127.0.0.1' && origin.origin === manifest.origins[key] &&
      !origin.username && !origin.password && Number(origin.port) >= 20000 && Number(origin.port) <= 60000, 'Unexpected isolated browser endpoint');
  }
  requireValue(manifest.origins.main !== manifest.origins.short, 'Main and short browser endpoints must differ');
  const trialRoot = path.join(repository, manifest.root);
  await confinedPath(repository, trialRoot, io);
  const hasAttempt = Object.hasOwn(environment, 'DODREAM_ISOLATED_ATTEMPT');
  const attemptId = hasAttempt ? environment.DODREAM_ISOLATED_ATTEMPT : null;
  requireValue(!hasAttempt || (typeof attemptId === 'string' && /^[a-z][a-z0-9-]{0,47}$/.test(attemptId)),
    'Explicit bounded isolated attempt identifier required');
  const attemptRoot = hasAttempt ? path.join(trialRoot, 'attempts', attemptId) : trialRoot;
  let attemptRunId = null;
  if (hasAttempt) {
    const receiptPath = path.join(attemptRoot, 'attempt.json');
    await confinedPath(repository, receiptPath, io, true);
    const receipt = JSON.parse(await io.readFile(receiptPath, 'utf8'));
    requireValue(receipt.schema === 1 && receipt.attemptId === attemptId && receipt.trialId === manifest.id &&
      receipt.project === manifest.project && uuid.test(receipt.runId), 'Matching isolated attempt receipt required');
    attemptRunId = receipt.runId;
  }
  const runtime = { suite, trialId: manifest.id, project: manifest.project, repositoryRoot: repository, manifestPath,
    trialRoot, attemptId, attemptRoot, attemptRunId,
    origin: manifest.origins[['auth', 'demo-disabled'].includes(suite) ? 'short' : 'main'],
    shortOrigin: manifest.origins.short, resultsDir: path.join(attemptRoot, 'results'),
    planDir: path.join(attemptRoot, 'browser-ui'), fixtureDir: path.join(attemptRoot, 'fixtures'),
    credentialsPath: path.join(trialRoot, manifest.credentials) };
  for (const target of [runtime.resultsDir, runtime.planDir, runtime.fixtureDir, runtime.credentialsPath]) {
    await confinedPath(repository, target, io);
  }
  return Object.freeze(runtime);
}

function validateOwnership(runtime, data) {
  requireValue(data.trialId === runtime.trialId && data.project === runtime.project && data.suite === runtime.suite &&
    data.origin === runtime.origin && data.syntheticOnly === true && uuid.test(data.runId), 'Fresh synthetic trial receipt required');
  requireValue(runtime.attemptId === null ? !Object.hasOwn(data, 'attemptId') || data.attemptId === null :
    data.attemptId === runtime.attemptId && data.runId === runtime.attemptRunId, 'Fixture or plan belongs to another attempt');
}

export async function readTrialFixture(runtime, io = fs) {
  const filename = path.join(runtime.fixtureDir, runtime.suite + '.json');
  await confinedPath(runtime.repositoryRoot, filename, io, true);
  const fixture = JSON.parse(await io.readFile(filename, 'utf8'));
  validateOwnership(runtime, fixture);
  const requiredText = { auth: ['teacherEmail'], authorization: ['ownerEmail', 'otherEmail', 'studentDeviceId', 'lessonTitle'],
    grading: ['ownerEmail', 'studentDeviceId', 'lessonTitle'], indexing: ['ownerEmail'], student: ['teacherEmail'],
    hardening: ['teacherEmail'], 'demo-disabled': [] }[runtime.suite];
  for (const key of requiredText) requireValue(typeof fixture[key] === 'string' && fixture[key].length > 0, `Fresh fixture requires ${key}`);
  if (runtime.suite === 'hardening') requireValue(Number.isSafeInteger(fixture.unauthorizedStudentId) && fixture.unauthorizedStudentId > 0,
    'Fresh boundary student identifier required');
  return Object.freeze(fixture);
}

export async function readTrialCredentials(runtime, fixture, io = fs) {
  // Deliberately separate from configuration/plan inspection. Called only in a future real browser run.
  validateOwnership(runtime, fixture);
  await confinedPath(runtime.repositoryRoot, runtime.credentialsPath, io, true);
  const settings = {};
  const allowed = new Set(['DODREAM_TRIAL_ID', 'DODREAM_TRIAL_RUN_ID', 'ISOLATED_MYSQL_PASSWORD', 'ISOLATED_MYSQL_ROOT_PASSWORD',
    'ISOLATED_JWT_SECRET_BASE64', 'ISOLATED_TEACHER_PASSWORD', 'ISOLATED_STUDENT_SECRET']);
  for (const line of (await io.readFile(runtime.credentialsPath, 'utf8')).split('\n')) {
    if (!line || line.startsWith('#')) continue;
    const separator = line.indexOf('=');
    requireValue(separator > 0, 'Invalid generated trial credential file');
    const key = line.slice(0, separator);
    requireValue(allowed.has(key) && !Object.hasOwn(settings, key), 'Unexpected or duplicate generated trial credential key');
    settings[key] = line.slice(separator + 1);
  }
  requireValue(settings.DODREAM_TRIAL_ID === runtime.trialId && settings.DODREAM_TRIAL_RUN_ID === fixture.runId,
    'Credential file must belong to this new trial run');
  requireValue(typeof settings.ISOLATED_TEACHER_PASSWORD === 'string' && settings.ISOLATED_TEACHER_PASSWORD.length > 0,
    'New trial teacher credential required');
  if (['authorization', 'grading'].includes(runtime.suite)) requireValue(typeof settings.ISOLATED_STUDENT_SECRET === 'string' && settings.ISOLATED_STUDENT_SECRET.length > 0,
    'New trial student credential required');
  return { LOCAL_TEACHER_PASSWORD: settings.ISOLATED_TEACHER_PASSWORD, LOCAL_STUDENT_SECRET: settings.ISOLATED_STUDENT_SECRET };
}

export async function readTrialBrowserPlan(runtime, fixture, environment = process.env, io = fs) {
  validateOwnership(runtime, fixture);
  const key = { indexing: 'DODREAM_INDEX_BROWSER_PLAN', student: 'DODREAM_STUDENT_BROWSER_PLAN' }[runtime.suite];
  requireValue(key, 'This suite has no browser handshake plan');
  const filename = environment[key];
  requireValue(typeof filename === 'string' && path.isAbsolute(filename) && path.dirname(filename) === runtime.planDir && filename.endsWith('.json'),
    'Explicit browser plan inside this trial browser-ui directory required');
  await confinedPath(runtime.repositoryRoot, filename, io, true);
  const plan = JSON.parse(await io.readFile(filename, 'utf8'));
  validateOwnership(runtime, plan);
  requireValue(plan.runId === fixture.runId, 'Browser plan must match the fresh fixture run');
  if (runtime.suite === 'student') requireValue(plan.teacherEmail === fixture.teacherEmail, 'Student plan teacher must match the fresh fixture');
  return { plan, filename };
}

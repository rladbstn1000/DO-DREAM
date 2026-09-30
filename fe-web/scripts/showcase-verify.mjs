import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { WEB_ROOT, REPO_ROOT, SHOWCASE_MIME, ensureResultsDirectory, listFiles, writeEvidence } from './showcase-paths.mjs';
import { auditShowcase, inspectArtifact, SYNTHETIC_SENTINELS } from './showcase-audit.mjs';
import { startShowcaseServer } from './showcase-server.mjs';

if (process.argv.length !== 2) throw new Error('verify:showcase accepts no overrides');
const results = ensureResultsDirectory();
const runId = new Date().toISOString().replace(/[:.]/g, '-');
const commands = [];
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';

function sourceDigest() {
  const sources = ['src', 'showcase', 'scripts', 'tests'].flatMap((directory) => listFiles(path.join(WEB_ROOT, directory)));
  sources.push(...['package.json', 'package-lock.json', 'vite.config.ts', 'vite.showcase.config.ts', 'tsconfig.app.json', 'tsconfig.node.json'].map((name) => path.join(WEB_ROOT, name)));
  const hash = crypto.createHash('sha256');
  for (const filename of sources.sort()) {
    hash.update(path.relative(WEB_ROOT, filename));
    hash.update(fs.readFileSync(filename));
  }
  return hash.digest('hex');
}

async function run(label, args, sentinel = false) {
  const started = new Date().toISOString();
  const logfile = path.join(results, `${runId}-${label}.log`);
  const output = fs.createWriteStream(logfile, { flags: 'wx' });
  const ownProcessGroup = process.platform !== 'win32';
  const child = spawn(npm, args, { cwd: WEB_ROOT, env: sentinel ? { ...process.env, ...SYNTHETIC_SENTINELS, NODE_ENV: 'development' } : process.env, stdio: ['ignore', 'pipe', 'pipe'], detached: ownProcessGroup });
  let killDeadline;
  const stopOwnCommand = (signal) => {
    try { ownProcessGroup ? process.kill(-child.pid, signal) : child.kill(signal); }
    catch (error) { if (error.code !== 'ESRCH') throw error; }
  };
  const timeout = setTimeout(() => {
    stopOwnCommand('SIGTERM');
    killDeadline = setTimeout(() => stopOwnCommand('SIGKILL'), 10_000);
  }, 240_000);
  child.stdout.on('data', (data) => { output.write(data); process.stdout.write(data); });
  child.stderr.on('data', (data) => { output.write(data); process.stderr.write(data); });
  const exitCode = await new Promise((resolve, reject) => { child.once('error', reject); child.once('close', resolve); });
  clearTimeout(timeout);
  clearTimeout(killDeadline);
  await new Promise((resolve) => output.end(resolve));
  commands.push({ label, command: `npm ${args.join(' ')}`, started, finished: new Date().toISOString(), exitCode, log: path.basename(logfile) });
  if (exitCode !== 0) throw new Error(`${label} failed with exit ${exitCode}`);
}

async function serverBoundaries(artifact) {
  const server = await startShowcaseServer();
  let checks = 0;
  try {
    for (const prefix of ['', '/DO-DREAM']) {
      const root = await fetch(`${server.origin}${prefix}/`);
      assert.equal(root.status, 200);
      assert.equal(root.headers.get('content-type'), 'text/html; charset=utf-8');
      checks += 1;
      // Every current manifest file, including original images/font/notice, must
      // have the same bytes and MIME at both static deployment prefixes.
      for (const file of artifact.files) {
        const response = await fetch(`${server.origin}${prefix}/${file.path}`);
        assert.equal(response.status, 200);
        assert.equal(response.headers.get('content-type'), SHOWCASE_MIME[path.extname(file.path)]);
        const bytes = Buffer.from(await response.arrayBuffer());
        assert.equal(bytes.length, file.bytes);
        assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), file.sha256);
        checks += 1;
      }
      for (const url of ['/missing-route', '/api/session/me', '/.env', '/.git/config', '/src/showcase/main.tsx']) {
        assert.equal((await fetch(`${server.origin}${prefix}${url}`)).status, 404);
        checks += 1;
      }
      assert.equal((await fetch(`${server.origin}${prefix}/`, { method: 'POST', body: 'synthetic boundary probe' })).status, 405);
      checks += 1;
    }
    return { origin: server.origin, checks, requests: server.requests };
  } finally { await server.close(); }
}

const initialSource = sourceDigest();
let result = { runId, status: 'RUNNING', commands, sourceDigest: initialSource };
try {
  await run('typecheck', ['run', 'typecheck']);
  await run('showcase-contracts', ['run', 'test:showcase']);
  await run('showcase-build-sentinel', ['run', 'build:showcase'], true);
  await run('phase1-build', ['run', 'build', '--', '--mode', 'phase1']);
  const artifact = auditShowcase();
  const server = await serverBoundaries(artifact);
  await run('showcase-browser', ['run', 'test:showcase-browser']);
  assert.equal(inspectArtifact().manifestDigest, artifact.manifestDigest, 'Artifact changed during acceptance');
  assert.equal(sourceDigest(), initialSource, 'Application or check sources changed during this single acceptance run');
  result = { ...result, status: 'PASS', artifact, server, sourceAndArtifactUnchanged: true };
} catch (error) {
  result = { ...result, status: 'FAIL', error: String(error?.message ?? error) };
  process.exitCode = 1;
} finally {
  const evidence = writeEvidence('verify-showcase', result);
  console.log(`Showcase verification ${result.status}; evidence: ${path.relative(REPO_ROOT, evidence.timestamped)}`);
}

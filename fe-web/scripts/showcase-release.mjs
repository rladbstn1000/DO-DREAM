import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { assertArtifactManifest, inspectArtifact } from './showcase-audit.mjs';
import { REPO_ROOT, RESULTS_DIR, SHOWCASE_OUT, assertNoSymlinkChain, listFiles } from './showcase-paths.mjs';

export function assertReleaseContext(context) {
  assert.equal(context.actions, 'true');
  assert.equal(context.runner, 'github-hosted');
  assert.equal(context.os, 'Linux');
  assert.equal(context.platform, 'linux');
  assert.equal(context.repository, 'rladbstn1000/DO-DREAM');
  assert.equal(context.event, 'workflow_dispatch');
  assert.equal(context.ref, 'refs/heads/main');
  assert.match(context.sourceSha ?? '', /^[0-9a-f]{40}$/);
  assert.equal(context.sourceSha, context.expectedSha, 'Dispatched main differs from the reviewed expected SHA');
  assert.match(context.runId ?? '', /^[1-9][0-9]*$/);
  assert.match(context.runAttempt ?? '', /^[1-9][0-9]*$/);
  assert.equal(context.serverUrl, 'https://github.com');
  const site = new URL(context.pagesBaseUrl);
  assert.equal(site.origin, 'https://rladbstn1000.github.io');
  assert.equal(site.pathname.replace(/\/$/, ''), '/DO-DREAM');
  assert.equal(site.search + site.hash + site.username + site.password, '');
}

export function makeReleaseManifest({ context, gitSha, tools, verification, browser, currentArtifact, browserArtifactDigest }) {
  assertReleaseContext(context);
  assert.equal(gitSha, context.sourceSha, 'Checked-out source differs from workflow SHA');
  assert.equal(tools.node, 'v22.22.0');
  assert.match(tools.npm, /^\d+\.\d+\.\d+$/);
  assert.equal(tools.chromePath, '/opt/google/chrome/chrome');
  assert.match(tools.chromeVersion, /^Google Chrome \d+\.\d+\.\d+\.\d+$/);
  assert.match(tools.playwright, /^\d+\.\d+\.\d+$/);
  assert.equal(verification.status, 'PASS');
  assert.equal(verification.sourceAndArtifactUnchanged, true);
  const expectedCommands = ['typecheck', 'showcase-contracts', 'showcase-build-sentinel', 'phase1-build', 'showcase-browser'];
  assert.deepEqual(verification.commands.map((command) => command.label), expectedCommands);
  assert.ok(verification.commands.every((command) => command.exitCode === 0));
  assertArtifactManifest(currentArtifact);
  assertArtifactManifest(verification.artifact);
  assert.equal(verification.artifact.manifestDigest, currentArtifact.manifestDigest, 'Verified output changed before release');
  assert.deepEqual(verification.artifact.files.map(({ path, bytes, sha256 }) => ({ path, bytes, sha256 })), currentArtifact.files.map(({ path, bytes, sha256 }) => ({ path, bytes, sha256 })));
  assert.equal(browser.status, 'PASS');
  assert.ok(browser.checks.length > 0 && browser.checks.every((check) => check.status === 'PASS'));
  assert.equal(browser.counts.checks, browser.checks.length);
  for (const key of ['forbiddenRequestAttempts', 'apiAttemptsBeforeCsp', 'webSocketAttempts', 'cspViolations', 'microphoneAttempts']) assert.equal(browser.counts[key], 0);
  assert.ok(browser.counts.staticRequests > 0);
  assert.deepEqual(browser.browserErrors, []);
  assert.equal(browser.runtime.platform, 'linux');
  assert.equal(browser.runtime.node, tools.node);
  assert.equal(browser.runtime.channel, 'chrome');
  assert.equal(browser.runtime.browserVersion, tools.chromeVersion.replace('Google Chrome ', ''));
  assert.equal(browser.artifactDigest, browserArtifactDigest, 'Browser accepted different artifact bytes');
  const started = verification.commands.at(-1).started;
  const finished = verification.commands.at(-1).finished;
  const browserTime = browser.timestamp.replace(/T(\d{2})(\d{2})(\d{2})(\d{3})Z$/, 'T$1:$2:$3.$4Z');
  assert.ok(Date.parse(browserTime) >= Date.parse(started) && Date.parse(browserTime) <= Date.parse(finished), 'Browser evidence is stale or outside the verification run');
  return {
    schemaVersion: 1,
    repository: context.repository,
    sourceSha: context.sourceSha,
    runId: context.runId,
    runAttempt: context.runAttempt,
    runUrl: `${context.serverUrl}/${context.repository}/actions/runs/${context.runId}`,
    tools: { node: tools.node, npm: tools.npm, chromePath: tools.chromePath, chromeVersion: tools.chromeVersion, playwright: tools.playwright },
    verification: { status: 'PASS', sourceAndArtifactUnchanged: true, browserChecks: browser.counts.checks, staticRequests: browser.counts.staticRequests, forbiddenRequestAttempts: 0 },
    artifact: { fileCount: currentArtifact.fileCount, totalBytes: currentArtifact.totalBytes, manifestDigest: currentArtifact.manifestDigest, files: currentArtifact.files.map(({ path, bytes, sha256 }) => ({ path, bytes, sha256 })) },
  };
}

function browserDigest() {
  const hash = crypto.createHash('sha256');
  for (const filename of listFiles(SHOWCASE_OUT)) hash.update(path.relative(SHOWCASE_OUT, filename).replaceAll(path.sep, '/')).update('\0').update(fs.readFileSync(filename)).update('\0');
  return hash.digest('hex');
}

function main() {
  assert.equal(process.argv.length, 2, 'Release provenance accepts no overrides');
  const context = {
    actions: process.env.GITHUB_ACTIONS, runner: process.env.RUNNER_ENVIRONMENT, os: process.env.RUNNER_OS, platform: process.platform,
    repository: process.env.GITHUB_REPOSITORY, event: process.env.GITHUB_EVENT_NAME, ref: process.env.GITHUB_REF,
    sourceSha: process.env.GITHUB_SHA, expectedSha: process.env.EXPECTED_SOURCE_SHA, runId: process.env.GITHUB_RUN_ID, runAttempt: process.env.GITHUB_RUN_ATTEMPT,
    serverUrl: process.env.GITHUB_SERVER_URL, pagesBaseUrl: process.env.PAGES_BASE_URL,
  };
  assertReleaseContext(context);
  const command = (program, args) => execFileSync(program, args, { cwd: REPO_ROOT, encoding: 'utf8', timeout: 15_000 }).trim();
  const tools = {
    node: process.version, npm: command('npm', ['--version']), chromePath: '/opt/google/chrome/chrome',
    chromeVersion: command('/opt/google/chrome/chrome', ['--version']),
    playwright: JSON.parse(fs.readFileSync(path.join(REPO_ROOT, 'fe-web/node_modules/playwright-core/package.json'), 'utf8')).version,
  };
  const read = (name) => JSON.parse(fs.readFileSync(path.join(RESULTS_DIR, name), 'utf8'));
  const manifest = makeReleaseManifest({ context, gitSha: command('git', ['rev-parse', 'HEAD']), tools,
    verification: read('verify-showcase.json'), browser: read('showcase-browser-latest.json'),
    currentArtifact: inspectArtifact(), browserArtifactDigest: browserDigest() });
  const filename = assertNoSymlinkChain(path.join(RESULTS_DIR, 'release-manifest.json'));
  fs.writeFileSync(filename, `${JSON.stringify(manifest, null, 2)}\n`, { flag: 'wx' });
  fs.appendFileSync(process.env.GITHUB_OUTPUT, `source_sha=${manifest.sourceSha}\nmanifest_digest=${manifest.artifact.manifestDigest}\n`);
  const rows = manifest.artifact.files.map((file) => `| \`${file.path}\` | ${file.bytes} | \`${file.sha256}\` |`).join('\n');
  fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `### Verified showcase release\n\n- Source: \`${manifest.sourceSha}\`\n- Run: ${manifest.runUrl} (attempt ${manifest.runAttempt})\n- Node: ${tools.node}; npm: ${tools.npm}; Playwright: ${tools.playwright}\n- Chrome: ${tools.chromeVersion} at \`${tools.chromePath}\`\n- Browser checks: ${manifest.verification.browserChecks}; static requests: ${manifest.verification.staticRequests}; forbidden attempts: 0\n- Manifest digest: \`${manifest.artifact.manifestDigest}\`\n- Files: ${manifest.artifact.fileCount}; bytes: ${manifest.artifact.totalBytes}\n\n| Public file | Bytes | SHA-256 |\n|---|---:|---|\n${rows}\n\nOnly \`fe-web/dist-showcase\` is uploaded for Pages. The separate \`showcase-provenance\` artifact contains just \`release-manifest.json\`, without raw browser logs or screenshots.\n`);
  console.log(`Release provenance PASS: ${manifest.sourceSha}, ${manifest.artifact.manifestDigest}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();

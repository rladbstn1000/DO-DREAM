import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import yaml from 'js-yaml';
import { assertReleaseContext, makeReleaseManifest } from '../scripts/showcase-release.mjs';
import { artifactManifestDigest } from '../scripts/showcase-audit.mjs';
import { REVIEWED_ASSETS } from '../scripts/showcase-paths.mjs';
import { validatePageUrl, validateReleaseManifest } from './showcase-public-browser.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const workflow = yaml.load(fs.readFileSync(path.join(root, '.github/workflows/showcase-pages.yml'), 'utf8'));
const sha = 'a'.repeat(40);

function fixture() {
  const image = REVIEWED_ASSETS.find(({ source }) => source.endsWith('.jpg'));
  const files = [{ path: 'assets/background-original.jpg', bytes: image.bytes, sha256: image.sha256 },
    { path: 'assets/main.css', bytes: 12, sha256: 'c'.repeat(64) }, { path: 'assets/main.js', bytes: 12, sha256: 'c'.repeat(64) },
    { path: 'index.html', bytes: 12, sha256: 'c'.repeat(64) }];
  const artifact = { fileCount: files.length, totalBytes: files.reduce((sum, file) => sum + file.bytes, 0), manifestDigest: artifactManifestDigest(files), files };
  return {
    context: { actions: 'true', runner: 'github-hosted', os: 'Linux', platform: 'linux', repository: 'rladbstn1000/DO-DREAM', event: 'workflow_dispatch', ref: 'refs/heads/main', sourceSha: sha, expectedSha: sha, runId: '12345', runAttempt: '1', serverUrl: 'https://github.com', pagesBaseUrl: 'https://rladbstn1000.github.io/DO-DREAM' },
    gitSha: sha,
    tools: { node: 'v22.22.0', npm: '10.9.4', chromePath: '/opt/google/chrome/chrome', chromeVersion: 'Google Chrome 154.0.1.2', playwright: '1.62.1' },
    verification: { status: 'PASS', sourceAndArtifactUnchanged: true, artifact: structuredClone(artifact), commands: ['typecheck', 'showcase-contracts', 'showcase-build-sentinel', 'phase1-build', 'showcase-browser'].map((label) => ({ label, exitCode: 0, started: '2026-10-01T00:00:00.000Z', finished: '2026-10-01T00:00:02.000Z' })) },
    browser: { status: 'PASS', timestamp: '2026-10-01T000001000Z', runtime: { node: 'v22.22.0', platform: 'linux', channel: 'chrome', browserVersion: '154.0.1.2' }, artifactDigest: 'd'.repeat(64), checks: [{ status: 'PASS' }], browserErrors: [], counts: { checks: 1, staticRequests: 3, forbiddenRequestAttempts: 0, apiAttemptsBeforeCsp: 0, webSocketAttempts: 0, cspViolations: 0, microphoneAttempts: 0 } },
    currentArtifact: artifact,
    browserArtifactDigest: 'd'.repeat(64),
  };
}

test('release context rejects fork, arbitrary ref/event, self-hosted or local execution', () => {
  const { context } = fixture();
  assert.doesNotThrow(() => assertReleaseContext(context));
  for (const patch of [{ actions: 'false' }, { runner: 'self-hosted' }, { os: 'macOS' }, { platform: 'darwin' }, { repository: 'other/DO-DREAM' }, { event: 'push' }, { event: 'pull_request' }, { ref: 'refs/heads/feature' }, { ref: 'refs/tags/main' }, { sourceSha: 'main' }, { expectedSha: 'f'.repeat(40) }, { expectedSha: undefined }, { runId: '../1' }, { pagesBaseUrl: 'https://unapproved.example/DO-DREAM' }, { pagesBaseUrl: 'https://rladbstn1000.github.io/another' }]) {
    assert.throws(() => assertReleaseContext({ ...context, ...patch }), JSON.stringify(patch));
  }
});

test('provenance contains only selected public fields and verified file digests', () => {
  const inputs = fixture();
  inputs.verification.privateRawTrace = 'SYNTHETIC_PRIVATE_NOT_FOR_ARTIFACT';
  inputs.browser.network = { sampleAnswer: 'SYNTHETIC_PRIVATE_NOT_FOR_ARTIFACT' };
  inputs.tools.unreviewedExtra = 'SYNTHETIC_PRIVATE_NOT_FOR_ARTIFACT';
  const manifest = makeReleaseManifest(inputs);
  assert.equal(manifest.schemaVersion, 1);
  assert.equal(manifest.sourceSha, sha);
  assert.equal(manifest.artifact.manifestDigest, inputs.currentArtifact.manifestDigest);
  assert.equal(manifest.runUrl, 'https://github.com/rladbstn1000/DO-DREAM/actions/runs/12345');
  assert.deepEqual(manifest.artifact.files, inputs.currentArtifact.files);
  assert.ok(!JSON.stringify(manifest).includes('SYNTHETIC_PRIVATE_NOT_FOR_ARTIFACT'));
});

test('public acceptance validates the dynamic reviewed asset set without contacting any URL', () => {
  const manifest = makeReleaseManifest(fixture());
  assert.equal(validateReleaseManifest(manifest), manifest);
  assert.equal(validatePageUrl('https://rladbstn1000.github.io/DO-DREAM/'), 'https://rladbstn1000.github.io/DO-DREAM/');
  for (const url of ['http://127.0.0.1:8080/', 'https://unreviewed.invalid/DO-DREAM/', 'https://rladbstn1000.github.io/DO-DREAM/?mode=real']) assert.throws(() => validatePageUrl(url));
  const malformed = structuredClone(manifest);
  malformed.artifact.files[0].sha256 = 'e'.repeat(64);
  malformed.artifact.manifestDigest = artifactManifestDigest(malformed.artifact.files);
  assert.throws(() => validateReleaseManifest(malformed), /Unreviewed static asset/);
});

test('provenance refuses changed bytes, unverified source or stale browser evidence', () => {
  const changes = [
    (x) => { x.gitSha = 'f'.repeat(40); },
    (x) => { x.currentArtifact.manifestDigest = 'e'.repeat(64); },
    (x) => { x.currentArtifact.files[0].bytes += 1; },
    (x) => { x.currentArtifact.files.pop(); },
    (x) => { x.currentArtifact.files[0].sha256 = 'e'.repeat(64); x.currentArtifact.manifestDigest = artifactManifestDigest(x.currentArtifact.files); x.verification.artifact = structuredClone(x.currentArtifact); },
    (x) => { x.currentArtifact.files[0].path = '../source.env'; x.currentArtifact.manifestDigest = artifactManifestDigest(x.currentArtifact.files); x.verification.artifact = structuredClone(x.currentArtifact); },
    (x) => { x.browserArtifactDigest = 'e'.repeat(64); },
    (x) => { x.verification.sourceAndArtifactUnchanged = false; },
    (x) => { x.browser.timestamp = '2026-09-30T000001000Z'; },
    (x) => { x.browser.runtime.browserVersion = '1.0.0.0'; },
    (x) => { x.tools.node = 'v24.0.0'; },
  ];
  for (const change of changes) { const inputs = fixture(); change(inputs); assert.throws(() => makeReleaseManifest(inputs)); }
});

test('failed, skipped, missing checks and even aborted network attempts prevent provenance', () => {
  const changes = [
    (x) => { x.verification.status = 'FAIL'; },
    (x) => { x.verification.commands.pop(); },
    (x) => { x.verification.commands[0].exitCode = 1; },
    (x) => { x.browser.status = 'FAIL'; },
    (x) => { x.browser.checks[0].status = 'SKIP'; },
    (x) => { x.browser.checks = []; },
    (x) => { x.browser.browserErrors.push('synthetic error'); },
    ...['forbiddenRequestAttempts', 'apiAttemptsBeforeCsp', 'webSocketAttempts', 'cspViolations', 'microphoneAttempts'].map((key) => (x) => { x.browser.counts[key] = 1; }),
  ];
  for (const change of changes) { const inputs = fixture(); change(inputs); assert.throws(() => makeReleaseManifest(inputs)); }
});

test('workflow permits only manual main on the approved repository with minimal separated permissions', () => {
  assert.deepEqual(workflow.on, { workflow_dispatch: { inputs: { expected_sha: { description: 'Reviewed main commit whose required CI has passed', required: true, type: 'string' } } } });
  assert.deepEqual(workflow.permissions, { contents: 'read' });
  assert.deepEqual(workflow.concurrency, { group: 'dodream-showcase-pages', 'cancel-in-progress': false });
  assert.deepEqual(Object.keys(workflow.jobs), ['build', 'deploy']);
  const { build, deploy } = workflow.jobs;
  assert.deepEqual(build.permissions, { contents: 'read', pages: 'read' });
  assert.deepEqual(deploy.permissions, { pages: 'write', 'id-token': 'write' });
  const gate = build.steps[0];
  assert.equal(gate.env.RELEASE_REPOSITORY, '${{ github.repository }}');
  assert.equal(gate.env.RELEASE_EVENT, '${{ github.event_name }}');
  assert.equal(gate.env.RELEASE_REF, '${{ github.ref }}');
  assert.equal(gate.env.RELEASE_SHA, '${{ github.sha }}');
  assert.equal(gate.env.EXPECTED_SHA, '${{ inputs.expected_sha }}');
  assert.ok(gate.run.includes(`test "$RELEASE_REPOSITORY" = 'rladbstn1000/DO-DREAM'`));
  assert.ok(gate.run.includes(`test "$RELEASE_EVENT" = 'workflow_dispatch'`));
  assert.ok(gate.run.includes(`test "$RELEASE_REF" = 'refs/heads/main'`));
  assert.ok(gate.run.includes('[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]'));
  assert.ok(gate.run.includes('test "$RELEASE_SHA" = "$EXPECTED_SHA"'));
  assert.equal(deploy.needs, 'build');
  for (const guard of ["github.repository == 'rladbstn1000/DO-DREAM'", "github.event_name == 'workflow_dispatch'", "github.ref == 'refs/heads/main'", "needs.build.result == 'success'"]) assert.ok(deploy.if.includes(guard));
  assert.deepEqual(deploy.environment, { name: 'github-pages', url: '${{ steps.deployment.outputs.page_url }}' });
  for (const job of Object.values(workflow.jobs)) {
    assert.equal(job['runs-on'], 'ubuntu-24.04');
    assert.ok(job['timeout-minutes'] <= 15);
    assert.equal(job['continue-on-error'], undefined);
    for (const step of job.steps) {
      assert.equal(step['continue-on-error'], undefined);
      assert.equal(step.if, undefined);
      if (step.uses) assert.match(step.uses, /^actions\/[a-z-]+@[0-9a-f]{40}$/);
    }
  }
});

test('workflow uploads exactly the accepted directory and one sanitized manifest without rebuilding', () => {
  const { build, deploy } = workflow.jobs;
  const checkout = build.steps.find((step) => step.uses?.startsWith('actions/checkout@'));
  assert.deepEqual(checkout.with, { ref: '${{ github.sha }}', 'persist-credentials': false });
  assert.equal(build.steps.find((step) => step.uses?.startsWith('actions/setup-node@')).with['node-version'], '22.22.0');
  assert.deepEqual(build.steps.find((step) => step.uses?.startsWith('actions/configure-pages@')).with, { enablement: false });
  const verified = build.steps.findIndex((step) => step.run === 'npm run verify:showcase');
  assert.ok(verified > 0);
  const tail = build.steps.slice(verified + 1);
  assert.equal(tail.length, 3);
  assert.equal(tail[0].run, 'node fe-web/scripts/showcase-release.mjs');
  assert.equal(tail[0].env.EXPECTED_SOURCE_SHA, '${{ inputs.expected_sha }}');
  assert.ok(tail[1].uses.startsWith('actions/upload-pages-artifact@'));
  assert.deepEqual(tail[1].with, { name: 'github-pages', path: 'fe-web/dist-showcase', 'retention-days': 1, 'include-hidden-files': false });
  assert.ok(tail[2].uses.startsWith('actions/upload-artifact@'));
  assert.deepEqual(tail[2].with, { name: 'showcase-provenance', path: '.local/static-showcase/results/release-manifest.json', 'if-no-files-found': 'error', 'retention-days': 7, 'include-hidden-files': true, overwrite: false });
  assert.equal(deploy.steps.length, 2);
  assert.ok(deploy.steps[0].uses.startsWith('actions/deploy-pages@'));
  assert.deepEqual(deploy.steps[0].with, { artifact_name: 'github-pages', timeout: '540000' });
  assert.ok(!deploy.steps[1].run.includes('npm'));
});

test('the actual first-step shell guard fails closed for dispatch parameter manipulation', () => {
  const gate = workflow.jobs.build.steps[0].run;
  const valid = { RELEASE_REPOSITORY: 'rladbstn1000/DO-DREAM', RELEASE_EVENT: 'workflow_dispatch', RELEASE_REF: 'refs/heads/main', RELEASE_SHA: sha, EXPECTED_SHA: sha };
  assert.equal(spawnSync('/bin/bash', ['-e', '-c', gate], { env: valid }).status, 0);
  for (const patch of [{ RELEASE_REPOSITORY: 'fork/DO-DREAM' }, { RELEASE_EVENT: 'push' }, { RELEASE_REF: 'refs/heads/feature' }, { RELEASE_SHA: 'f'.repeat(40) }, { EXPECTED_SHA: 'A'.repeat(40) }, { EXPECTED_SHA: '' }, { EXPECTED_SHA: `"; exit 0; #` }, { EXPECTED_SHA: `${sha}\n${sha}` }]) {
    assert.notEqual(spawnSync('/bin/bash', ['-e', '-c', gate], { env: { ...valid, ...patch } }).status, 0, JSON.stringify(patch));
  }
});

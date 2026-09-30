import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { resolveConfig } from 'vite';
import { WEB_ROOT, assertSafeOutput, assertShowcaseBundle } from '../scripts/showcase-paths.mjs';
import { auditBuildGraphs, inspectArtifact, SYNTHETIC_SENTINELS } from '../scripts/showcase-audit.mjs';

function temporary(t) {
  const directory = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'dodream-showcase-boundary-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return directory;
}

test('the output guard accepts only the dedicated absolute output directory', (t) => {
  const project = temporary(t);
  const sentinel = path.join(project, 'source-must-remain.txt');
  fs.writeFileSync(sentinel, 'synthetic source');
  assert.equal(assertSafeOutput(project, path.join(project, 'dist-showcase')), path.join(project, 'dist-showcase'));
  for (const candidate of [project, path.dirname(project), path.join(project, 'dist'), path.join(project, 'src'), 'dist-showcase']) {
    assert.throws(() => assertSafeOutput(project, candidate), /fixed dist-showcase/);
  }
  assert.equal(fs.readFileSync(sentinel, 'utf8'), 'synthetic source');
});

test('output and descendant symlinks are rejected without touching their targets', (t) => {
  const project = temporary(t);
  const other = temporary(t);
  fs.writeFileSync(path.join(other, 'keep.txt'), 'synthetic user file');
  const output = path.join(project, 'dist-showcase');
  fs.symlinkSync(other, output, 'dir');
  assert.throws(() => assertSafeOutput(project, output), /Symbolic links/);
  fs.unlinkSync(output);
  fs.mkdirSync(output);
  fs.symlinkSync(other, path.join(output, 'assets'), 'dir');
  assert.throws(() => assertSafeOutput(project, output), /Symbolic links/);
  assert.equal(fs.readFileSync(path.join(other, 'keep.txt'), 'utf8'), 'synthetic user file');
});

test('a symlink in the project ancestor chain is rejected', (t) => {
  const base = temporary(t);
  const target = temporary(t);
  fs.symlinkSync(target, path.join(base, 'linked'), 'dir');
  assert.throws(() => assertSafeOutput(path.join(base, 'linked'), path.join(base, 'linked', 'dist-showcase')), /Symbolic links/);
});

test('emitted chunk and asset filenames cannot escape even a valid output root', () => {
  assert.doesNotThrow(() => assertShowcaseBundle({ 'index.html': { fileName: 'index.html' }, 'assets/app-123.js': { fileName: 'assets/app-123.js' } }));
  for (const filename of ['../keep.txt', '/absolute.js', 'assets/../../keep.txt', 'assets/../main.js', 'assets\\main.js', '.env', 'manifest.json', 'assets/main.js.map']) {
    assert.throws(() => assertShowcaseBundle({ [filename]: { fileName: filename } }), /outside the reviewed/);
  }
  assert.throws(() => assertShowcaseBundle({ 'assets/good.js': { fileName: '../keep.txt' } }), /outside the reviewed/);
});

test('actual Vite showcase config does not expose inherited VITE or process sentinel values', async () => {
  const previous = new Map(Object.keys(SYNTHETIC_SENTINELS).map((key) => [key, process.env[key]]));
  try {
    Object.assign(process.env, SYNTHETIC_SENTINELS);
    const config = await resolveConfig({ configFile: path.join(WEB_ROOT, 'vite.showcase.config.ts'), mode: 'showcase' }, 'build', 'production', 'production');
    assert.equal(config.envDir, false);
    assert.equal(config.publicDir, '');
    assert.equal(config.server.proxy, undefined);
    assert.equal(config.base, './');
    assert.equal(config.build.sourcemap, false);
    assert.equal(config.build.modulePreload.polyfill, false);
    assert.equal(config.isProduction, true);
    assert.deepEqual(config.css.postcss, { map: false, plugins: [] });
    assert.equal(config.plugins.find((plugin) => plugin.name === 'vite:react-babel')?.transform, undefined);
    assert.deepEqual(Object.keys(config.env).sort(), ['BASE_URL', 'DEV', 'MODE', 'PROD']);
    assert.ok(!Object.values(config.env).some((value) => Object.values(SYNTHETIC_SENTINELS).includes(value)));
  } finally {
    for (const [key, value] of previous) value === undefined ? delete process.env[key] : process.env[key] = value;
  }
});

test('actual Vite config rejects wrong mode and outDir/rollup/base overrides before output cleanup', async (t) => {
  const target = temporary(t);
  fs.writeFileSync(path.join(target, 'keep.txt'), 'synthetic user file');
  const base = { configFile: path.join(WEB_ROOT, 'vite.showcase.config.ts'), mode: 'showcase' };
  await assert.rejects(resolveConfig({ ...base, mode: 'production' }, 'build', 'production', 'production'), /explicit build:showcase/);
  await assert.rejects(resolveConfig({ ...base, build: { outDir: target } }, 'build', 'production', 'production'), /fixed dist-showcase/);
  await assert.rejects(resolveConfig({ ...base, base: 'https://sentinel-cdn.invalid/' }, 'build', 'production', 'production'), /cannot be overridden/);
  await assert.rejects(resolveConfig({ ...base, build: { rollupOptions: { output: { dir: target } } } }, 'build', 'production', 'production'), /cannot be overridden/);
  assert.equal(fs.readFileSync(path.join(target, 'keep.txt'), 'utf8'), 'synthetic user file');
});

function graphs() {
  return [{
    mode: 'showcase', configuration: { base: './', outDir: 'fe-web/dist-showcase', envDir: false, publicDir: false, sourcemap: false, proxyConfigured: false, production: true, envKeys: ['BASE_URL', 'DEV', 'MODE', 'PROD'] },
    modules: [{ id: 'fe-web/src/showcase/main.tsx' }],
  }, { mode: 'phase1', modules: [{ id: 'fe-web/src/main.tsx' }] }];
}

test('graph audit rejects auth/API dependencies and sample imports from the real entry', () => {
  for (const forbidden of ['fe-web/src/auth/client.ts', 'fe-web/src/student/Session.tsx', 'fe-web/src/student/api.ts', 'fe-web/src/pages/Classroom.tsx']) {
    const [showcase, phase1] = graphs();
    showcase.modules.push({ id: forbidden });
    assert.throws(() => auditBuildGraphs(showcase, phase1), /Unreviewed showcase/);
  }
  const [showcase, phase1] = graphs();
  phase1.modules.push({ id: 'fe-web/src/showcase/samples.ts' });
  assert.throws(() => auditBuildGraphs(showcase, phase1), /Real entry must not import/);
});

test('artifact audit rejects private files and development/source-map contents', (t) => {
  const artifact = temporary(t);
  fs.mkdirSync(path.join(artifact, 'assets'));
  fs.writeFileSync(path.join(artifact, 'index.html'), `<meta content="connect-src 'none'"><script src="./assets/main.js"></script><link href="./assets/main.css">`);
  fs.writeFileSync(path.join(artifact, 'assets/main.css'), 'body{color:navy}');
  fs.writeFileSync(path.join(artifact, 'assets/main.js'), 'console.log("synthetic bundle")');
  assert.equal(inspectArtifact(artifact).fileCount, 3);
  fs.writeFileSync(path.join(artifact, '.env'), 'SYNTHETIC_ONLY=yes');
  assert.throws(() => inspectArtifact(artifact), /Unexpected public file/);
  fs.unlinkSync(path.join(artifact, '.env'));
  for (const value of ['//# sourceMappingURL=main.js.map', 'http://127.0.0.1:18082/api/auth', SYNTHETIC_SENTINELS.VITE_API_BASE, 'https://unreviewed.invalid/resource']) {
    fs.writeFileSync(path.join(artifact, 'assets/main.js'), value);
    assert.throws(() => inspectArtifact(artifact));
  }
});

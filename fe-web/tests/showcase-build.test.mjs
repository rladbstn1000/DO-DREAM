import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { resolveConfig } from 'vite';
import { WEB_ROOT, REPO_ROOT, REVIEWED_ASSETS, SHOWCASE_MIME, assertSafeOutput, assertShowcaseBundle, evidenceDirectory, isShowcasePublicFile } from '../scripts/showcase-paths.mjs';
import { auditBuildGraphs, assertArtifactManifest, inspectArtifact, SYNTHETIC_SENTINELS } from '../scripts/showcase-audit.mjs';

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

test('evidence destinations are fixed local choices, never caller-supplied paths', () => {
  assert.equal(evidenceDirectory('original-ui'), path.join(REPO_ROOT, '.local/original-ui/results'));
  assert.equal(evidenceDirectory('original-ui-polish'), path.join(REPO_ROOT, '.local/original-ui-polish/results'));
  assert.equal(evidenceDirectory('original-ui-release'), path.join(REPO_ROOT, '.local/original-ui-release/results'));
  assert.equal(evidenceDirectory('static-showcase'), path.join(REPO_ROOT, '.local/static-showcase/results'));
  for (const value of ['', '..', '/tmp', '../original-ui', 'publication-pages']) assert.throws(() => evidenceDirectory(value), /Unreviewed/);
});

test('reviewed image, font and full license bytes are accepted before write; altered or new assets are refused', () => {
  for (const asset of REVIEWED_ASSETS) {
    const name = `assets/reviewed-${path.basename(asset.source)}`;
    const bytes = fs.readFileSync(path.join(REPO_ROOT, asset.source));
    assert.equal(bytes.length, asset.bytes);
    assert.ok(isShowcasePublicFile(name));
    assert.ok(SHOWCASE_MIME[path.extname(name)]);
    assert.doesNotThrow(() => assertShowcaseBundle({ [name]: { fileName: name, source: bytes } }));
    const altered = Buffer.from(bytes); altered[0] ^= 1;
    assert.throws(() => assertShowcaseBundle({ [name]: { fileName: name, source: altered } }), /Unreviewed static asset/);
  }
  for (const name of ['assets/unreviewed.png', 'assets/unreviewed.svg', 'assets/unreviewed.woff', 'assets/unreviewed.txt']) {
    assert.throws(() => assertShowcaseBundle({ [name]: { fileName: name, source: 'synthetic unreviewed' } }), /Unreviewed static asset/);
  }
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
    assert.equal(config.build.assetsInlineLimit, 0);
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
  await assert.rejects(resolveConfig({ ...base, build: { assetsInlineLimit: 4000 } }, 'build', 'production', 'production'), /cannot be overridden/);
  assert.equal(fs.readFileSync(path.join(target, 'keep.txt'), 'utf8'), 'synthetic user file');
});

function graphs() {
  return [{
    mode: 'showcase', configuration: { base: './', outDir: 'fe-web/dist-showcase', envDir: false, publicDir: false, sourcemap: false, proxyConfigured: false, production: true, envKeys: ['BASE_URL', 'DEV', 'MODE', 'PROD'] },
    modules: [{ id: 'fe-web/src/showcase/main.tsx' }],
  }, { mode: 'phase1', modules: [{ id: 'fe-web/src/main.tsx' }] }];
}

test('graph audit rejects auth/API/native/private paths and sample imports from the real entry', () => {
  for (const forbidden of ['fe-web/src/auth/client.ts', 'fe-web/src/student/Session.tsx', 'fe-web/src/student/api.ts', 'fe-web/src/pages/Classroom.tsx', 'fe_app/src/auth/session.ts', 'fe_app/src/App.tsx', '.local/sample.json', 'fe-web/src/assets/unreviewed.png', 'fe-web/src/showcase/unreviewed.json', 'fe-web/src/showcase/../auth/session.ts']) {
    const [showcase, phase1] = graphs();
    showcase.modules.push({ id: forbidden });
    assert.throws(() => auditBuildGraphs(showcase, phase1), /Unreviewed showcase/);
  }
  const [showcase, phase1] = graphs();
  phase1.modules.push({ id: 'fe-web/src/showcase/samples.ts' });
  assert.throws(() => auditBuildGraphs(showcase, phase1), /Real entry must not import/);
});

test('only reviewed editor/icon package graph and original source assets are accepted', () => {
  const [showcase, phase1] = graphs();
  for (const id of ['fe-web/src/showcase/teacher/TeacherEditor.tsx', 'fe-web/src/showcase/student/original-student.css', 'fe-web/src/assets/join/background.jpg', 'fe-web/src/showcase/assets/yg-jalnan.woff', 'fe-web/src/showcase/assets/jalnan-LICENSE.txt?url', 'fe-web/node_modules/@tiptap/react/dist/index.js', 'fe-web/node_modules/@tiptap/starter-kit/dist/index.js', 'fe-web/node_modules/prosemirror-model/dist/index.js', 'fe-web/node_modules/lucide-react/dist/esm/lucide-react.js', '\0fe-web/node_modules/react/index.js?commonjs-proxy', '\0commonjsHelpers.js']) showcase.modules.push({ id });
  assert.doesNotThrow(() => auditBuildGraphs(showcase, phase1));
  for (const dependency of ['@tiptap/extension-image', '@tiptap/extension-table', 'axios', 'firebase', 'docx', 'sweetalert2', 'react-native', 'unreviewed-package']) {
    assert.throws(() => auditBuildGraphs({ ...showcase, modules: [...showcase.modules, { id: `fe-web/node_modules/${dependency}/index.js` }] }, phase1), /Unexpected showcase runtime dependency/);
  }
  assert.doesNotThrow(() => auditBuildGraphs({ ...showcase, modules: [...showcase.modules, { id: `\0${REPO_ROOT}/fe-web/node_modules/react/index.js?commonjs-es-import` }] }, phase1));
  assert.throws(() => auditBuildGraphs({ ...showcase, modules: [...showcase.modules, { id: 'fe-web/node_modules/react/../../axios/index.js' }] }, phase1), /Unreviewed showcase/);
});

test('artifact audit rejects private files and development/source-map contents', (t) => {
  const artifact = temporary(t);
  fs.mkdirSync(path.join(artifact, 'assets'));
  fs.writeFileSync(path.join(artifact, 'index.html'), `<meta content="script-src 'self'; connect-src 'none'"><script src="./assets/main.js"></script><link href="./assets/main.css">`);
  fs.writeFileSync(path.join(artifact, 'assets/main.css'), 'body{color:navy}');
  fs.writeFileSync(path.join(artifact, 'assets/main.js'), 'console.log("synthetic bundle")');
  assert.equal(inspectArtifact(artifact).fileCount, 3);
  const asset = REVIEWED_ASSETS.find(({ source }) => source.endsWith('.jpg'));
  fs.copyFileSync(path.join(REPO_ROOT, asset.source), path.join(artifact, 'assets/background-reviewed.jpg'));
  const accepted = inspectArtifact(artifact);
  assert.equal(accepted.fileCount, 4);
  assert.equal(accepted.files.find((file) => file.path.endsWith('.jpg')).reviewedSource, asset.source);
  assert.doesNotThrow(() => assertArtifactManifest(accepted));
  assert.throws(() => assertArtifactManifest({ ...accepted, fileCount: 3 }));
  assert.throws(() => assertArtifactManifest({ ...accepted, manifestDigest: '0'.repeat(64) }));
  fs.writeFileSync(path.join(artifact, 'assets/extra.png'), 'synthetic unreviewed');
  assert.throws(() => inspectArtifact(artifact), /Unreviewed static asset/);
  fs.unlinkSync(path.join(artifact, 'assets/extra.png'));
  fs.writeFileSync(path.join(artifact, '.env'), 'SYNTHETIC_ONLY=yes');
  assert.throws(() => inspectArtifact(artifact), /Unexpected public file/);
  fs.unlinkSync(path.join(artifact, '.env'));
  for (const value of ['//# sourceMappingURL=main.js.map', 'http://127.0.0.1:18082/api/auth', SYNTHETIC_SENTINELS.VITE_API_BASE, 'https://unreviewed.invalid/resource']) {
    fs.writeFileSync(path.join(artifact, 'assets/main.js'), value);
    assert.throws(() => inspectArtifact(artifact));
  }
  fs.writeFileSync(path.join(artifact, 'assets/main.js'), 'console.log("synthetic bundle")');
  for (const value of ['body{background:url(data:image/png;base64,AA==)}', 'body{background:url(./not-in-manifest.png)}', 'body{background:url(/assets/background-reviewed.jpg)}']) {
    fs.writeFileSync(path.join(artifact, 'assets/main.css'), value);
    assert.throws(() => inspectArtifact(artifact), /CSS resource/);
  }
  fs.writeFileSync(path.join(artifact, 'assets/main.css'), 'body{background:url(./background-reviewed.jpg)}');
  assert.doesNotThrow(() => inspectArtifact(artifact));
  for (const script of ["'self' 'unsafe-inline'", "'self' 'unsafe-eval'", "'self' https://unreviewed.invalid"]) {
    fs.writeFileSync(path.join(artifact, 'index.html'), `<meta content="script-src ${script}; connect-src 'none'"><script src="./assets/main.js"></script><link href="./assets/main.css">`);
    assert.throws(() => inspectArtifact(artifact), /Script CSP|Unsafe script/);
  }
});

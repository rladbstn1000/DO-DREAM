import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { RESULTS_DIR, SHOWCASE_OUT, REPO_ROOT, REVIEWED_ASSETS, assertReviewedStaticAsset, isShowcasePublicFile, listFiles, writeEvidence } from './showcase-paths.mjs';

export const SYNTHETIC_SENTINELS = Object.freeze({
  VITE_API_BASE: 'https://sentinel-api.invalid/SHOWCASE_ENV_SENTINEL_53a4',
  VITE_PROVIDER_KEY: 'SHOWCASE_VITE_SENTINEL_937c',
  DODREAM_SYNTHETIC_PRIVATE: 'SHOWCASE_PROCESS_SENTINEL_175f',
});
const PURE_REUSE = new Set([
  'fe-web/src/learning/Presentation.tsx', 'fe-web/src/student/speech.ts', 'fe-web/src/student/student.css',
]);
// Observed dependency closure of the existing React/Router UI plus reviewed
// lucide and Tiptap React + StarterKit entries. This is not a scope wildcard.
const RUNTIME_PACKAGES = new Set([
  'cookie', 'react', 'react-dom', 'react-router', 'react-router-dom', 'scheduler', 'set-cookie-parser',
  '@tiptap/core', '@tiptap/react', '@tiptap/starter-kit', '@tiptap/pm', '@tiptap/extensions',
  ...['blockquote', 'bold', 'code', 'code-block', 'document', 'hard-break', 'heading', 'horizontal-rule', 'italic', 'link', 'list', 'paragraph', 'strike', 'text', 'underline'].map((name) => `@tiptap/extension-${name}`),
  'fast-equals', 'linkifyjs', 'lucide-react', 'orderedmap', 'rope-sequence', 'use-sync-external-store', 'w3c-keyname',
  ...['commands', 'dropcursor', 'gapcursor', 'history', 'keymap', 'model', 'schema-list', 'state', 'transform', 'view'].map((name) => `prosemirror-${name}`),
]);
const assetSources = new Set(REVIEWED_ASSETS.map((asset) => asset.source));
const packageName = (id) => {
  const part = id.split('/node_modules/').at(-1);
  if (part === id) return undefined;
  const segments = part.split('/');
  return segments[0].startsWith('@') ? segments.slice(0, 2).join('/') : segments[0];
};

function assertReviewedImport(id) {
  // CommonJS virtual wrappers retain the underlying reviewed module pathname.
  let normalized = id.replace(/^\0/, '').split('?')[0];
  if (normalized.startsWith(REPO_ROOT + '/')) normalized = normalized.slice(REPO_ROOT.length + 1);
  assert.ok(!normalized.split('/').some((segment) => segment === '.' || segment === '..'), `Unreviewed showcase application import: ${id}`);
  if (id === '\0commonjsHelpers.js' || normalized === 'fe-web/showcase/index.html') return;
  if (normalized.startsWith('fe-web/node_modules/')) {
    assert.ok(RUNTIME_PACKAGES.has(packageName(normalized)), `Unexpected showcase runtime dependency: ${id}`);
    return;
  }
  const ownedSource = /^fe-web\/src\/showcase\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_-]+\.(tsx?|css)$/.test(normalized);
  assert.ok(ownedSource || PURE_REUSE.has(normalized) || assetSources.has(normalized), `Unreviewed showcase application import: ${id}`);
}

export function auditBuildGraphs(showcase, phase1) {
  assert.equal(showcase.mode, 'showcase');
  assert.equal(phase1.mode, 'phase1');
  assert.equal(showcase.configuration.base, './');
  assert.equal(showcase.configuration.outDir, 'fe-web/dist-showcase');
  assert.equal(showcase.configuration.envDir, false);
  assert.equal(showcase.configuration.publicDir, false);
  assert.equal(showcase.configuration.sourcemap, false);
  assert.equal(showcase.configuration.proxyConfigured, false);
  assert.equal(showcase.configuration.production, true);
  assert.deepEqual(showcase.configuration.envKeys, ['BASE_URL', 'DEV', 'MODE', 'PROD']);
  const showcaseIds = showcase.modules.map((module) => module.id);
  const phase1Ids = phase1.modules.map((module) => module.id);
  assert.ok(showcaseIds.includes('fe-web/src/showcase/main.tsx'), 'Dedicated showcase entry must be built');
  assert.ok(phase1Ids.includes('fe-web/src/main.tsx'), 'Real phase1 entry must be built');
  for (const id of showcaseIds) {
    assertReviewedImport(id);
  }
  assert.ok(!phase1Ids.some((id) => id.includes('/src/showcase/')), 'Real entry must not import showcase samples, rules, or state');
  const packagesFrom = (ids) => [...new Set(ids.map(packageName).filter(Boolean))].sort();
  const renderedIds = (showcase.chunks ?? []).flatMap((chunk) => chunk.modules.filter((module) => module.renderedLength > 0).map((module) => module.id));
  return { showcaseModuleCount: showcaseIds.length, phase1ModuleCount: phase1Ids.length, importGraphPackages: packagesFrom(showcaseIds), emittedPackages: packagesFrom(renderedIds), pureReuse: [...PURE_REUSE], reviewedAssetImports: showcaseIds.map((id) => id.split('?')[0]).filter((id) => assetSources.has(id)).sort() };
}

// Dependency strings such as XML namespaces / error documentation are not fetches.
// They are individually classified here; actual automatic requests are checked in Chrome.
const REFERENCE_URLS = [
  /^https?:\/\/www\.w3\.org\/(?:1999\/xhtml|2000\/svg|1998\/Math\/MathML|1999\/xlink|XML\/1998\/namespace|2000\/xmlns\/?)$/,
  /^https:\/\/react\.dev\/errors\/\d*$/,
  /^https:\/\/reactrouter\.com\/en\/main\/routers\/picking-a-router\.$/,
  /^https:\/\/github\.com\/ungap\/url-search-params\.$/,
  // ProseMirror schema validation error text; this string does not load a URL.
  /^https:\/\/prosemirror\.net\/docs\/guide\/#generatable$/,
  // React Router's createBrowserURL fallback base; the active HashRouter passes
  // window.location.origin. This exact no-port/no-path constant does not fetch.
  /^http:\/\/localhost$/,
];

export function inspectArtifact(directory = SHOWCASE_OUT) {
  const filenames = listFiles(directory);
  const publicPaths = new Set(filenames.map((filename) => path.relative(directory, filename).replaceAll(path.sep, '/')));
  const files = filenames.map((filename) => {
    const name = path.relative(directory, filename).replaceAll(path.sep, '/');
    assert.ok(isShowcasePublicFile(name), `Unexpected public file: ${name}`);
    const bytes = fs.readFileSync(filename);
    assert.ok(bytes.length <= 5_000_000, `Unexpectedly large static asset: ${name}`);
    const reviewedSource = assertReviewedStaticAsset(name, bytes);
    let referenceUrls = [];
    if (/\.(html|js|css|svg)$/.test(name)) {
      const text = bytes.toString('utf8');
      for (const sentinel of Object.values(SYNTHETIC_SENTINELS)) assert.ok(!text.includes(sentinel), 'Synthetic environment sentinel leaked');
      assert.ok(!/SHOWCASE_(?:ENV|VITE|PROCESS)_SENTINEL/.test(text), 'Synthetic environment sentinel leaked');
      assert.ok(!/sourceMappingURL|@vite\/client|\/src\/main\.tsx|localhost:\d+|127\.0\.0\.1|\.local\//.test(text), `Development/private path in ${name}`);
      assert.ok(!/VITE_API_BASE|VITE_RAG_BASE|accessToken|deviceSecret|\/api\/auth|\/api\/session|\/ai\/rag/.test(text), `Real service setting in ${name}`);
      assert.ok(!/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|\bsk-[A-Za-z0-9_-]{24,}|\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}/.test(text), `Credential-shaped value in ${name}`);
      if (name.endsWith('.html')) {
        const decoded = text.replaceAll('&#39;', "'");
        assert.ok(decoded.includes("connect-src 'none'"));
        assert.ok(/(?:^|[;"\s])script-src 'self'\s*(?:;|")/.test(decoded), 'Script CSP must remain self only');
        assert.ok(!/script-src[^;"\n]*(?:unsafe-inline|unsafe-eval|https?:|data:)/.test(decoded), 'Unsafe script CSP');
        assert.ok(!/\son\w+=|<script(?![^>]*\bsrc=)[^>]*>/i.test(text), 'Unexpected inline HTML script');
        const links = [...text.matchAll(/(?:src|href)="([^"]+)"/g)].map((match) => match[1]);
        assert.ok(links.every((link) => link.startsWith('./assets/') && publicPaths.has(link.slice(2))), 'HTML assets must be current relative local files');
      }
      if (name.endsWith('.css')) {
        assert.ok(!/url\(\s*["']?(?:https?:|\/\/|data:|blob:)|@import/i.test(text), 'External or inline CSS resource');
        for (const match of text.matchAll(/url\(\s*["']?([^\s"')]+)["']?\s*\)/g)) {
          assert.ok(match[1].startsWith('./') && publicPaths.has(path.posix.join(path.posix.dirname(name), match[1])), 'CSS resource must be a current reviewed artifact file');
        }
      }
      referenceUrls = [...new Set(text.match(/https?:\/\/[^\s"'`<>\\)]+/g) ?? [])].sort();
      for (const url of referenceUrls) assert.ok(REFERENCE_URLS.some((allowed) => allowed.test(url)), `Unreviewed URL in ${name}: ${url}`);
    }
    return { path: name, bytes: bytes.length, sha256: crypto.createHash('sha256').update(bytes).digest('hex'), referenceUrls, ...(reviewedSource ? { reviewedSource } : {}) };
  });
  assert.ok(files.some((file) => file.path === 'index.html'), 'Missing output root index.html');
  assert.ok(files.some((file) => file.path.endsWith('.js')), 'Missing application bundle');
  assert.ok(files.some((file) => file.path.endsWith('.css')), 'Missing application stylesheet');
  const manifestDigest = artifactManifestDigest(files);
  const artifact = { fileCount: files.length, totalBytes: files.reduce((sum, file) => sum + file.bytes, 0), manifestDigest, files };
  assertArtifactManifest(artifact);
  return artifact;
}

export const artifactManifestDigest = (files) => crypto.createHash('sha256').update(files.map((file) => `${file.path}\0${file.bytes}\0${file.sha256}\n`).join('')).digest('hex');

export function assertArtifactManifest(artifact) {
  assert.ok(Array.isArray(artifact?.files) && artifact.files.length >= 3 && artifact.files.length <= 100);
  const names = artifact.files.map((file) => file.path);
  assert.deepEqual(names, [...new Set(names)].sort(), 'Manifest paths must be unique and sorted');
  for (const file of artifact.files) {
    assert.ok(isShowcasePublicFile(file.path), 'Unexpected public manifest path');
    assert.ok(Number.isSafeInteger(file.bytes) && file.bytes > 0 && file.bytes <= 5_000_000);
    assert.match(file.sha256, /^[0-9a-f]{64}$/);
    if (/\.(svg|png|jpg|jpeg|webp|woff|txt)$/.test(file.path)) {
      assert.ok(REVIEWED_ASSETS.some((asset) => path.extname(asset.source) === path.extname(file.path) && asset.bytes === file.bytes && asset.sha256 === file.sha256), 'Unreviewed static asset in manifest');
    }
  }
  assert.ok(names.includes('index.html') && names.some((name) => name.endsWith('.js')) && names.some((name) => name.endsWith('.css')));
  assert.equal(artifact.fileCount, artifact.files.length);
  assert.equal(artifact.totalBytes, artifact.files.reduce((sum, file) => sum + file.bytes, 0));
  assert.ok(artifact.totalBytes <= 20_000_000);
  assert.equal(artifact.manifestDigest, artifactManifestDigest(artifact.files), 'Manifest digest does not match current file records');
  return artifact;
}

export function auditShowcase() {
  const showcase = JSON.parse(fs.readFileSync(path.join(RESULTS_DIR, 'showcase-modules.json'), 'utf8'));
  const phase1 = JSON.parse(fs.readFileSync(path.join(RESULTS_DIR, 'phase1-modules.json'), 'utf8'));
  const graph = auditBuildGraphs(showcase, phase1);
  const lock = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, 'fe-web/package-lock.json'), 'utf8'));
  const runtimeVersions = Object.fromEntries(graph.emittedPackages.map((name) => [name, lock.packages[`node_modules/${name}`].version]));
  const result = { status: 'PASS', ...graph, runtimeVersions, ...inspectArtifact() };
  writeEvidence('artifact-review', result);
  return result;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = auditShowcase();
  console.log(`Showcase artifact PASS: ${result.fileCount} files, ${result.totalBytes} bytes, digest ${result.manifestDigest}`);
}

import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { RESULTS_DIR, SHOWCASE_OUT, listFiles, writeEvidence } from './showcase-paths.mjs';

export const SYNTHETIC_SENTINELS = Object.freeze({
  VITE_API_BASE: 'https://sentinel-api.invalid/SHOWCASE_ENV_SENTINEL_53a4',
  VITE_PROVIDER_KEY: 'SHOWCASE_VITE_SENTINEL_937c',
  DODREAM_SYNTHETIC_PRIVATE: 'SHOWCASE_PROCESS_SENTINEL_175f',
});
const PURE_REUSE = new Set([
  'fe-web/src/learning/Presentation.tsx', 'fe-web/src/student/speech.ts', 'fe-web/src/student/student.css',
]);

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
    const source = id.match(/fe-web\/src\/[^?]+/)?.[0];
    assert.ok(!source || source.startsWith('fe-web/src/showcase/') || PURE_REUSE.has(source), `Unreviewed showcase application import: ${source}`);
    assert.ok(!/node_modules\/(?:@tiptap|axios|firebase|aws-sdk|@aws-sdk|docx|lottie-web)\//.test(id), `Unexpected showcase runtime dependency: ${id}`);
  }
  assert.ok(!phase1Ids.some((id) => id.includes('/src/showcase/')), 'Real entry must not import showcase samples, rules, or state');
  const packagesFrom = (ids) => [...new Set(ids.flatMap((id) => {
    const part = id.split('/node_modules/').at(-1);
    if (part === id) return [];
    const segments = part.split('/');
    return [segments[0].startsWith('@') ? segments.slice(0, 2).join('/') : segments[0]];
  }))].sort();
  const renderedIds = (showcase.chunks ?? []).flatMap((chunk) => chunk.modules.filter((module) => module.renderedLength > 0).map((module) => module.id));
  return { showcaseModuleCount: showcaseIds.length, phase1ModuleCount: phase1Ids.length, importGraphPackages: packagesFrom(showcaseIds), emittedPackages: packagesFrom(renderedIds), pureReuse: [...PURE_REUSE] };
}

// Dependency strings such as XML namespaces / error documentation are not fetches.
// They are individually classified here; actual automatic requests are checked in Chrome.
const REFERENCE_URLS = [
  /^https?:\/\/www\.w3\.org\/(?:1999\/xhtml|2000\/svg|1998\/Math\/MathML|1999\/xlink|XML\/1998\/namespace|2000\/xmlns\/?)$/,
  /^https:\/\/react\.dev\/errors\/\d*$/,
  /^https:\/\/reactrouter\.com\/en\/main\/routers\/picking-a-router\.$/,
  /^https:\/\/github\.com\/ungap\/url-search-params\.$/,
  // React Router's createBrowserURL fallback base; the active HashRouter passes
  // window.location.origin. This exact no-port/no-path constant does not fetch.
  /^http:\/\/localhost$/,
];

export function inspectArtifact(directory = SHOWCASE_OUT) {
  const files = listFiles(directory).map((filename) => {
    const name = path.relative(directory, filename).replaceAll(path.sep, '/');
    assert.ok(name === 'index.html' || /^assets\/[A-Za-z0-9_-]+\.(js|css|svg|png|webp)$/.test(name), `Unexpected public file: ${name}`);
    const bytes = fs.readFileSync(filename);
    assert.ok(bytes.length <= 5_000_000, `Unexpectedly large static asset: ${name}`);
    let referenceUrls = [];
    if (/\.(html|js|css|svg)$/.test(name)) {
      const text = bytes.toString('utf8');
      for (const sentinel of Object.values(SYNTHETIC_SENTINELS)) assert.ok(!text.includes(sentinel), 'Synthetic environment sentinel leaked');
      assert.ok(!/SHOWCASE_(?:ENV|VITE|PROCESS)_SENTINEL/.test(text), 'Synthetic environment sentinel leaked');
      assert.ok(!/sourceMappingURL|@vite\/client|\/src\/main\.tsx|localhost:\d+|127\.0\.0\.1|\.local\//.test(text), `Development/private path in ${name}`);
      assert.ok(!/VITE_API_BASE|VITE_RAG_BASE|accessToken|deviceSecret|\/api\/auth|\/api\/session|\/ai\/rag/.test(text), `Real service setting in ${name}`);
      assert.ok(!/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|\bsk-[A-Za-z0-9_-]{24,}|\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}/.test(text), `Credential-shaped value in ${name}`);
      if (name.endsWith('.html')) {
        assert.ok(text.includes('connect-src &#39;none&#39;') || text.includes("connect-src 'none'"));
        assert.ok(!/\son\w+=|<script(?![^>]*\bsrc=)[^>]*>/i.test(text), 'Unexpected inline HTML script');
        const links = [...text.matchAll(/(?:src|href)="([^"]+)"/g)].map((match) => match[1]);
        assert.ok(links.every((link) => link.startsWith('./assets/')), 'HTML assets must be relative local files');
      }
      if (name.endsWith('.css')) assert.ok(!/url\(\s*["']?(?:https?:|\/\/)|@import/i.test(text), 'External CSS resource');
      referenceUrls = [...new Set(text.match(/https?:\/\/[^\s"'`<>\\)]+/g) ?? [])].sort();
      for (const url of referenceUrls) assert.ok(REFERENCE_URLS.some((allowed) => allowed.test(url)), `Unreviewed URL in ${name}: ${url}`);
    }
    return { path: name, bytes: bytes.length, sha256: crypto.createHash('sha256').update(bytes).digest('hex'), referenceUrls };
  });
  assert.ok(files.some((file) => file.path === 'index.html'), 'Missing output root index.html');
  assert.ok(files.some((file) => file.path.endsWith('.js')), 'Missing application bundle');
  assert.ok(files.some((file) => file.path.endsWith('.css')), 'Missing application stylesheet');
  const manifestDigest = crypto.createHash('sha256').update(files.map((file) => `${file.path}\0${file.bytes}\0${file.sha256}\n`).join('')).digest('hex');
  return { fileCount: files.length, totalBytes: files.reduce((sum, file) => sum + file.bytes, 0), manifestDigest, files };
}

export function auditShowcase() {
  const showcase = JSON.parse(fs.readFileSync(path.join(RESULTS_DIR, 'showcase-modules.json'), 'utf8'));
  const phase1 = JSON.parse(fs.readFileSync(path.join(RESULTS_DIR, 'phase1-modules.json'), 'utf8'));
  const result = { status: 'PASS', ...auditBuildGraphs(showcase, phase1), ...inspectArtifact() };
  writeEvidence('artifact-review', result);
  return result;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = auditShowcase();
  console.log(`Showcase artifact PASS: ${result.fileCount} files, ${result.totalBytes} bytes, digest ${result.manifestDigest}`);
}

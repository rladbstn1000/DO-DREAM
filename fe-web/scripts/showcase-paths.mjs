import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const REPO_ROOT = path.dirname(WEB_ROOT);
export const SHOWCASE_ROOT = path.join(WEB_ROOT, 'showcase');
export const SHOWCASE_OUT = path.join(WEB_ROOT, 'dist-showcase');
export function evidenceDirectory(selection = process.env.DODREAM_SHOWCASE_EVIDENCE) {
  if (selection !== undefined && !['static-showcase', 'original-ui', 'original-ui-polish', 'original-ui-release'].includes(selection)) throw new Error('Unreviewed showcase evidence directory');
  return path.join(REPO_ROOT, '.local', selection ?? 'static-showcase', 'results');
}
export const RESULTS_DIR = evidenceDirectory();

export const SHOWCASE_MIME = Object.freeze({
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
  '.woff': 'font/woff', '.txt': 'text/plain; charset=utf-8',
});
export const isShowcasePublicFile = (name) => typeof name === 'string' && (name === 'index.html' || /^assets\/[A-Za-z0-9_-]+\.(js|css|svg|png|jpg|jpeg|webp|woff|txt)$/.test(name));

// Reviewed original UI images, unchanged licensed font and its full notice. Paths
// identify provenance; emitted asset names may change with Vite, bytes may not.
export const REVIEWED_ASSETS = Object.freeze([
  ['fe-web/src/assets/join/background.jpg', 893557, '80e3a354750edb7ef8a2ad2f4f8ded72d8e6f15234c370605fbd25616d9ad00a'],
  ['fe-web/src/assets/join/signin.png', 1248501, '2ee696167b7bf4b182bb17d2ea7a3d2106d106ee354eafceeeb56f6ce0481702'],
  ['fe-web/src/assets/join/signup.png', 179709, '8d2c0e9b6350787d7ef1ede9d04c551e4372fa10b7799a8bef9ccab5798c7156'],
  ['fe-web/src/assets/classList/teacher.png', 1108881, '2ffe378092d1ad39a36ae43fe653ac628231f8367e90eb3e2e9b2f1f38d0b850'],
  ['fe-web/src/assets/classList/memo.png', 417870, 'f61fd42eb44485b6e043915d0d080194d9575656594006b9040e6733f3ac3d52'],
  ['fe-web/src/assets/classList/school.png', 1008593, '323bc8040f13ffac74a74061cb3617b3a17c1d0389bb770822858a0bdb7920ec'],
  ['fe-web/src/assets/classroom/male.png', 222433, '0fea7ba29352dcb172bb851fc7236a3b3064fd43ebe087912df112b24ecf2f56'],
  ['fe-web/src/assets/classroom/female.png', 274444, '9010cc74df152fccb43ce805f01586cd73d3c22a1fff7f90812540788569df49'],
  ['fe-web/src/showcase/assets/yg-jalnan.woff', 537996, '606c8ff7146886d42bacecdf1df92c4088ab18e2b3f4de77764b02e136510140'],
  ['fe-web/src/showcase/assets/jalnan-LICENSE.txt', 2014, 'a503432ebbb2aef98af241a61ce93f876176aafd5af81cd136ce099745467d1e'],
].map(([source, bytes, sha256]) => Object.freeze({ source, bytes, sha256 })));

export function assertReviewedStaticAsset(name, bytes) {
  if (!/\.(svg|png|jpg|jpeg|webp|woff|txt)$/.test(name)) return undefined;
  const digest = crypto.createHash('sha256').update(bytes).digest('hex');
  const reviewed = REVIEWED_ASSETS.find((asset) => path.extname(asset.source) === path.extname(name) && asset.bytes === bytes.length && asset.sha256 === digest);
  if (!reviewed) throw new Error(`Unreviewed static asset bytes: ${name}`);
  return reviewed.source;
}

// Never follow links when a build may empty an output directory or a server reads it.
export function assertNoSymlinkChain(target) {
  const absolute = path.resolve(target);
  const parsed = path.parse(absolute);
  let current = parsed.root;
  for (const part of absolute.slice(parsed.root.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, part);
    if (fs.lstatSync(current, { throwIfNoEntry: false })?.isSymbolicLink()) throw new Error('Symbolic links are not allowed in showcase paths');
  }
  return absolute;
}

export function listFiles(root) {
  assertNoSymlinkChain(root);
  if (!fs.existsSync(root)) return [];
  const result = [];
  const walk = (directory) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const filename = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) throw new Error('Symbolic links are not allowed in showcase output');
      if (entry.isDirectory()) walk(filename);
      else if (entry.isFile()) result.push(filename);
      else throw new Error('Only regular files are allowed in showcase output');
    }
  };
  walk(root);
  return result.sort();
}

export function assertSafeOutput(projectRoot, candidate) {
  const project = assertNoSymlinkChain(projectRoot);
  if (!fs.existsSync(project) || !fs.statSync(project).isDirectory()) throw new Error('Missing showcase project directory');
  const expected = path.join(project, 'dist-showcase');
  if (!path.isAbsolute(candidate) || path.resolve(candidate) !== expected) {
    throw new Error('Showcase output must be the fixed dist-showcase directory');
  }
  assertNoSymlinkChain(expected);
  if (fs.existsSync(expected)) {
    if (!fs.statSync(expected).isDirectory()) throw new Error('Showcase output must be a directory');
    listFiles(expected);
  }
  return expected;
}

export function assertShowcaseBundle(bundle) {
  for (const [name, entry] of Object.entries(bundle)) {
    if (name !== entry.fileName || !isShowcasePublicFile(name)) {
      throw new Error('Showcase emitted filename is outside the reviewed static file set');
    }
    if (/\.(svg|png|jpg|jpeg|webp|woff|txt)$/.test(name)) assertReviewedStaticAsset(name, Buffer.from(entry.source));
  }
}

export function ensureResultsDirectory() {
  assertNoSymlinkChain(RESULTS_DIR);
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  return RESULTS_DIR;
}

export function writeEvidence(name, value) {
  if (!/^[a-z0-9-]+$/.test(name)) throw new Error('Invalid evidence name');
  const directory = ensureResultsDirectory();
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const text = `${JSON.stringify(value, null, 2)}\n`;
  assertNoSymlinkChain(path.join(directory, `${name}.json`));
  const timestamped = path.join(directory, `${name}-${stamp}.json`);
  const latest = path.join(directory, `${name}.json`);
  fs.writeFileSync(timestamped, text, { flag: 'wx' });
  fs.writeFileSync(latest, text);
  return { timestamped, latest };
}

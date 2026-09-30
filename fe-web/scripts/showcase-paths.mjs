import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const REPO_ROOT = path.dirname(WEB_ROOT);
export const SHOWCASE_ROOT = path.join(WEB_ROOT, 'showcase');
export const SHOWCASE_OUT = path.join(WEB_ROOT, 'dist-showcase');
export const RESULTS_DIR = path.join(REPO_ROOT, '.local', 'static-showcase', 'results');

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
    if (name !== entry.fileName || (name !== 'index.html' && !/^assets\/[A-Za-z0-9_-]+\.(js|css|svg|png|webp)$/.test(name))) {
      throw new Error('Showcase emitted filename is outside the reviewed static file set');
    }
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

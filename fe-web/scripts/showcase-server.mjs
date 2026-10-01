import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { fileURLToPath } from 'node:url';
import { WEB_ROOT, SHOWCASE_OUT, SHOWCASE_MIME, assertSafeOutput, assertReviewedStaticAsset, isShowcasePublicFile, listFiles } from './showcase-paths.mjs';

// A small local preview server, not a production server. There is no route fallback,
// proxy, arbitrary root option, directory listing or access to source/evidence files.
export async function startShowcaseServer({ port = 0 } = {}) {
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Invalid preview port');
  assertSafeOutput(WEB_ROOT, SHOWCASE_OUT);
  const files = new Map(listFiles(SHOWCASE_OUT).map((filename) => {
    const name = path.relative(SHOWCASE_OUT, filename).replaceAll(path.sep, '/');
    if (!isShowcasePublicFile(name)) throw new Error('Unexpected public artifact');
    // Serve the accepted regular-file bytes, so later path replacement cannot expose a link target.
    const bytes = fs.readFileSync(filename);
    assertReviewedStaticAsset(name, bytes);
    return [name, { bytes, mime: SHOWCASE_MIME[path.extname(name)] }];
  }));
  if (!files.has('index.html')) throw new Error('Build showcase before starting preview');
  const requests = [];
  const server = http.createServer((request, response) => {
    let pathname;
    try {
      pathname = decodeURIComponent((request.url ?? '/').split('?')[0]);
      if (pathname.includes('\\') || pathname.includes('\0') || pathname.split('/').some((part) => part === '.' || part === '..')) throw new Error('Invalid path');
    } catch {
      response.writeHead(400).end();
      requests.push({ method: request.method, path: '[invalid]', status: 400 });
      return;
    }
    const reply = (status, headers = {}, bytes) => {
      requests.push({ method: request.method, path: pathname, status });
      response.writeHead(status, { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', ...headers });
      response.end(request.method === 'HEAD' ? undefined : bytes);
    };
    if (request.method !== 'GET' && request.method !== 'HEAD') return reply(405, { Allow: 'GET, HEAD' });
    if (pathname === '/DO-DREAM') return reply(308, { Location: '/DO-DREAM/' });
    const relative = pathname.startsWith('/DO-DREAM/') ? pathname.slice('/DO-DREAM/'.length) : pathname.slice(1);
    const file = files.get(relative === '' ? 'index.html' : relative);
    if (!file) return reply(404);
    reply(200, { 'Content-Type': file.mime, 'Content-Length': file.bytes.length }, file.bytes);
  });
  server.requestTimeout = 10_000;
  server.headersTimeout = 10_000;
  server.keepAliveTimeout = 1_000;
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => { server.off('error', reject); resolve(); });
  });
  const address = server.address();
  const origin = `http://127.0.0.1:${address.port}`;
  return { origin, url: `${origin}/`, requests, close: () => new Promise((resolve, reject) => {
    server.close((error) => error ? reject(error) : resolve());
    server.closeIdleConnections();
  }) };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (args.length && (args.length !== 2 || args[0] !== '--port' || !/^\d+$/.test(args[1]))) throw new Error('Only --port NUMBER is accepted');
  const server = await startShowcaseServer({ port: args.length ? Number(args[1]) : 0 });
  console.log(`DO:DREAM static preview: ${server.url}`);
  console.log(`Subpath preview: ${server.origin}/DO-DREAM/`);
  const stop = async () => { await server.close(); process.exit(0); };
  process.once('SIGINT', stop);
  process.once('SIGTERM', stop);
}

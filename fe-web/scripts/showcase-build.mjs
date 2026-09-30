import path from 'node:path';
import { WEB_ROOT, SHOWCASE_OUT, assertSafeOutput } from './showcase-paths.mjs';

if (process.argv.length !== 2) throw new Error('build:showcase accepts no output or configuration overrides');
assertSafeOutput(WEB_ROOT, SHOWCASE_OUT);
// The public build cannot inherit development-mode transforms from a caller.
process.env.NODE_ENV = 'production';
const { build } = await import('vite');
await build({ configFile: path.join(WEB_ROOT, 'vite.showcase.config.ts'), mode: 'showcase' });

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { assertSafeOutput, assertShowcaseBundle } from './scripts/showcase-paths.mjs';
import { recordBuildGraph } from './scripts/showcase-graph.mjs';

const webRoot = path.dirname(fileURLToPath(import.meta.url));
const showcaseRoot = path.join(webRoot, 'showcase');
const output = path.join(webRoot, 'dist-showcase');

export default defineConfig(({ command, mode }) => {
  if (command !== 'build' || mode !== 'showcase') throw new Error('Use the explicit build:showcase command');
  assertSafeOutput(webRoot, output);
  return {
    root: showcaseRoot,
    base: './',
    envDir: false,
    envPrefix: [],
    publicDir: false,
    // Inline settings also prevent ambient Babel/PostCSS config discovery. The
    // owned CSS does not need previous source maps or third-party CSS plugins.
    css: { postcss: { map: false, plugins: [] }, devSourcemap: false },
    plugins: [react({ babel: { babelrc: false, configFile: false } }), {
      name: 'dodream-fixed-showcase-output',
      configResolved(config) {
        // Runs before Vite prepares/empties outputs, including direct CLI overrides.
        assertSafeOutput(webRoot, path.resolve(config.root, config.build.outDir));
        if (!config.isProduction || config.build.ssr || config.root !== showcaseRoot || config.base !== './' || config.envDir !== false || config.publicDir ||
            config.build.sourcemap || config.server.proxy || Object.keys(config.define ?? {}).length ||
            Object.keys(config.env).some((key) => !['BASE_URL', 'MODE', 'DEV', 'PROD', 'SSR'].includes(key)) ||
            config.build.rollupOptions.output || config.build.rollupOptions.input !== path.join(showcaseRoot, 'index.html')) {
          throw new Error('Showcase configuration boundary cannot be overridden');
        }
      },
      generateBundle: {
        order: 'post',
        handler(_options, bundle) {
          // Check emitted names before Rollup writes, not just the output root.
          assertShowcaseBundle(bundle);
        },
      },
    }, recordBuildGraph('showcase')],
    build: {
      outDir: output,
      emptyOutDir: true,
      sourcemap: false,
      manifest: false,
      modulePreload: { polyfill: false },
      rollupOptions: { input: path.join(showcaseRoot, 'index.html') },
    },
  };
});

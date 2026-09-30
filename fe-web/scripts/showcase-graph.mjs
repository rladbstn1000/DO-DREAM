import path from 'node:path';
import { REPO_ROOT, ensureResultsDirectory, writeEvidence } from './showcase-paths.mjs';

const normal = (id) => id.replaceAll('\\', '/');
const relative = (id) => normal(id.startsWith(REPO_ROOT + path.sep) ? path.relative(REPO_ROOT, id) : id);

// This audit stays outside dist. The public app does not import or fetch it.
export function recordBuildGraph(mode) {
  let resolved;
  return {
    name: `dodream-${mode}-module-evidence`,
    apply: 'build',
    configResolved(config) { resolved = config; },
    writeBundle(_options, bundle) {
      ensureResultsDirectory();
      const modules = [...this.getModuleIds()].map((id) => {
        const info = this.getModuleInfo(id);
        return { id: relative(id), importedIds: (info?.importedIds ?? []).map(relative).sort() };
      }).sort((a, b) => a.id.localeCompare(b.id));
      const chunks = Object.values(bundle).filter((entry) => entry.type === 'chunk').map((entry) => ({
        file: entry.fileName,
        entry: entry.isEntry,
        modules: Object.entries(entry.modules).map(([id, info]) => ({ id: relative(id), renderedLength: info.renderedLength })),
      }));
      const report = {
        mode,
        createdAt: new Date().toISOString(),
        configuration: {
          root: relative(resolved.root), outDir: relative(path.resolve(resolved.root, resolved.build.outDir)),
          base: resolved.base, envKeys: Object.keys(resolved.env).sort(),
          envDir: resolved.envDir === false ? false : relative(resolved.envDir),
          publicDir: resolved.publicDir === false || resolved.publicDir === '' ? false : relative(resolved.publicDir),
          sourcemap: resolved.build.sourcemap, proxyConfigured: !!resolved.server.proxy,
          production: resolved.isProduction,
        },
        modules, chunks,
      };
      writeEvidence(`${mode}-modules`, report);
    },
  };
}

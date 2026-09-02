import * as esbuild from 'esbuild';
import { createHash } from 'node:crypto';
import { copyFileSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { join, posix, relative, sep } from 'node:path';

// Copy Hunspell dictionary files from node_modules/dictionary-en into the
// static assets directory so they can be fetched by linter-spell.ts at runtime.
// This runs once at build time and commits the result to git (~555KB total).
function copyHunspellDicts() {
  const srcDir = 'node_modules/dictionary-en';
  const destDir = 'ui/default/static/hunspell-en';
  mkdirSync(destDir, { recursive: true });
  for (const file of ['index.aff', 'index.dic']) {
    copyFileSync(join(srcDir, file), join(destDir, file));
  }
}
copyHunspellDicts();

const entryPoints = {
  'nav':              'src/ts/nav/index.ts',
  'index-app':        'src/ts/apps/index-app.ts',
  'stats-app':        'src/ts/apps/stats-app.ts',
  'tools-app':        'src/ts/apps/tools-app.ts',
  'settings-app':     'src/ts/apps/settings-app.ts',
  'story-app':        'src/ts/apps/story-app.ts',
  'inspect-app':      'src/ts/apps/inspect-app.ts',
  'extensions-app':   'src/ts/apps/extensions-app.ts',
  'share-app':        'src/ts/apps/share-app.ts',
  'a11y':             'src/ts/a11y/index.ts',
  'power-vim-edit':   'src/ts/keyboard/vim-edit-standalone.ts',
  'favorites-app':    'src/ts/apps/favorites-app.ts',
  'lan-share-app':    'src/ts/apps/lan-share-app.ts',
  'bridge-app':       'src/ts/apps/bridge-app.ts',
  'report-app':       'src/ts/apps/report-app.ts',
  'agent-journal-app':'src/ts/apps/agent-journal-app.ts',
  'scheduler-app':    'src/ts/apps/scheduler-app.ts',
  'llm-router-app':   'src/ts/apps/llm-router-app.ts',
  'mesh-inference-app': 'src/ts/apps/mesh-inference-app.ts',
  'lan-cowork-app':     'src/ts/apps/lan-cowork-app.ts',
  'scan-jobs-app':      'src/ts/apps/scan-jobs-app.ts',
  'sweep-view-app':     'src/ts/apps/sweep-view-app.ts',
  'diagnostics-app':    'src/ts/apps/diagnostics-app.ts',
  'agent-memory-app':   'src/ts/apps/agent-memory-app.ts',
  'md-viewer-vendor': 'src/ts/vendor/md-viewer-vendor.ts',
  'extension-api':    'src/ts/extension-api/index.ts',
  'ext-bridges-app':  'src/ts/apps/ext-bridges-app.ts',
  'crypto-tools-app': 'src/ts/apps/crypto-tools-app.ts',
};

const isWatch = process.argv.includes('--watch');
const isProd = process.env.NODE_ENV === 'production';

// Wipe hash-named chunk outputs before non-watch builds so stale chunks don't
// accumulate and pollute git status. Entry-point .js files have deterministic
// names and are overwritten in place, so leave those alone.
if (!isWatch) {
  for (const dir of ['ui/default/static/dist/chunks', 'ui/default/static/dist/workers']) {
    try { rmSync(dir, { recursive: true, force: true }); } catch { /* ignore */ }
  }
}

// Plugin: refresh dist/.build-info.json after every successful build so the
// startup freshness check in scripts/check_dist_freshness.py stays accurate
// during `pnpm run watch` cycles.
const buildInfoPlugin = {
  name: 'build-info',
  setup(build) {
    build.onEnd((result) => {
      if (result.errors.length === 0) writeBuildInfo();
    });
  },
};

// Main ESM build (splitting enabled)
const ctx = await esbuild.context({
  entryPoints,
  bundle: true,
  format: 'esm',
  splitting: true,
  outdir: 'ui/default/static/dist',
  chunkNames: 'chunks/[name]-[hash]',
  sourcemap: true,
  minify: isProd,
  target: 'es2020',
  plugins: [buildInfoPlugin],
});

// Worker build (IIFE, no splitting — Workers are incompatible with ESM splitting)
const workerCtx = await esbuild.context({
  entryPoints: { 'search-worker': 'src/ts/workers/search-worker.ts' },
  bundle: true,
  format: 'iife',
  outdir: 'ui/default/static/dist/workers',
  sourcemap: true,
  minify: isProd,
  target: 'es2020',
  plugins: [buildInfoPlugin],
});

// Linter IIFE — non-module script for bridge/simulator pages
const linterCtx = await esbuild.context({
  entryPoints: ['src/ts/apps/linter-global.ts'],
  bundle: true,
  format: 'iife',
  outfile: 'ui/default/static/dist/linter.js',
  sourcemap: true,
  minify: isProd,
  target: 'es2020',
  plugins: [buildInfoPlugin],
});

// Gateway page build (ESM, stable filename referenced directly by template)
const gatewayPageCtx = await esbuild.context({
  entryPoints: ['src/ts/gateway-page/index.ts'],
  bundle: true,
  format: 'esm',
  outfile: 'ui/default/static/js/gateway-page.js',
  sourcemap: true,
  minify: isProd,
  target: 'es2020',
  plugins: [buildInfoPlugin],
});

// Stable sha256 over every src/ts/**/*.ts file (path + null + content + null).
// Mirrored by scripts/check_dist_freshness.py — keep the two in sync.
function computeSrcHash(srcDir) {
  // Sort key is the posix-style relative path so ordering matches the
  // Python side in scripts/check_dist_freshness.py regardless of OS path sep.
  const entries = [];
  function walk(dir) {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      const st = statSync(full);
      if (st.isDirectory()) walk(full);
      else if (st.isFile() && name.endsWith('.ts')) {
        const rel = relative(srcDir, full).split(sep).join(posix.sep);
        entries.push({ rel, full });
      }
    }
  }
  walk(srcDir);
  entries.sort((a, b) => (a.rel < b.rel ? -1 : a.rel > b.rel ? 1 : 0));
  const h = createHash('sha256');
  for (const { rel, full } of entries) {
    h.update(rel);
    h.update('\0');
    h.update(readFileSync(full));
    h.update('\0');
  }
  return h.digest('hex');
}

function writeBuildInfo() {
  const info = {
    src_hash: computeSrcHash('src/ts'),
    built_at: Date.now(),
  };
  writeFileSync('ui/default/static/dist/.build-info.json', JSON.stringify(info, null, 2) + '\n');
}

if (isWatch) {
  await ctx.watch();
  await workerCtx.watch();
  await linterCtx.watch();
  await gatewayPageCtx.watch();
  console.log('Watching for changes...');
} else {
  await ctx.rebuild();
  await workerCtx.rebuild();
  await linterCtx.rebuild();
  await gatewayPageCtx.rebuild();
  await ctx.dispose();
  await workerCtx.dispose();
  await linterCtx.dispose();
  await gatewayPageCtx.dispose();
}

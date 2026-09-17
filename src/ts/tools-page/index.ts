/**
 * tools-page/index.ts -- Entry point for the tools page TS bundle.
 *
 * Split into:
 *   - window-bridges.ts  : namespaced browser API registration
 *   - index.ts (this)    : page initialization logic
 */

// Side-effect imports: register toolsPageApi on window
import './window-bridges';

// --- initialization imports ---
import { initStartupMode } from './startup-mode';
import { initDupeCheckSync } from './duplicates/ui';
import { loadCacheInfo } from './file-search/core';
import { loadDbInfo, loadTagCount, loadInferenceInfo, loadScanErrors, checkDebugMode } from './db-info';
import { loadScanRoots } from './roots/list';
import { loadExtensions } from './extensions-summary';
import { loadUpdateStatus } from './system-update';
import { initHashBackfill } from './scan/hash-backfill';
import { initSvgRasterize } from './scan/svg-rasterize';
import { initOcrAdvanced } from './ocr-advanced';
import './webhooks';
import './lora-projects';
import './prompt-convert';
import './mcp-connections';
import './chatlog-search';
import { sseSubscribe } from '../sse';
import { createPagePerfTracker } from '../shared/page-perf';
import { captureThrownError } from '../shared/error-reporter';
import { initAccordion, registerLazy } from './accordion';
import { initSidebar, registerCategoryLoader } from './sidebar';

// ===========================
// Initialization
// ===========================

initStartupMode();
initDupeCheckSync();
initHashBackfill(sseSubscribe);
initSvgRasterize();
initOcrAdvanced();
loadCacheInfo();
const _perf = createPagePerfTracker('tools');
_perf.markOnce('module_ready');

type Loader = () => void | Promise<void>;

async function _loadAiAnalysis(): Promise<void> {
  const mod = await import('./ai-analysis/core');
  await mod.loadAiConfig();
  await mod.loadTrendHistory();
}

async function _loadWdTagger(): Promise<void> {
  const mod = await import('./wd-tagger/core');
  await mod.wtLoadConfig();
}

async function _loadVideoAnalysis(): Promise<void> {
  const mod = await import('./video-analysis/core');
  await mod.vaLoadConfig();
}

const _loadedTasks = new Set<string>();

function _runOnce(key: string, loader: Loader): void {
  if (_loadedTasks.has(key)) return;
  _loadedTasks.add(key);
  void Promise.resolve().then(loader).catch((err) => {
    console.warn(`[tools-page] ${key} load failed:`, err);
    captureThrownError(err, {
      source: 'tools-page.loader',
      action: key,
    });
  });
}

function _loadMaintenanceTab(): void {
  _runOnce('tab.maintenance', async () => {
    await loadDbInfo();
    await loadTagCount();
    await loadInferenceInfo();
    await loadScanErrors();
    await checkDebugMode();
    const [debugLog, backupManager] = await Promise.all([
      import('./debug-log'),
      import('./backup-manager'),
    ]);
    await debugLog.loadDebugLog(false);
    await backupManager.loadBackupStatus();
    await backupManager.loadBackupList();
    await loadUpdateStatus();
    _perf.markOnce('maintenance_ready');
  });
}

// lazy loader registration: fires on details toggle
registerLazy('tool-ai-analysis', () => _runOnce('search.ai', async () => {
  await _loadAiAnalysis();
  _perf.markOnce('search_ai_ready');
}));
registerLazy('tool-wd-tagger', () => _runOnce('search.wd_tagger', _loadWdTagger));
registerLazy('tool-video-analysis', () => _runOnce('search.video_analysis', _loadVideoAnalysis));
registerLazy('tool-archive-cleanup', () => _runOnce('organize.archive_cleanup', async () => {
  const mod = await import('./archive-cleanup/core');
  await mod.acTryRestore();
}));

// category first-view loaders
registerCategoryLoader('maintenance', () => _loadMaintenanceTab());
registerCategoryLoader('system', () => _runOnce('tab.scan', async () => {
  await loadScanRoots();
  await loadExtensions();
  _perf.markOnce('scan_ready');
}));

window.addEventListener('load', () => {
  _perf.markOnce('window_load');
});

initAccordion();
initSidebar();

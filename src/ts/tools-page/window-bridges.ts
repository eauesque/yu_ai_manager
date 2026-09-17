import { installWindowApi } from '../shared/window-api';
import { setStartupMode } from './startup-mode';
import {
  pickFolderNative,
  browseServerPath,
  browseServerParent,
  openServerDirBrowser,
  closeServerDirBrowser,
  selectCurrentServerDir,
  browseServerPathFromInput,
} from './dir-browser';
import { loadDbInfo, loadTagCount, loadInferenceInfo, loadScanErrors, resolveScanError, loadWdUntaggedCount, executeDebugSql } from './db-info';
import { findDuplicates, computeHashes } from './duplicates/find';
import {
  syncDupeCheck,
  previewDuplicateImage,
  selectAllDupes,
  setKeepImage,
  updateDupeDeleteCount,
} from './duplicates/ui';
import { deleteDuplicates, deleteDuplicatesHard } from './duplicates/delete';
import { previewNormalize, executeNormalize } from './tag-normalize';
import {
  aisActivate,
  aisTest,
  aisRemove,
  aisToggleEnabled,
  aisMigrateFromLegacy,
  aisRegisterDiscovered,
  aisTestDiscovered,
  aisMatchDiscovered,
  aisUnmatchDiscovered,
  aisIgnoreDiscovered,
  aisUnignoreDiscovered,
} from './ai-analysis/server-list';
import {
  aisCloseDialog,
  aisShowAddDialog,
  aisShowEditDialog,
  aisOnTypeChange,
  aisSaveDialog,
  aisRefreshModels,
} from './ai-analysis/server-dialog';
import { startScan } from './scan/start';
import { startScanAll } from './scan/all';
import { closeRescanDialog, executeRescan } from './roots/rescan';
import { downloadBackup, restoreBackup, triggerRestoreFile } from './backup';
import { loadExtensions } from './extensions-summary';
import { crossSearch } from './cross-search';
import {
  clearThumbnailCache,
  startFaststartPrescan,
  searchFiles,
} from './file-search/core';
import { checkForUpdate, applySystemUpdate, checkUnifiedUpdates, applyUnifiedUpdates } from './system-update';
import {
  acActionChange,
  acSelectAll,
  acSelectAllPerfect,
} from './archive-cleanup/actions';
import { acLlmVerify } from './archive-cleanup/llm';
import { loadGroups, warmGroupsIndex } from './groups-manager';
import { shutdownServer } from './shutdown-server';

type LazyModule = Record<string, (...args: any[]) => any>;

function lazyAction(loader: () => Promise<LazyModule>, name: string): (...args: any[]) => Promise<any> {
  return async (...args: any[]) => {
    const mod = await loader();
    return mod[name](...args);
  };
}

function lazyActions(loader: () => Promise<LazyModule>, names: string[]): LazyModule {
  return Object.fromEntries(names.map((name) => [name, lazyAction(loader, name)])) as LazyModule;
}

const aiCore = () => import('./ai-analysis/core') as Promise<LazyModule>;
const backupManager = () => import('./backup-manager') as Promise<LazyModule>;
const debugLog = () => import('./debug-log') as Promise<LazyModule>;
const wdTaggerCore = () => import('./wd-tagger/core') as Promise<LazyModule>;
const videoAnalysisCore = () => import('./video-analysis/core') as Promise<LazyModule>;
const archiveCleanupCore = () => import('./archive-cleanup/core') as Promise<LazyModule>;

const toolsPageApi = installWindowApi('toolsPageApi', {
  goExtensions: () => {
    window.location.href = '/extensions';
  },
  setStartupMode,
  pickFolderNative,
  browseServerPath,
  browseServerParent,
  openServerDirBrowser,
  closeServerDirBrowser,
  selectCurrentServerDir,
  browseServerPathFromInput,
  loadDbInfo,
  loadTagCount,
  loadInferenceInfo,
  loadScanErrors,
  resolveScanError,
  loadWdUntaggedCount,
  executeDebugSql,
  findDuplicates,
  computeHashes,
  syncDupeCheck,
  syncDupeCheckArg: (el: HTMLElement) => {
    const arg = el.dataset.actionArg || '';
    const [idxStr, fileIdxStr] = arg.split(':');
    syncDupeCheck(el as HTMLInputElement, parseInt(idxStr, 10), parseInt(fileIdxStr, 10));
  },
  previewDuplicateImage,
  selectAllDupes,
  setKeepImageArg: (arg: string) => {
    const sep = arg.indexOf(':');
    const groupIdx = parseInt(arg.slice(0, sep), 10);
    const fileIdx = parseInt(arg.slice(sep + 1), 10);
    setKeepImage(groupIdx, fileIdx);
  },
  updateDupeDeleteCount,
  deleteDuplicates,
  deleteDuplicatesHard,
  previewNormalize,
  executeNormalize,
  ...lazyActions(aiCore, [
    'loadAiConfig',
    'onAiEngineChange',
    'saveAiConfig',
    'analyzeCurrentBatch',
    'analyzePromptTrends',
    'loadOllamaModels',
    'testOllamaConnection',
    'loadOpenaiCompatModels',
    'testOpenaiCompatConnection',
    'onFallbackLocalOnlyChange',
    'cancelAiBatch',
    'deleteTrendHistoryEntry',
  ]),
  aisActivate,
  aisTest,
  aisShowEditDialog,
  aisToggleEnabled,
  aisToggleEnabledArg: (arg: string) => {
    const sep = arg.indexOf(':');
    const id = arg.slice(0, sep);
    const enabled = arg.slice(sep + 1) === 'true';
    aisToggleEnabled(id, enabled);
  },
  aisRemove,
  aisMigrateFromLegacy,
  aisRegisterDiscovered,
  aisTestDiscovered,
  aisMatchDiscovered,
  aisUnmatchDiscovered,
  aisIgnoreDiscovered,
  aisUnignoreDiscovered,
  aisShowAddDialog,
  aisCloseDialog,
  aisSaveDialog,
  aisOnTypeChange,
  aisRefreshModels,
  closeRescanDialog,
  executeRescan,
  ...lazyActions(backupManager, [
    'restoreFromBackup',
    'deleteBackupFile',
    'createManualBackup',
  ]),
  ...lazyActions(archiveCleanupCore, ['acSort', 'acFilter', 'acPage']),
  acActionChange,
  acActionChangeArg: (arg: string) => {
    const sep = arg.indexOf(':');
    const idx = parseInt(arg.slice(0, sep), 10);
    const action = arg.slice(sep + 1);
    acActionChange(idx, action);
  },
  acSelectAll,
  acSelectAllPerfect,
  acLlmVerify,
  acCloseExecBanner: () => {
    document.getElementById('acExecBanner')?.remove();
  },
  startScan,
  startScanAll,
  downloadBackup,
  triggerRestoreFile,
  restoreBackup,
  ...lazyActions(debugLog, [
    'loadDebugLog',
    'filterDebugLogClient',
    'toggleDebugLogAuto',
    'downloadDebugLog',
    'clearDebugLog',
  ]),
  loadExtensions,
  crossSearch,
  clearThumbnailCache,
  startFaststartPrescan,
  searchFiles,
  ...lazyActions(wdTaggerCore, [
    'wtLoadConfig',
    'wtSaveConfig',
    'wtDownloadModel',
    'wtRunBatch',
    'wtCancelBatch',
    'wtTestVlm',
    'wtToggleEngineUI',
  ]),
  ...lazyActions(videoAnalysisCore, ['vaSaveConfig', 'vaOnStrategyChange']),
  checkForUpdate,
  applySystemUpdate,
  checkUnifiedUpdates,
  applyUnifiedUpdates,
  ...lazyActions(archiveCleanupCore, [
    'acScan',
    'acExecute',
    'acPickFolder',
    'acLlmVerifyAll',
    'acLoadLlmConfig',
    'acSaveLlmConfig',
    'acOnLlmEngineChange',
    'acRefreshModels',
  ]),
  loadGroups,
  warmGroupsIndex,
  shutdownServer,
});
void toolsPageApi;

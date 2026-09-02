import { copyWithFeedback, notifyCopy } from './tools/copy';
import {
  openFileDirectory,
  renderFileName,
  renderPathDisplay,
  searchByCheckpoint,
  copySeed,
} from './tools/paths';
import { installWindowApi } from '../shared/window-api';

function memoImport<T>(loader: () => Promise<T>): () => Promise<T> {
  let promise: Promise<T> | null = null;
  return () => (promise ??= loader());
}

const _loadQrModule = memoImport(() => import('./tools/qr'));
const _loadRegexIntro = memoImport(() => import('./regex/intro'));
const _loadServerInfo = memoImport(() => import('./system/server-info'));
const _loadCheckpoints = memoImport(() => import('./system/checkpoints-init'));
const _loadFavorites = memoImport(() => import('./favorites/favorites'));
const _loadFavSelect = memoImport(() => import('./favorites/select'));
const _loadCollectionsSidebar = memoImport(() => import('./collections-sidebar'));
const _loadFolderTree = memoImport(() => import('./folder-tree'));
const _loadAnalysis = memoImport(() => import('./tools/analysis'));
const _loadConvert = memoImport(() => import('./tools/convert'));
const _loadPromptLibrary = memoImport(() => import('./tools/prompt-library-save'));
const _loadWdTags = memoImport(() => import('./tools/wd-tags'));

export function installRuntimeToolsUiWindowBridges(): void {
  installWindowApi('runtimeToolsApi', {
    copyWithFeedback,
    notifyCopy,
    renderFileName,
    renderPathDisplay,
    searchByCheckpoint,
    copySeed,
    openFileDirectory,
    analyzeCurrentImage: (fileId: number) =>
      _loadAnalysis().then((mod) => mod.analyzeCurrentImage(fileId)),
    loadSavedAnalysis: (fileId: number) =>
      _loadAnalysis().then((mod) => mod.loadSavedAnalysis(fileId)),
    convertAndCopy: (targetId: string, mode: string, evt?: Event) =>
      _loadConvert().then((mod) => mod.convertAndCopy(targetId, mode, evt)),
    convertAndShow: (targetId: string, mode: string, evt?: Event) =>
      _loadConvert().then((mod) => mod.convertAndShow(targetId, mode, evt)),
    showQRShare: (fileId: number) => _loadQrModule().then((mod) => mod.showQRShare(fileId)),
    generateQR: (fileId: number) => _loadQrModule().then((mod) => mod.generateQR(fileId)),
    copyQRContent: (fileId: number, triggerEl?: HTMLElement | null) =>
      _loadQrModule().then((mod) => mod.copyQRContent(fileId, triggerEl)),
    downloadQR: (fileId: number) => _loadQrModule().then((mod) => mod.downloadQR(fileId)),
    saveToPromptLibrary: (fileId: number) =>
      _loadPromptLibrary().then((mod) => mod.saveToPromptLibrary(fileId)),
    loadWdTags: (fileId: number) =>
      _loadWdTags().then((mod) => mod.loadWdTags(fileId)),
    viewXmpModal: (fileId: number) =>
      _loadWdTags().then((mod) => mod.viewXmpModal(fileId)),
    openRegexIntro: () => _loadRegexIntro().then((mod) => mod.openRegexIntro()),
    closeRegexIntro: () => _loadRegexIntro().then((mod) => mod.closeRegexIntro()),
    markCopyableExamples: () => _loadRegexIntro().then((mod) => mod.markCopyableExamples()),
    loadServerInfo: () => _loadServerInfo().then((mod) => mod.loadServerInfo()),
    loadCheckpoints: () => _loadCheckpoints().then((mod) => mod.loadCheckpoints()),
    toggleFavorite: (fileId: number, collectionId?: number) =>
      _loadFavorites().then((mod) => mod.toggleFavorite(fileId, collectionId)),
    checkFavorites: (ids: number[]) =>
      _loadFavorites().then((mod) => mod.checkFavorites(ids)),
    updateModalFavButton: (fileId: number) =>
      _loadFavorites().then((mod) => mod.updateModalFavButton(fileId)),
    loadCollectionFilter: () =>
      _loadFavorites().then((mod) => mod.loadCollectionFilter()),
    favSelectToggle: () => _loadFavSelect().then((mod) => mod.favSelectToggle()),
    favSelectChanged: () => _loadFavSelect().then((mod) => mod.favSelectChanged()),
    favSelectAll: () => _loadFavSelect().then((mod) => mod.favSelectAll()),
    favDeselectAll: () => _loadFavSelect().then((mod) => mod.favDeselectAll()),
    favBatchAdd: () => _loadFavSelect().then((mod) => mod.favBatchAdd()),
    favBatchRemove: () => _loadFavSelect().then((mod) => mod.favBatchRemove()),
    favShowCollDropdown: (el?: HTMLElement) => {
      if (!el) return Promise.resolve();
      return _loadFavSelect().then((mod) => mod.favShowCollDropdown(el));
    },
    favBatchAddToCollection: (collectionId: number) =>
      _loadFavSelect().then((mod) => mod.favBatchAddToCollection(collectionId)),
    favBatchDownloadZip: () => _loadFavSelect().then((mod) => mod.favBatchDownloadZip()),
    refreshCollectionSidebar: () =>
      _loadCollectionsSidebar().then((mod) => mod.loadSidebarCollections()),
    loadFolderTree: () =>
      _loadFolderTree().then((mod) => mod.loadFolderTree()),
    refreshFolderTree: () =>
      _loadFolderTree().then((mod) => mod.refreshFolderTree()),
    selectFolder: (path: string) =>
      _loadFolderTree().then((mod) => mod.selectFolder(path)),
    clearFolderSelection: () =>
      _loadFolderTree().then((mod) => mod.clearFolderSelection()),
  });
}

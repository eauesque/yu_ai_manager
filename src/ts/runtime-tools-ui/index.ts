/**
 * runtime-tools-ui entry point — initializes tools, UI, favorites, and sidebar.
 */
// --- ui ---
import { initUiCore } from './ui/init';

// --- favorites ---
// --- SSE sync ---
import { initSseSync } from './sse-sync';
import { initRuntimeToolsUiHooks } from './hooks';
import { installRuntimeToolsUiWindowBridges } from './bridges';
import { getDetailModalApi, getSearchResultsApi } from '../shared/browser-apis';
import { scheduleVisibleIdle as _scheduleIdle } from '../shared/idle';

function memoImport<T>(loader: () => Promise<T>): () => Promise<T> {
  let promise: Promise<T> | null = null;
  return () => (promise ??= loader());
}

const _loadRegexIntro = memoImport(() => import('./regex/intro'));
const _loadCheckpoints = memoImport(() => import('./system/checkpoints-init'));
const _loadFavorites = memoImport(() => import('./favorites/favorites'));
const _loadFavSelect = memoImport(() => import('./favorites/select'));
const _loadCollectionsSidebar = memoImport(() => import('./collections-sidebar'));
const _loadFolderTree = memoImport(() => import('./folder-tree'));


// ========================================================================
// Initialization
// ========================================================================

initRuntimeToolsUiHooks({
  checkFavorites: (ids: number[]) => {
    void _loadFavorites().then((mod) => mod.checkFavorites(ids)).catch(() => {});
  },
  closeModal: () => getDetailModalApi().closeModal(),
  loadCollectionFilter: () => {
    void _loadFavorites().then((mod) => mod.loadCollectionFilter()).catch(() => {});
  },
  loadFolderTree: () => {
    void _loadFolderTree().then((mod) => mod.loadFolderTree()).catch(() => {});
  },
  refreshCollectionSidebar: () => {
    void _loadCollectionsSidebar().then((mod) => mod.loadSidebarCollections()).catch(() => {});
  },
  runSearch: (event?: Event) => { getSearchResultsApi().runSearch(event); },
  showDetail: (id: number, opts?: any) => { getDetailModalApi().showDetail(id, opts); },
});
installRuntimeToolsUiWindowBridges();

initUiCore();
initSseSync();

_scheduleIdle(() => _loadFavorites().then((mod) => {
  mod.initFavorites();
}));
_scheduleIdle(() => _loadFavSelect().then((mod) => {
  mod.initFavSelect();
}));
_scheduleIdle(() => _loadCollectionsSidebar().then((mod) => {
  mod.initCollectionsSidebar();
}));
_scheduleIdle(() => _loadFolderTree().then((mod) => {
  mod.initFolderTree();
}));

_scheduleIdle(() => _loadRegexIntro().then((mod) => {
  mod.initCopyableClickHandler();
}));
_scheduleIdle(() => _loadCheckpoints().then((mod) => {
  mod.initCheckpoints();
}));

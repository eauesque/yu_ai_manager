interface RuntimeToolsUiHooks {
  checkFavorites: (ids: number[]) => void;
  closeModal: () => void;
  loadCollectionFilter: () => void;
  loadFolderTree: () => void;
  refreshCollectionSidebar: () => void;
  runSearch: (event?: Event) => void;
  showDetail: (id: number, opts?: any) => void;
}

const hooks: RuntimeToolsUiHooks = {
  checkFavorites: () => {},
  closeModal: () => {},
  loadCollectionFilter: () => {},
  loadFolderTree: () => {},
  refreshCollectionSidebar: () => {},
  runSearch: () => {},
  showDetail: () => {},
};

export function initRuntimeToolsUiHooks(nextHooks: RuntimeToolsUiHooks): void {
  hooks.checkFavorites = nextHooks.checkFavorites;
  hooks.closeModal = nextHooks.closeModal;
  hooks.loadCollectionFilter = nextHooks.loadCollectionFilter;
  hooks.loadFolderTree = nextHooks.loadFolderTree;
  hooks.refreshCollectionSidebar = nextHooks.refreshCollectionSidebar;
  hooks.runSearch = nextHooks.runSearch;
  hooks.showDetail = nextHooks.showDetail;
}

export function getRuntimeToolsUiHooks(): RuntimeToolsUiHooks {
  return hooks;
}

/**
 * collections-sidebar.ts -- Left sidebar for collection management on search page.
 * Handles init, list rendering, collapse/expand, tab switching, and mobile drawer.
 *
 * CRUD operations are in collections-crud.ts.
 * Smart collection / UNION logic is in collections-smart.ts.
 * List item rendering + event delegation are in collections-list-item.ts.
 * Shared state lives in collections-state.ts.
 */

import {
  type CollectionRecord,
  _t,
  STORAGE_KEY,
  STORAGE_KEY_TAB,
  getActiveValue,
  getSidebar,
  getListEl,
  getAddInput,
  getAddBtn,
  selectCollection,
  setSidebar,
  setListEl,
  setAddInput,
  setAddBtn,
} from './collections-state';
import { handleCreate } from './collections-crud';
import {
  updateUnionBtnVisibility,
  saveCurrentSearch,
  createUnionButtons,
} from './collections-smart';
import { initMobileDrawer } from './collections-drawer';
import { safeViewTransition } from '../shared/view-transition';
import { rebuildCollMap, makeItem, handleListClick, handleListKeydown } from './collections-list-item';
import { getRuntimeToolsUiHooks } from './hooks';
import { getAppApi } from '../shared/browser-apis';

// Re-export selectCollection so existing imports from this module keep working
export { selectCollection };

// -- Collapse/Expand --
function setCollapsed(collapsed: boolean): void {
  const sidebar = getSidebar();
  if (!sidebar) return;
  const doCollapse = () => {
    sidebar.classList.toggle('cs-collapsed', collapsed);
    const collapseBtn = document.getElementById('csCollapseBtn');
    if (collapseBtn) collapseBtn.innerHTML = collapsed ? '&raquo;' : '&laquo;';
  };
  safeViewTransition(doCollapse);
  try { localStorage.setItem(STORAGE_KEY, collapsed ? '1' : ''); } catch (_e) { /* ignore */ }
}

// -- Render collection list --
export async function loadSidebarCollections(): Promise<void> {
  const listEl = getListEl();
  if (!listEl) return;
  try {
    const response = await getAppApi().apiFetch('/api/collections');
    if (!response.ok) return;
    const data = await response.json();
    const collections: CollectionRecord[] = data.collections || [];
    const activeVal = getActiveValue();

    rebuildCollMap(collections);

    listEl.innerHTML = '';

    // Fixed: "All" item
    listEl.appendChild(makeItem('', _t('collections.all_items', 'All'), null, activeVal));

    // Fixed: "All Favorites" item
    listEl.appendChild(makeItem('all', '\u2B50 ' + _t('collections.all_favorites', 'All Favorites'), null, activeVal));

    // Dynamic collections
    collections.forEach((coll) => {
      listEl.appendChild(makeItem(String(coll.id), coll.name, coll, activeVal));
    });

    // Sync UNION button visibility with current check state
    updateUnionBtnVisibility();
  } catch (e) {
    console.error('loadSidebarCollections failed:', e);
  }
}

/**
 * Initialize the collections sidebar. Checks for DOM elements
 * and sets up event listeners. Noop if sidebar element is absent.
 */
export function initCollectionsSidebar(): void {
  const sidebar = document.getElementById('collectionsSidebar');
  setSidebar(sidebar);
  if (!sidebar) return;

  const collapseBtn = document.getElementById('csCollapseBtn');
  const listEl = document.getElementById('csCollectionList');
  setListEl(listEl);
  setAddInput(document.getElementById('csNewName') as HTMLInputElement | null);
  setAddBtn(document.getElementById('csAddBtn'));

  // Event delegation: install handler once on the list container
  if (listEl) {
    listEl.addEventListener('click', handleListClick);
    listEl.addEventListener('keydown', handleListKeydown);
  }

  // Restore collapse state
  try {
    if (localStorage.getItem(STORAGE_KEY) === '1') setCollapsed(true);
  } catch (_e) { /* ignore */ }

  if (collapseBtn) {
    collapseBtn.addEventListener('click', () => {
      const isCollapsed = sidebar.classList.contains('cs-collapsed');
      setCollapsed(!isCollapsed);
    });
  }

  const addBtn = getAddBtn();
  const addInput = getAddInput();
  if (addBtn) addBtn.addEventListener('click', handleCreate);
  if (addInput) {
    addInput.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter') { e.preventDefault(); handleCreate(); }
      e.stopPropagation();
    });
  }

  // Save current search as smart collection
  const saveSearchBtn = document.getElementById('csSaveSearchBtn');
  if (saveSearchBtn) {
    saveSearchBtn.addEventListener('click', () => {
      saveCurrentSearch();
    });
  }

  // UNION search buttons (delegated to collections-smart)
  const btnContainer = createUnionButtons();
  const addRow = addInput?.closest('.cs-add') as HTMLElement | null;
  if (addRow && addRow.parentElement) {
    addRow.parentElement.insertBefore(btnContainer, addRow);
  } else {
    sidebar.appendChild(btnContainer);
  }

  // -- Tab switching (Collections / Folders) --
  _initTabSwitching();

  // Initial load
  loadSidebarCollections();

  // -- Mobile drawer --
  initMobileDrawer();
}

function _initTabSwitching(): void {
  const tabCollections = document.getElementById('csTabCollections');
  const tabFolders = document.getElementById('csTabFolders');

  function switchTab(tab: string): void {
    const doSwitch = () => {
      document.querySelectorAll('.cs-tab').forEach((t) => {
        const isActive = (t as HTMLElement).dataset.tab === tab;
        t.classList.toggle('active', isActive);
        t.setAttribute('aria-selected', isActive ? 'true' : 'false');
      });
      document.querySelectorAll('.cs-tab-panel').forEach((p) => {
        const panelId = 'csPanel' + tab.charAt(0).toUpperCase() + tab.slice(1);
        p.classList.toggle('active', p.id === panelId);
      });
    };
    safeViewTransition(doSwitch);
    try { localStorage.setItem(STORAGE_KEY_TAB, tab); } catch (_e) { /* ignore */ }
    // Lazy load folder tree on first switch
    if (tab === 'folders') getRuntimeToolsUiHooks().loadFolderTree();
  }

  if (tabCollections) tabCollections.addEventListener('click', () => switchTab('collections'));
  if (tabFolders) tabFolders.addEventListener('click', () => switchTab('folders'));

  // Restore saved tab
  try {
    const savedTab = localStorage.getItem(STORAGE_KEY_TAB);
    if (savedTab === 'folders') switchTab('folders');
  } catch (_e) { /* ignore */ }
}

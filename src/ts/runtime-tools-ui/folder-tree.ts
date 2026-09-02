/**
 * folder-tree.ts — Folder tree panel for the sidebar on search page.
 * Main entry point: event handling, interactions, state persistence,
 * data fetch, and initialization.
 *
 * Tree construction lives in folder-tree-model.ts,
 * HTML rendering lives in folder-tree-render.ts.
 */

import {
  type FolderNode,
  type GroupsIndex,
  ftState,
  STORAGE_KEY_EXPANDED,
  STORAGE_KEY_SELECTED,
  buildTree,
} from './folder-tree-model';
import { renderTree } from './folder-tree-render';
import { getRuntimeToolsUiHooks } from './hooks';
import { getAppApi } from '../shared/browser-apis';

// Re-export public API so external imports from './folder-tree' keep working
export { buildTree, renderTree };
export type { FolderNode, GroupsIndex };

// ---------------------------------------------------------------------------
// Event handling (delegated)
// ---------------------------------------------------------------------------

function _handleTreeClick(e: MouseEvent): void {
  const target = e.target as HTMLElement;

  // Toggle arrow click
  const toggleEl = target.closest('.ft-toggle[data-action="toggle"]') as HTMLElement | null;
  if (toggleEl) {
    const path = toggleEl.dataset.path || '';
    toggleFolder(path);
    return;
  }

  // Node row click -> select folder
  const nodeEl = target.closest('.ft-node') as HTMLElement | null;
  if (nodeEl) {
    const path = nodeEl.dataset.path ?? '';
    if (!path || ftState.selectedPath === path) {
      clearFolderSelection();
    } else {
      selectFolder(path);
    }
  }
}

// ---------------------------------------------------------------------------
// Interactions
// ---------------------------------------------------------------------------

export function toggleFolder(path: string): void {
  const wasExpanded = ftState.expanded[path] ?? false;
  ftState.expanded[path] = !wasExpanded;
  _persistExpanded();
  renderTree();
}

export function selectFolder(path: string): void {
  ftState.selectedPath = path;
  _persistSelected();

  // Set inPath field and trigger search
  const inPathEl = document.getElementById('inPath') as HTMLInputElement | null;
  if (inPathEl) {
    inPathEl.value = path;
  }
  getRuntimeToolsUiHooks().runSearch();

  renderTree();
}

export function clearFolderSelection(): void {
  ftState.selectedPath = null;
  _persistSelected();

  const inPathEl = document.getElementById('inPath') as HTMLInputElement | null;
  if (inPathEl) inPathEl.value = '';
  getRuntimeToolsUiHooks().runSearch();

  renderTree();
}

// ---------------------------------------------------------------------------
// State persistence (localStorage)
// ---------------------------------------------------------------------------

function _persistExpanded(): void {
  try {
    localStorage.setItem(STORAGE_KEY_EXPANDED, JSON.stringify(ftState.expanded));
  } catch (_e) { /* ignore */ }
}

function _restoreExpanded(): void {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_EXPANDED);
    if (raw) ftState.expanded = JSON.parse(raw);
  } catch (_e) {
    ftState.expanded = {};
  }
}

function _persistSelected(): void {
  try {
    if (ftState.selectedPath) {
      localStorage.setItem(STORAGE_KEY_SELECTED, ftState.selectedPath);
    } else {
      localStorage.removeItem(STORAGE_KEY_SELECTED);
    }
  } catch (_e) { /* ignore */ }
}

function _restoreSelected(): void {
  try {
    ftState.selectedPath = localStorage.getItem(STORAGE_KEY_SELECTED) || null;
  } catch (_e) {
    ftState.selectedPath = null;
  }
}

// ---------------------------------------------------------------------------
// Data fetch & init
// ---------------------------------------------------------------------------

export async function loadFolderTree(): Promise<void> {
  if (ftState.loaded) return;

  try {
    const response = await getAppApi().apiFetch('/api/groups-index');
    if (!response.ok) return;
    const data: GroupsIndex = await response.json();
    ftState.root = buildTree(data);
    ftState.folderCountTotal = _countLeafFolders(ftState.root);
    ftState.loaded = true;

    // If there was a selected path, restore inPath
    if (ftState.selectedPath) {
      const inPathEl = document.getElementById('inPath') as HTMLInputElement | null;
      if (inPathEl && !inPathEl.value) {
        inPathEl.value = ftState.selectedPath;
      }
    }

    renderTree();
  } catch (e) {
    console.error('loadFolderTree failed:', e);
  }
}

/**
 * Force-refresh the folder tree: reset cache and reload data.
 * Preserves expand/selection state.
 */
export async function refreshFolderTree(): Promise<void> {
  ftState.loaded = false;
  ftState.root = null;
  await loadFolderTree();
}

function _countLeafFolders(node: FolderNode): number {
  if (node.children.size === 0) return 1;
  let count = 0;
  for (const child of node.children.values()) {
    count += _countLeafFolders(child);
  }
  return count;
}

/**
 * Initialize folder tree. Grabs DOM refs and restores persisted state.
 * Actual data loading is deferred until tab switch (lazy).
 */
export function initFolderTree(): void {
  ftState.treeEl = document.getElementById('ftTree');
  ftState.filterInput = document.getElementById('ftFilter') as HTMLInputElement | null;
  ftState.countEl = document.getElementById('ftFolderCount');

  if (!ftState.treeEl) return;

  // Attach delegated click handler (event delegation on container, set once)
  ftState.treeEl.onclick = _handleTreeClick;

  _restoreExpanded();
  _restoreSelected();

  // Filter input
  if (ftState.filterInput) {
    let debounceTimer: ReturnType<typeof setTimeout> | null = null;
    ftState.filterInput.addEventListener('input', () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        ftState.filterText = ftState.filterInput!.value.trim();
        renderTree();
      }, 200);
    });
    // Prevent search shortcut keys from interfering
    ftState.filterInput.addEventListener('keydown', (e: KeyboardEvent) => {
      e.stopPropagation();
    });
  }
}

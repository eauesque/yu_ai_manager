/**
 * runtime-init entry point — bundles NovelAI character parsing/rendering,
 * keyboard hints, scan progress, search persistence, grid controls,
 * search modal, and scroll/header management.
 */

import { showKeyboardHint, hideKeyboardHint, initKeyboardHint } from './novelai/keyboard';

// --- scan (legacy stubs — progress handled by nav/job-progress.ts) ---
import { startScanProgress, hideScanProgress } from './scan/progress';
import { installFocusRescan } from './scan/focus-rescan';

// --- persistence ---
import './persistence/fields';
import { saveSearchState, restoreSearchState } from './persistence/core';
import { clearInput, clearAllInputs } from './persistence/ui';
import { initPersistenceNav } from './persistence/nav';
import { installWindowApi } from '../shared/window-api';

// --- nav ---
import { setGridColumns, initGridColumns } from './nav/grid';
import { showScrollBackBtn, scrollBackToPosition, toggleHeaderInfo } from './nav/scroll-header';
import { scheduleVisibleIdle as _scheduleIdle } from '../shared/idle';

function memoImport<T>(loader: () => Promise<T>): () => Promise<T> {
  let promise: Promise<T> | null = null;
  return () => (promise ??= loader());
}

const _loadCharacterParse = memoImport(() => import('./novelai/character-parse'));
const _loadCharacterRender = memoImport(() => import('./novelai/character-render'));
const _loadCharacterGrid = memoImport(() => import('./novelai/character-grid'));
const _loadPresets = memoImport(() => import('./persistence/presets'));
const _loadSearchModal = memoImport(() => import('./nav/search-modal'));
const _loadScrollHeaderInit = memoImport(() => import('./nav/scroll-header-init'));


// ============================================================
// Window bridges — onclick handlers
// ============================================================

installWindowApi('runtimeInitApi', {
  parseNovelAICharacterPrompts: (rawMetaJson: string) =>
    _loadCharacterParse().then((mod) => mod.parseNovelAICharacterPrompts(rawMetaJson)),
  renderCharacterPrompts: (container: HTMLElement, data: unknown) =>
    _loadCharacterRender().then((mod) => mod.renderCharacterPrompts(container, data as never)),
  renderCharacterGrid: (wrapper: HTMLElement, imgEl: HTMLElement, characters: unknown) =>
    _loadCharacterGrid().then((mod) => mod.renderCharacterGrid(wrapper, imgEl, characters as never)),
  removeCharacterGrid: (wrapper: HTMLElement) =>
    _loadCharacterGrid().then((mod) => mod.removeCharacterGrid(wrapper)),
  toggleCharacterGrid: (wrapper: HTMLElement) =>
    _loadCharacterGrid().then((mod) => mod.toggleCharacterGrid(wrapper)),
  showKeyboardHint,
  hideKeyboardHint,
  startScanProgress,
  hideScanProgress,
  saveSearchState,
  restoreSearchState,
  clearInput,
  clearAllInputs,
  savePreset: () => _loadPresets().then((mod) => mod.savePreset()),
  loadPreset: (name: string) => _loadPresets().then((mod) => mod.loadPreset(name)),
  deletePreset: (name: string) => _loadPresets().then((mod) => mod.deletePreset(name)),
  togglePresetMenu: () => _loadPresets().then((mod) => mod.togglePresetMenu()),
  setGridColumns,
  openSearchOrModal: () => _loadSearchModal().then((mod) => mod.openSearchOrModal()),
  openSearchModal: () => _loadSearchModal().then((mod) => mod.openSearchModal()),
  closeSearchModal: () => _loadSearchModal().then((mod) => mod.closeSearchModal()),
  executeSearchModal: () => _loadSearchModal().then((mod) => mod.executeSearchModal()),
  showScrollBackBtn,
  scrollBackToPosition,
  toggleHeaderInfo,
});

// ============================================================
// Initialization
// ============================================================

initKeyboardHint();
initPersistenceNav();
initGridColumns();
installFocusRescan();
_scheduleIdle(() => _loadScrollHeaderInit().then((mod) => {
  mod.initScrollHeader();
}));

/* Search util overflow (⋯) menu */
(function initSearchUtilOverflow() {
  const btn = document.getElementById('searchUtilOverflowBtn');
  const menu = document.getElementById('searchUtilOverflow');
  if (!btn || !menu) return;
  btn.addEventListener('click', (e: Event) => {
    e.stopPropagation();
    const open = menu.style.display !== 'none';
    menu.style.display = open ? 'none' : 'block';
    btn.setAttribute('aria-expanded', String(!open));
  });
  document.addEventListener('click', (e: Event) => {
    if (!(e.target as HTMLElement).closest('.search-util-overflow-wrap')) {
      menu.style.display = 'none';
      btn.setAttribute('aria-expanded', 'false');
    }
  });
})();

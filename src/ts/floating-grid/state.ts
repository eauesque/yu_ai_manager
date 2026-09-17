/**
 * floating-grid/state — DOM references, panel toggle, grid state queries,
 * compact mode detection, and live info display.
 *
 * Converted from templates/index/floating_grid_ctrl/_script_core_state.html
 */

import { safeViewTransition } from '../shared/view-transition';
import { isVirtualScrollActive, vsGetAllIds } from '../search-results/results/virtual-scroll-bridge';

// ---------------------------------------------------------------------------
// DOM references (nullable — elements may not exist)
// ---------------------------------------------------------------------------

export const re = document.getElementById('results');
export const ss = document.getElementById('gridSizeSlider') as HTMLInputElement | null;
export const cs = document.getElementById('gridColSlider') as HTMLInputElement | null;
export const sizeVal = document.getElementById('gridSizeVal');
export const colVal = document.getElementById('gridColVal');

const ctrl = document.getElementById('floatingGridCtrl');
const liveInfo = document.getElementById('gridLiveInfo');
const toggle = document.getElementById('fgcToggle');
const body = document.getElementById('fgcBody');

// ---------------------------------------------------------------------------
// Result count helper
// ---------------------------------------------------------------------------

function getResultCount(): number {
  // When virtual scroll is active, return the total count from the DataStore
  if (isVirtualScrollActive()) {
    return vsGetAllIds().length;
  }
  return re ? re.querySelectorAll('.result-card').length : 0;
}

// ---------------------------------------------------------------------------
// Panel visibility
// ---------------------------------------------------------------------------

export function setCtrlVisible(): void {
  if (!re || !ctrl) return;
  ctrl.style.display = getResultCount() > 0 ? 'flex' : 'none';
}

// ---------------------------------------------------------------------------
// Panel open / close / toggle
// ---------------------------------------------------------------------------

export function isPanelOpen(): boolean {
  return !!(body && body.style.display !== 'none');
}

function openPanel(): void {
  if (!body || !toggle) return;
  const doOpen = () => {
    body!.style.display = '';
    toggle!.classList.add('active');
  };
  safeViewTransition(doOpen);
}

export function closePanel(): void {
  if (!body || !toggle) return;
  const doClose = () => {
    body!.style.display = 'none';
    toggle!.classList.remove('active');
  };
  safeViewTransition(doClose);
}

function togglePanel(): void {
  if (isPanelOpen()) closePanel();
  else openPanel();
}

// Bind toggle button click
if (toggle) {
  toggle.addEventListener('click', (e: Event) => {
    e.stopPropagation();
    togglePanel();
  });
}

// Close panel on outside click
document.addEventListener('click', (e: Event) => {
  if (!isPanelOpen()) return;
  if (ctrl && !ctrl.contains(e.target as Node)) closePanel();
});

// ---------------------------------------------------------------------------
// Grid state queries
// ---------------------------------------------------------------------------

export function getCurrentMinSize(): number {
  return parseInt((ss && ss.value) || localStorage.getItem('gridMinSize') || '300', 10) || 300;
}

export function getCurrentCols(): number {
  return parseInt((cs && cs.value) || localStorage.getItem('gridColumns') || '0', 10) || 0;
}

export function estimateAutoCols(minSize: number): number {
  if (!re) return 0;
  const w = re.clientWidth || 0;
  if (!w || !minSize) return 0;
  return Math.max(1, Math.floor(w / minSize));
}

// ---------------------------------------------------------------------------
// Compact mode
// ---------------------------------------------------------------------------

export function isCompactMode(): boolean {
  if (!re) return false;
  const cols = getCurrentCols();
  if (cols >= 5) return true;
  const minSize = getCurrentMinSize();
  const cardWidth = cols > 0
    ? Math.floor((re.clientWidth || 0) / Math.max(cols, 1))
    : minSize;
  return cardWidth > 0 && cardWidth < 220;
}

export function updateCompactMode(): void {
  if (!re) return;
  re.classList.toggle('compact-grid', isCompactMode());
}

// ---------------------------------------------------------------------------
// Live info display
// ---------------------------------------------------------------------------

export function updateLiveInfo(): void {
  if (!liveInfo) return;
  const count = getResultCount();
  const cols = getCurrentCols();
  const minSize = getCurrentMinSize();
  const _t: (key: string, fallback: string) => string =
    typeof window.tr === 'function'
      ? (k, f) => window.tr(k, f)
      : (_k, f) => f || '';
  const colUnit = _t('grid.col_unit', '\u5217');
  const colText = cols > 0
    ? (cols + _t('grid.col_fixed', '\u5217\uFF08\u56FA\u5B9A\uFF09'))
    : (_t('grid.auto', '\u81EA\u52D5') + '(' + estimateAutoCols(minSize) + colUnit + ')');
  const sizeHint = cols > 0 ? _t('grid.size_hint', ' / \u30B5\u30A4\u30BA\u306F\u81EA\u52D5\u6642\u306B\u53CD\u6620') : '';
  const compact = isCompactMode();
  liveInfo.textContent =
    _t('grid.count_prefix', '\u8868\u793A: ') + count +
    _t('grid.count_unit', '\u4EF6 / ') + colText + sizeHint +
    (compact ? _t('grid.image_only', ' / \u753B\u50CF\u306E\u307F') : '');
}

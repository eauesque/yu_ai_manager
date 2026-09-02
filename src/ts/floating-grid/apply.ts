/**
 * floating-grid/apply — applyMinSize and applyCols functions.
 * Sets CSS custom properties on the results grid and persists to localStorage.
 *
 * Converted from templates/index/floating_grid_ctrl/_script_core_apply.html
 */

import { re, sizeVal, colVal, updateCompactMode, updateLiveInfo } from './state';
import { getRuntimeInitApi } from '../shared/browser-apis';

function _syncCvGrid(cols: string | null, minSize: string | null): void {
  const cv = document.getElementById('cvGrid');
  if (!cv) return;
  if (cols !== null) {
    if (cols === '0' || cols === '') cv.style.removeProperty('--grid-columns');
    else cv.style.setProperty('--grid-columns', cols);
  }
  if (minSize !== null) {
    cv.style.setProperty('--grid-min-size', minSize);
  }
}

// ---------------------------------------------------------------------------
// applyMinSize — set minimum card size (CSS custom property + localStorage)
// ---------------------------------------------------------------------------

export function applyMinSize(px: number): void {
  const g = document.getElementById('results');
  if (sizeVal) sizeVal.textContent = String(px);
  if (g) g.style.setProperty('--grid-min-size', px + 'px');
  localStorage.setItem('gridMinSize', String(px));
  // Sync to ContainerView grid if open
  _syncCvGrid(null, px + 'px');
  updateCompactMode();
  updateLiveInfo();
}

// ---------------------------------------------------------------------------
// applyCols — set fixed column count or auto (CSS custom property + localStorage)
// ---------------------------------------------------------------------------

export function applyCols(n: number): void {
  const runtimeInitApi = getRuntimeInitApi();
  const _t: (key: string, fallback: string) => string =
    typeof window.tr === 'function'
      ? (k, f) => window.tr(k, f)
      : (_k, f) => f || '';
  if (colVal) {
    colVal.textContent = n === 0
      ? _t('grid.auto', '\u81EA\u52D5')
      : (n + _t('grid.col_unit', '\u5217'));
  }
  runtimeInitApi.setGridColumns(n);
  updateCompactMode();
  updateLiveInfo();
}

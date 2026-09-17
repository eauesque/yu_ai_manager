/**
 * floating-grid/init — slider event bindings, MutationObserver,
 * resize handler, and saved state restoration.
 *
 * Converted from templates/index/floating_grid_ctrl/_script_init.html
 */

import {
  re, ss, cs, sizeVal,
  setCtrlVisible, updateCompactMode, updateLiveInfo,
  getCurrentMinSize, getCurrentCols,
} from './state';
import { applyMinSize, applyCols } from './apply';
import { vsRefreshLayout } from '../search-results/results/virtual-scroll-bridge';

// ---------------------------------------------------------------------------
// Slider event bindings
// rAF debounce: prevent high-frequency DOM repaints when virtual scroll is active.
// Firefox workaround: performing heavy DOM operations (vsRefreshLayout) during drag
// causes the range input to lose pointer capture, snapping the thumb back.
// Therefore, only CSS updates are done on 'input'; VS repaint is deferred to 'change'.
// ---------------------------------------------------------------------------

let _sizeRaf: number | null = null;
let _colRaf: number | null = null;

if (ss) {
  ss.addEventListener('input', function (this: HTMLInputElement) {
    const px = parseInt(this.value, 10) || 300;
    // Update the label immediately (to keep the UI responsive)
    if (sizeVal) sizeVal.textContent = String(px);
    // Batch CSS + DOM updates via rAF (VS repaint deferred until drag ends)
    if (_sizeRaf !== null) cancelAnimationFrame(_sizeRaf);
    _sizeRaf = requestAnimationFrame(() => {
      _sizeRaf = null;
      applyMinSize(px);
    });
  });
  // Repaint virtual scroll on drag end
  ss.addEventListener('change', () => vsRefreshLayout());
}

if (cs) {
  cs.addEventListener('input', function (this: HTMLInputElement) {
    const n = parseInt(this.value, 10) || 0;
    // Batch CSS + DOM updates via rAF (VS repaint deferred until drag ends)
    if (_colRaf !== null) cancelAnimationFrame(_colRaf);
    _colRaf = requestAnimationFrame(() => {
      _colRaf = null;
      applyCols(n);
    });
  });
  // Repaint virtual scroll on drag end
  cs.addEventListener('change', () => vsRefreshLayout());
}

// ---------------------------------------------------------------------------
// MutationObserver — react to result card changes
// ---------------------------------------------------------------------------

if (re) {
  const obs = new MutationObserver(() => {
    setCtrlVisible();
    updateCompactMode();
    updateLiveInfo();
  });
  obs.observe(re, { childList: true, subtree: true });
}

// ---------------------------------------------------------------------------
// Window globals
// ---------------------------------------------------------------------------

window.updateGridCompactMode = updateCompactMode;

// ---------------------------------------------------------------------------
// Resize handler
// ---------------------------------------------------------------------------

window.addEventListener('resize', () => {
  updateCompactMode();
  updateLiveInfo();
});

// ---------------------------------------------------------------------------
// Restore saved state from localStorage
// ---------------------------------------------------------------------------

const savedSize = localStorage.getItem('gridMinSize');
if (savedSize && ss) ss.value = savedSize;
applyMinSize(getCurrentMinSize());

const savedCols = localStorage.getItem('gridColumns');
if (savedCols && cs) cs.value = savedCols;
applyCols(getCurrentCols());
updateCompactMode();
setCtrlVisible();

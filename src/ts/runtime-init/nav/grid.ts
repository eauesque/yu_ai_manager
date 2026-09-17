/**
 * Grid column controls — set/restore grid column count.
 */

export function setGridColumns(n: string | number): void {
  const grid = document.getElementById('results');
  if (!grid) return;
  const cols = parseInt(String(n), 10) || 0;
  if (cols > 0) grid.style.setProperty('--grid-columns', String(cols));
  else grid.style.removeProperty('--grid-columns');
  localStorage.setItem('gridColumns', String(n));
  if (typeof window.updateGridCompactMode === 'function') window.updateGridCompactMode();
  else grid.classList.toggle('compact-grid', cols >= 5);
  // Sync to ContainerView grid if open
  _syncCvGrid(cols > 0 ? String(cols) : null, null);
}

declare global {
  interface Window {
    updateGridCompactMode?: () => void;
  }
}

/**
 * Sync --grid-columns / --grid-min-size to the ContainerView grid (#cvGrid).
 * Called from setGridColumns and exported for floating-grid applyMinSize.
 */
export function _syncCvGrid(cols: string | null, minSize: string | null): void {
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

/**
 * Restore saved grid column setting from localStorage.
 * Call once during page initialization.
 */
export function initGridColumns(): void {
  const saved = localStorage.getItem('gridColumns');
  if (!saved) return;
  const sel = document.getElementById('gridColumns') as HTMLSelectElement | null;
  if (sel) sel.value = saved;
  setGridColumns(saved);
}

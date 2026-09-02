/**
 * virtual-scroll-bridge.ts
 *
 * Bridge connecting VirtualGrid to the existing search results rendering pipeline.
 * When isVirtualScrollEnabled() is true and groupMode === 'all',
 * render.ts displayResults / appendResults delegate here.
 *
 * Virtual scroll is disabled in group mode (folder/zip/archive)
 * because group display directly manipulates the DOM and cannot coexist with VirtualGrid.
 */

import { VirtualGrid, VirtualGridDataStore, isVirtualScrollEnabled } from '../../virtual-grid';
import { resetThumbnailBatch } from './thumbnail-batch';
import { getMode } from './grouping-utils';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ResultRecord = Record<string, any>;

let _vgInstance: VirtualGrid | null = null;
let _vgDataStore: VirtualGridDataStore | null = null;

/** True when group mode is not 'all' (disables virtual scroll) */
function _isGroupedMode(): boolean {
  try {
    return getMode() !== 'all';
  } catch {
    return false;
  }
}

/** Returns true if virtual scroll is enabled and initialized */
export function isVirtualScrollActive(): boolean {
  return isVirtualScrollEnabled() && !_isGroupedMode() && _vgInstance !== null;
}

/** Get VirtualGrid instance (lazy initialization) */
function ensureInstance(): { grid: VirtualGrid; store: VirtualGridDataStore } | null {
  const container = document.getElementById('results');
  if (!container) return null;

  if (!_vgDataStore) {
    _vgDataStore = new VirtualGridDataStore();
  }
  if (!_vgInstance) {
    _vgInstance = new VirtualGrid(container, _vgDataStore);
  }
  return { grid: _vgInstance, store: _vgDataStore };
}

/**
 * Display search results using virtual scroll (replacement for displayResults).
 * @returns true: handled by virtual scroll, false: disabled, use normal path
 */
export function vsDisplayResults(results: ResultRecord[]): boolean {
  // Reset batch cache for new search results
  resetThumbnailBatch();

  // Don't use virtual scroll in group mode
  if (!isVirtualScrollEnabled() || _isGroupedMode()) {
    // Stop virtual scroll if running
    if (_vgInstance) vsDeactivate();
    return false;
  }

  const inst = ensureInstance();
  if (!inst) return false;

  inst.store.clear();
  // Immediately set new data after store.clear() so scroll handler won't render empty data
  // (no gap between clear and setAll)
  if (results && results.length > 0) {
    inst.store.setAll(results);
  }

  if (!inst.grid['active']) {
    inst.grid.activate();
  } else {
    // Reset scroll position to display from the first row
    // (if the user scrolled partway in the previous search,
    //  leftover scroll position causes visible range to be offset after refresh)
    const container = document.getElementById('results');
    if (container) {
      window.scrollTo(0, 0);
    }
    inst.grid.refresh();
  }
  return true;
}

/**
 * Append paged results via virtual scroll (replacement for appendResults).
 * @returns true: handled by virtual scroll, false: disabled, use normal path
 */
export function vsAppendResults(results: ResultRecord[]): boolean {
  if (!isVirtualScrollEnabled() || _isGroupedMode() || !_vgInstance || !_vgDataStore) return false;

  _vgDataStore.append(results);
  _vgInstance.refresh();
  return true;
}

/**
 * Deactivate virtual scroll and clear the DOM.
 * Called when switching to group mode or returning to normal rendering.
 */
export function vsDeactivate(): void {
  if (_vgInstance) {
    _vgInstance.deactivate();
  }
  _vgDataStore = null;
  _vgInstance = null;
}

/** Recalculate layout on grid size change */
export function vsRefreshLayout(): void {
  if (_vgInstance && _vgInstance['active']) {
    _vgInstance.refresh();
  }
}

/** Return all IDs from the current VirtualGridDataStore */
export function vsGetAllIds(): number[] {
  return _vgDataStore?.getAllIds() ?? [];
}

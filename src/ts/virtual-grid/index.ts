/**
 * virtual-grid/index.ts
 *
 * Virtual scroll — efficient rendering for large numbers of cards.
 * Enabled via localStorage `virtualScroll=1`.
 */

export { VirtualGrid } from './virtual-grid-core';
export { VirtualGridDataStore } from './virtual-grid-data';
export { isVirtualScrollEnabled, enableVirtualScroll, disableVirtualScroll } from './virtual-grid-core';

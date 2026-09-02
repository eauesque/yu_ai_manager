/**
 * virtual-grid/virtual-grid-core.ts
 *
 * VirtualGrid class — scroll/resize observation, visible range calculation, DOM updates.
 * Coexists with CSS Grid layout using a padding model.
 */

import { VirtualGridDataStore } from './virtual-grid-data';
import { computeLayout, totalRows, type GridLayout } from './virtual-grid-layout';
import { renderCards } from './virtual-grid-render';
import { queueThumbnails } from '../search-results/results/thumbnail-batch';

/** Feature flag key */
const FEATURE_FLAG_KEY = 'virtualScroll';

/** Base off-screen buffer rows */
const BUFFER_ROWS = 8;

/** Extra buffer rows in the scroll direction */
const DIRECTION_EXTRA = 6;

/** Rows to prefetch thumbnails beyond the current render window */
const PREFETCH_ROWS = 2;

/** Check if virtual scroll is enabled (enabled by default) */
export function isVirtualScrollEnabled(): boolean {
  try {
    return localStorage.getItem(FEATURE_FLAG_KEY) !== '0';
  } catch {
    return true;
  }
}

/** Enable virtual scroll */
export function enableVirtualScroll(): void {
  try {
    localStorage.setItem(FEATURE_FLAG_KEY, '1');
  } catch {
    // localStorage unavailable
  }
}

/** Disable virtual scroll */
export function disableVirtualScroll(): void {
  try {
    localStorage.removeItem(FEATURE_FLAG_KEY);
  } catch {
    // localStorage unavailable
  }
}

/**
 * Virtual scroll controller class.
 *
 * Adjusts scroll position via padding-top/padding-bottom on top of CSS Grid
 * (#results.results-grid) and only places visible-range cards in the DOM.
 */
export class VirtualGrid {
  private container: HTMLElement;
  private dataStore: VirtualGridDataStore;
  private layout: GridLayout | null = null;
  private scrollParent: HTMLElement | Window;
  private lastStartRow = -1;
  private lastEndRow = -1;
  private rafId: number | null = null;
  private resizeRafId: number | null = null;
  private resizeObserver: ResizeObserver | null = null;
  private active = false;
  /** Previous scroll position (for direction detection) */
  private prevScrollTop = 0;
  /** Scroll direction: 1=down, -1=up, 0=unknown */
  private scrollDir: -1 | 0 | 1 = 0;

  constructor(container: HTMLElement, dataStore: VirtualGridDataStore) {
    this.container = container;
    this.dataStore = dataStore;
    this.scrollParent = this.findScrollParent();
  }

  /** Start virtual scrolling */
  activate(): void {
    if (this.active) return;
    this.active = true;
    this.container.classList.add('vs-active');

    this.layout = computeLayout(this.container);
    this.bindEvents();
    this.update();
  }

  /** Stop virtual scrolling */
  deactivate(): void {
    if (!this.active) return;
    this.active = false;
    this.container.classList.remove('vs-active');
    this.container.style.paddingTop = '';
    this.container.style.paddingBottom = '';
    this.unbindEvents();
    this.lastStartRow = -1;
    this.lastEndRow = -1;
  }

  /** Redraw on data change */
  refresh(): void {
    if (!this.active) return;
    this.layout = computeLayout(this.container);
    this.lastStartRow = -1;
    this.lastEndRow = -1;
    this.update();
  }

  /** Scroll to a specific item */
  scrollToIndex(index: number): void {
    if (!this.active || !this.layout) return;
    const row = Math.floor(index / this.layout.columns);
    const scrollTop = row * this.layout.rowHeight;
    if (this.scrollParent instanceof Window) {
      this.scrollParent.scrollTo({ top: scrollTop, behavior: 'smooth' });
    } else {
      this.scrollParent.scrollTo({ top: scrollTop, behavior: 'smooth' });
    }
  }

  /** Get the current visible range */
  getVisibleRange(): { start: number; end: number } {
    const cols = this.layout?.columns ?? 1;
    return {
      start: this.lastStartRow * cols,
      end: this.lastEndRow * cols,
    };
  }

  private findScrollParent(): HTMLElement | Window {
    let el: HTMLElement | null = this.container.parentElement;
    while (el) {
      const style = getComputedStyle(el);
      if (style.overflow === 'auto' || style.overflow === 'scroll' ||
          style.overflowY === 'auto' || style.overflowY === 'scroll') {
        return el;
      }
      el = el.parentElement;
    }
    return window;
  }

  private getScrollTop(): number {
    if (this.scrollParent instanceof Window) {
      return window.scrollY || document.documentElement.scrollTop;
    }
    return this.scrollParent.scrollTop;
  }

  private getViewportHeight(): number {
    if (this.scrollParent instanceof Window) {
      return window.innerHeight;
    }
    return this.scrollParent.clientHeight;
  }

  private update(): void {
    if (!this.active || !this.layout) return;

    const { columns, rowHeight } = this.layout;
    const itemCount = this.dataStore.length;
    const rows = totalRows(itemCount, columns);

    if (rows === 0) {
      this.container.style.paddingTop = '0px';
      this.container.style.paddingBottom = '0px';
      this.container.innerHTML = '';
      return;
    }

    const scrollTop = Math.max(0, this.getScrollTop() - this.container.offsetTop);
    const viewHeight = this.getViewportHeight();

    // Detect scroll direction
    const delta = scrollTop - this.prevScrollTop;
    if (Math.abs(delta) > 2) {
      this.scrollDir = delta > 0 ? 1 : -1;
    }
    this.prevScrollTop = scrollTop;

    // Calculate visible row range (extra buffer in scroll direction)
    const firstVisibleRow = Math.floor(scrollTop / rowHeight);
    const lastVisibleRow = Math.ceil((scrollTop + viewHeight) / rowHeight);

    const bufferBefore = BUFFER_ROWS + (this.scrollDir === -1 ? DIRECTION_EXTRA : 0);
    const bufferAfter = BUFFER_ROWS + (this.scrollDir === 1 ? DIRECTION_EXTRA : 0);
    const startRow = Math.max(0, firstVisibleRow - bufferBefore);
    const endRow = Math.min(rows, lastVisibleRow + bufferAfter);

    // Skip if unchanged
    if (startRow === this.lastStartRow && endRow === this.lastEndRow) return;

    this.lastStartRow = startRow;
    this.lastEndRow = endRow;

    // Get data range
    const startIdx = startRow * columns;
    const endIdx = Math.min(endRow * columns, itemCount);
    const items = this.dataStore.slice(startIdx, endIdx);

    // Maintain scroll position via padding
    const paddingTop = startRow * rowHeight;
    const paddingBottom = Math.max(0, (rows - endRow) * rowHeight);

    this.container.style.paddingTop = `${paddingTop}px`;
    this.container.style.paddingBottom = `${paddingBottom}px`;

    // Render cards
    renderCards(this.container, items, startIdx);

    // Prefetch thumbnails beyond current render window in scroll direction.
    // scrollDir initial value is 0 (unknown): treated as "down" — intentional,
    // as first render is almost always at the top of a downward-scrolling list.
    if (this.scrollDir >= 0) {
      // Scrolling down (or initial render): prefetch rows beyond endRow
      const prefetchStart = endIdx;
      const prefetchEnd = Math.min(endRow * columns + PREFETCH_ROWS * columns, itemCount);
      if (prefetchStart < prefetchEnd) {
        const prefetchIds = this.dataStore.slice(prefetchStart, prefetchEnd)
          .map((r) => r.id as number)
          .filter((id) => Number.isFinite(id) && id > 0);
        if (prefetchIds.length > 0) queueThumbnails(prefetchIds);
      }
    } else {
      // Scrolling up: prefetch rows beyond startRow
      const prefetchStart = Math.max(0, startRow * columns - PREFETCH_ROWS * columns);
      const prefetchEnd = startIdx;
      if (prefetchStart < prefetchEnd) {
        const prefetchIds = this.dataStore.slice(prefetchStart, prefetchEnd)
          .map((r) => r.id as number)
          .filter((id) => Number.isFinite(id) && id > 0);
        if (prefetchIds.length > 0) queueThumbnails(prefetchIds);
      }
    }
  }

  private onScroll = (): void => {
    if (this.rafId !== null) return;
    this.rafId = requestAnimationFrame(() => {
      this.rafId = null;
      this.update();
    });
  };

  private onResize = (): void => {
    if (!this.active) return;
    // Debounce via rAF: even if ResizeObserver fires frequently during slider operation,
    // only re-layout + re-render once per frame
    if (this.resizeRafId !== null) cancelAnimationFrame(this.resizeRafId);
    this.resizeRafId = requestAnimationFrame(() => {
      this.resizeRafId = null;
      if (!this.active) return;
      this.layout = computeLayout(this.container);
      this.lastStartRow = -1;
      this.lastEndRow = -1;
      this.update();
    });
  };

  private bindEvents(): void {
    const target = this.scrollParent === window ? window : this.scrollParent;
    target.addEventListener('scroll', this.onScroll, { passive: true });

    this.resizeObserver = new ResizeObserver(this.onResize);
    this.resizeObserver.observe(this.container);
  }

  private unbindEvents(): void {
    const target = this.scrollParent === window ? window : this.scrollParent;
    target.removeEventListener('scroll', this.onScroll);

    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
      this.resizeObserver = null;
    }

    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    if (this.resizeRafId !== null) {
      cancelAnimationFrame(this.resizeRafId);
      this.resizeRafId = null;
    }
  }
}

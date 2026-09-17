/**
 * virtual-grid/virtual-grid-layout.ts
 *
 * Column count and row height calculation. References CSS Grid's --grid-min-size.
 */

/** Layout calculation result */
export interface GridLayout {
  /** Number of columns */
  columns: number;
  /** Row height (px) */
  rowHeight: number;
  /** Card width (px) */
  cardWidth: number;
}

/** Default grid minimum size (CSS variable fallback) */
const DEFAULT_MIN_SIZE = 300;

/** Default estimated height of card footer (info + prompt) */
const DEFAULT_EXTRA_HEIGHT = 80;

/** Grid gap */
const GRID_GAP = 16;

/**
 * Calculate column count and row height from the current container size.
 */
export function computeLayout(container: HTMLElement): GridLayout {
  const style = getComputedStyle(container);
  const minSizeStr = style.getPropertyValue('--grid-min-size').trim();
  const minSize = parseInt(minSizeStr, 10) || DEFAULT_MIN_SIZE;

  const containerWidth = container.clientWidth;
  const columns = Math.max(1, Math.floor((containerWidth + GRID_GAP) / (minSize + GRID_GAP)));
  const cardWidth = (containerWidth - (columns - 1) * GRID_GAP) / columns;

  // Measure actual card height (if present in DOM)
  // Exclude skeleton cards as they differ in size from real cards
  const firstCard = container.querySelector<HTMLElement>('.result-card:not(.skeleton-card)');
  const extraHeight = firstCard
    ? firstCard.offsetHeight - cardWidth  // measured value
    : DEFAULT_EXTRA_HEIGHT;
  const rowHeight = cardWidth + Math.max(extraHeight, 0) + GRID_GAP;

  return { columns, rowHeight, cardWidth };
}

/**
 * Calculate the first item index from a row index.
 */
export function rowToItemIndex(row: number, columns: number): number {
  return row * columns;
}

/**
 * Calculate the row index from an item index.
 */
export function itemToRow(itemIndex: number, columns: number): number {
  return Math.floor(itemIndex / columns);
}

/**
 * Calculate the total number of rows.
 */
export function totalRows(itemCount: number, columns: number): number {
  return Math.ceil(itemCount / columns);
}

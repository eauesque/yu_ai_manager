/**
 * NovelAI V4 character position grid overlay.
 * Renders a 5x5 grid on top of the image with character position markers,
 * similar to the NAI official UI.
 */

export interface GridCharacter {
  index: number;
  positions: Array<{ x: number; y: number }>;
}

const GRID_CLASS = 'char-position-grid';
const GRID_SIZE = 5;

/** ResizeObserver instances keyed by wrapper, for cleanup on removeCharacterGrid. */
const _observers = new WeakMap<HTMLElement, ResizeObserver>();

function _repositionGrid(grid: HTMLElement, img: HTMLElement): void {
  if (grid.style.display === 'none') return;
  grid.style.top = img.offsetTop + 'px';
  grid.style.left = img.offsetLeft + 'px';
  grid.style.width = img.clientWidth + 'px';
  grid.style.height = img.clientHeight + 'px';
}

/** Accent colours for character markers (up to 6 characters). */
export const MARKER_COLORS = [
  '#4a90d9', // blue
  '#e06060', // red
  '#50b860', // green
  '#d0a040', // gold
  '#9b59b6', // purple
  '#e67e22', // orange
];

/**
 * Render a 5x5 character position grid overlay on top of an image element.
 * The wrapper must have `position: relative`.
 */
export function renderCharacterGrid(
  wrapper: HTMLElement,
  imgEl: HTMLElement,
  characters: GridCharacter[],
): void {
  removeCharacterGrid(wrapper);

  const w = imgEl.clientWidth;
  const h = imgEl.clientHeight;
  if (!w || !h) return;

  // Build cell-to-characters map
  const cellMap = new Map<string, Array<{ index: number; color: string }>>();
  for (const char of characters) {
    const color = MARKER_COLORS[(char.index - 1) % MARKER_COLORS.length];
    for (const pos of char.positions) {
      const col = Math.min(GRID_SIZE - 1, Math.floor(pos.x * GRID_SIZE));
      const row = Math.min(GRID_SIZE - 1, Math.floor(pos.y * GRID_SIZE));
      const key = `${row}-${col}`;
      if (!cellMap.has(key)) cellMap.set(key, []);
      cellMap.get(key)!.push({ index: char.index, color });
    }
  }

  // Create grid container
  const grid = document.createElement('div');
  grid.className = GRID_CLASS;
  grid.style.cssText = `position:absolute;top:${imgEl.offsetTop}px;left:${imgEl.offsetLeft}px;width:${w}px;height:${h}px;pointer-events:none;z-index:2;display:grid;grid-template-columns:repeat(${GRID_SIZE},1fr);grid-template-rows:repeat(${GRID_SIZE},1fr);border-radius:4px;overflow:hidden;`;

  for (let r = 0; r < GRID_SIZE; r++) {
    for (let c = 0; c < GRID_SIZE; c++) {
      const cell = document.createElement('div');
      cell.className = 'char-grid-cell';

      const key = `${r}-${c}`;
      const markers = cellMap.get(key);
      if (markers) {
        for (const m of markers) {
          const marker = document.createElement('span');
          marker.className = 'char-grid-marker';
          marker.textContent = String(m.index);
          marker.style.setProperty('--marker-color', m.color);
          cell.appendChild(marker);
        }
      }
      grid.appendChild(cell);
    }
  }

  wrapper.appendChild(grid);

  // Observe the image for size changes (zoom / fit-mode) and reposition the
  // grid overlay whenever it is visible.
  const prev = _observers.get(wrapper);
  if (prev) prev.disconnect();
  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => _repositionGrid(grid, imgEl));
    ro.observe(imgEl);
    _observers.set(wrapper, ro);
  }
}

/** Remove grid overlay from wrapper. */
export function removeCharacterGrid(wrapper: HTMLElement): void {
  const ro = _observers.get(wrapper);
  if (ro) { ro.disconnect(); _observers.delete(wrapper); }
  const existing = wrapper.querySelectorAll('.' + GRID_CLASS);
  existing.forEach((el) => el.remove());
}

/**
 * Toggle grid visibility. Returns the new visible state (true = now visible).
 * Re-measures image dimensions on show to handle zoom / fit-mode changes.
 */
export function toggleCharacterGrid(wrapper: HTMLElement): boolean {
  const grid = wrapper.querySelector('.' + GRID_CLASS) as HTMLElement | null;
  if (!grid) return false;
  const isHidden = grid.style.display === 'none';
  if (isHidden) {
    const img = wrapper.querySelector('img') as HTMLImageElement | null;
    if (img && img.clientWidth && img.clientHeight) {
      grid.style.top = img.offsetTop + 'px';
      grid.style.left = img.offsetLeft + 'px';
      grid.style.width = img.clientWidth + 'px';
      grid.style.height = img.clientHeight + 'px';
    }
    grid.style.display = 'grid';
  } else {
    grid.style.display = 'none';
  }
  return isHidden;
}

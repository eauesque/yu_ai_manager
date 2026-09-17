/**
 * NovelAI character position overlay.
 *
 * Draws each character's position on top of the image. NovelAI V4 picked
 * positions from a 5x5 grid; V5 replaced that with free coordinates in [0,1].
 * The metadata shape is identical either way, so **the coordinate values alone
 * cannot tell the two apart** -- the only discriminator is `use_coords`.
 *
 * Because of that this renderer never branches on model generation. It draws
 * one continuous layer and keeps the grid as an optional reference overlay.
 * Snapping a position to the nearest cell to "detect" V4 would be an
 * unfalsifiable heuristic that misclassifies by construction.
 */

export interface GridCharacter {
  index: number;
  positions: Array<{ x: number; y: number }>;
}

/**
 * Whether the image's coordinates are in force.
 *
 * `null` means the metadata did not say, which is not the same as `false`.
 * Folding the two together makes a V5 image claim it uses no coordinates.
 */
export type CoordsMode = boolean | null;

const LAYER_CLASS = 'char-position-grid';
const GRID_SIZE = 5;

/** ResizeObserver instances keyed by wrapper, for cleanup on removeCharacterGrid. */
const _observers = new WeakMap<HTMLElement, ResizeObserver>();

function _repositionLayer(layer: HTMLElement, img: HTMLElement): void {
  if (layer.style.display === 'none') return;
  layer.style.top = img.offsetTop + 'px';
  layer.style.left = img.offsetLeft + 'px';
  layer.style.width = img.clientWidth + 'px';
  layer.style.height = img.clientHeight + 'px';
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

/** Clamp for drawing only. The extracted value is kept verbatim. */
function clamp01(v: number): number {
  if (!Number.isFinite(v)) return 0.5;
  return Math.min(1, Math.max(0, v));
}

/**
 * Spread markers that land on the same spot so each stays grabbable.
 *
 * Without this, characters left at the default 0.5,0.5 stack into one dot and
 * only the topmost can be read.
 */
function fanOut(index: number, total: number): { dx: number; dy: number } {
  if (total < 2) return { dx: 0, dy: 0 };
  const angle = (index / total) * Math.PI * 2;
  const r = 10;
  return { dx: Math.cos(angle) * r, dy: Math.sin(angle) * r };
}

function buildGridLines(): HTMLElement {
  const grid = document.createElement('div');
  grid.className = 'char-grid-reference';
  grid.style.cssText =
    `position:absolute;inset:0;display:grid;` +
    `grid-template-columns:repeat(${GRID_SIZE},1fr);` +
    `grid-template-rows:repeat(${GRID_SIZE},1fr);pointer-events:none;`;
  for (let i = 0; i < GRID_SIZE * GRID_SIZE; i++) {
    const cell = document.createElement('div');
    cell.className = 'char-grid-cell';
    grid.appendChild(cell);
  }
  return grid;
}

/**
 * Render the character position overlay on top of an image element.
 * The wrapper must have `position: relative`.
 *
 * @param coordsMode `true` draws markers, `false` draws none (the image uses
 *   character order only), `null` draws them with an "unverified" badge.
 * @param showGrid draws the 5x5 reference lines. They are a reading aid, never
 *   a claim about which mode the image used.
 */
export function renderCharacterGrid(
  wrapper: HTMLElement,
  imgEl: HTMLElement,
  characters: GridCharacter[],
  coordsMode: CoordsMode = true,
  showGrid = false,
): void {
  removeCharacterGrid(wrapper);

  const w = imgEl.clientWidth;
  const h = imgEl.clientHeight;
  if (!w || !h) return;

  const layer = document.createElement('div');
  layer.className = LAYER_CLASS;
  layer.style.cssText =
    `position:absolute;top:${imgEl.offsetTop}px;left:${imgEl.offsetLeft}px;` +
    `width:${w}px;height:${h}px;pointer-events:none;z-index:2;` +
    `border-radius:4px;overflow:hidden;`;

  if (showGrid) layer.appendChild(buildGridLines());

  if (coordsMode !== false) {
    // Count how many characters share each spot, so overlapping ones fan out.
    const bucket = new Map<string, number>();
    for (const char of characters) {
      for (const pos of char.positions) {
        const key = `${clamp01(pos.x).toFixed(3)}:${clamp01(pos.y).toFixed(3)}`;
        bucket.set(key, (bucket.get(key) ?? 0) + 1);
      }
    }
    const seen = new Map<string, number>();

    for (const char of characters) {
      const color = MARKER_COLORS[(char.index - 1) % MARKER_COLORS.length];
      for (const pos of char.positions) {
        const x = clamp01(pos.x);
        const y = clamp01(pos.y);
        const key = `${x.toFixed(3)}:${y.toFixed(3)}`;
        const total = bucket.get(key) ?? 1;
        const nth = seen.get(key) ?? 0;
        seen.set(key, nth + 1);
        const { dx, dy } = fanOut(nth, total);

        const marker = document.createElement('span');
        marker.className = 'char-grid-marker char-position-marker';
        marker.textContent = String(char.index);
        marker.style.setProperty('--marker-color', color);
        // `x * 100` is float-noisy (0.528 -> 52.800000000000004); trim to a
        // precision far finer than a pixel so the emitted CSS stays readable.
        const leftPct = Number((x * 100).toFixed(4));
        const topPct = Number((y * 100).toFixed(4));
        marker.style.cssText +=
          `position:absolute;left:${leftPct}%;top:${topPct}%;` +
          `transform:translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px));`;
        marker.title = `${x.toFixed(3)}, ${y.toFixed(3)}`;
        layer.appendChild(marker);
      }
    }
  }

  wrapper.appendChild(layer);

  // Three states, three messages. `false` and `null` must not read alike: one
  // says "this image used character order", the other says "we do not know".
  if (coordsMode !== true) {
    const note = document.createElement('div');
    note.className = 'char-position-note';
    note.dataset.mode = coordsMode === false ? 'order' : 'unknown';
    const tr = (window as unknown as { tr?: (k: string, f: string) => string }).tr;
    const key = coordsMode === false
      ? 'novelai.coords_unused'
      : 'novelai.coords_unknown';
    const fallback = coordsMode === false
      ? 'Order-based (coordinates unused)'
      : 'Coordinate use unconfirmed';
    note.textContent = tr ? tr(key, fallback) : fallback;
    layer.appendChild(note);
  }

  // Observe the image for size changes (zoom / fit-mode) and reposition the
  // overlay whenever it is visible.
  const prev = _observers.get(wrapper);
  if (prev) prev.disconnect();
  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => _repositionLayer(layer, imgEl));
    ro.observe(imgEl);
    _observers.set(wrapper, ro);
  }
}

/** Remove the overlay from wrapper. */
export function removeCharacterGrid(wrapper: HTMLElement): void {
  const ro = _observers.get(wrapper);
  if (ro) { ro.disconnect(); _observers.delete(wrapper); }
  const existing = wrapper.querySelectorAll('.' + LAYER_CLASS);
  existing.forEach((el) => el.remove());
}

/**
 * Toggle overlay visibility. Returns the new visible state (true = now visible).
 * Re-measures image dimensions on show to handle zoom / fit-mode changes.
 */
export function toggleCharacterGrid(wrapper: HTMLElement): boolean {
  const layer = wrapper.querySelector('.' + LAYER_CLASS) as HTMLElement | null;
  if (!layer) return false;
  const isHidden = layer.style.display === 'none';
  if (isHidden) {
    const img = wrapper.querySelector('img');
    if (img && img.clientWidth && img.clientHeight) {
      layer.style.top = img.offsetTop + 'px';
      layer.style.left = img.offsetLeft + 'px';
      layer.style.width = img.clientWidth + 'px';
      layer.style.height = img.clientHeight + 'px';
    }
    layer.style.display = 'block';
  } else {
    layer.style.display = 'none';
  }
  return isHidden;
}

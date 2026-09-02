/**
 * Bridge result-panel history store.
 *
 * Solves two memory problems with the previous implementation:
 *   1. Each thumb kept the full base64 PNG/WebP in DOM (img.src=data:...).
 *      With 50+ entries this easily reaches hundreds of MB.
 *   2. ``HistoryEntry.base64`` was retained even after the entry scrolled
 *      out of view, doubling the cost.
 *
 * Strategy
 *   - The newest ``KEEP_FULL`` entries keep their full-resolution data so
 *     the user can re-open the original from history without quality loss.
 *   - Older entries get canvas-downsampled to a 256px JPEG thumbnail
 *     (~10-30 KB each, vs. 1-3 MB originals). The full base64 is dropped.
 *   - Beyond ``MAX_HISTORY`` total entries the oldest is removed entirely.
 */

import type { HistoryEntry } from './result-panel-view';

export const KEEP_FULL = 5;
export const MAX_HISTORY = 30;
const THUMB_SIZE = 256;
const THUMB_QUALITY = 0.75;

/**
 * Render *src* to a JPEG data: URL no larger than ``maxSize`` on its
 * longest edge. Used to shrink stale history entries.
 */
export function downsampleToThumb(src: string, maxSize = THUMB_SIZE, quality = THUMB_QUALITY): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const w = img.naturalWidth;
      const h = img.naturalHeight;
      if (!w || !h) {
        reject(new Error('zero-sized image'));
        return;
      }
      const scale = Math.min(1, maxSize / Math.max(w, h));
      const cw = Math.max(1, Math.round(w * scale));
      const ch = Math.max(1, Math.round(h * scale));
      const canvas = document.createElement('canvas');
      canvas.width = cw;
      canvas.height = ch;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        reject(new Error('no 2d context'));
        return;
      }
      ctx.drawImage(img, 0, 0, cw, ch);
      try {
        resolve(canvas.toDataURL('image/jpeg', quality));
      } catch (e) {
        reject(e as Error);
      }
    };
    img.onerror = () => reject(new Error('image decode failed'));
    img.src = src;
  });
}

export interface HistoryStoreEntry extends HistoryEntry {
  /** True once full data has been replaced with a thumb. */
  downsampled?: boolean;
  /** DOM thumb element holding this entry, for in-place src swaps. */
  thumbEl?: HTMLElement;
}

export interface HistoryStore {
  readonly entries: HistoryStoreEntry[];
  add(entry: HistoryEntry): HistoryStoreEntry;
  clear(): void;
  /** Called when an entry is dropped from the store entirely. */
  onEvict?: (entry: HistoryStoreEntry) => void;
  /** Called when an entry has been downsampled — DOM should re-bind its src. */
  onDownsample?: (entry: HistoryStoreEntry) => void;
}

export function createHistoryStore(): HistoryStore {
  const entries: HistoryStoreEntry[] = [];
  const store: HistoryStore = {
    entries,
    add(entry) {
      const e = entry as HistoryStoreEntry;
      entries.unshift(e);
      // Trim oldest beyond cap.
      while (entries.length > MAX_HISTORY) {
        const removed = entries.pop();
        if (removed && store.onEvict) store.onEvict(removed);
      }
      // Downsample any entry that has aged past KEEP_FULL.
      // Index KEEP_FULL is the (KEEP_FULL+1)th newest — exactly the one that
      // just fell out of the "keep full" window when we unshifted.
      const target = entries[KEEP_FULL];
      if (target && !target.downsampled) {
        // Mark eagerly so two near-simultaneous adds don't both schedule.
        target.downsampled = true;
        downsampleToThumb(target.src).then((thumb) => {
          target.src = thumb;
          target.base64 = ''; // Free original
          if (store.onDownsample) store.onDownsample(target);
        }).catch(() => {
          // Roll back so a future add can retry.
          target.downsampled = false;
        });
      }
      return e;
    },
    clear() {
      entries.length = 0;
    },
  };
  return store;
}

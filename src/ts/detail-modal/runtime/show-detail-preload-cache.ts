/**
 * Neighboring image preload cache.
 *
 * Preloads preview images (1200px) so they can be displayed instantly
 * during modal navigation.
 * Preloading previews instead of full-resolution images saves bandwidth
 * and speeds up the second stage of progressive loading.
 */

import { getAppApi } from '../../shared/browser-apis';

const MAX_PRELOAD = 8;
const preloads: HTMLImageElement[] = [];

export function preloadImageById(id: number): void {
  if (typeof id !== 'number' || !Number.isFinite(id)) return;
  const img = new Image();
  img.decoding = 'async';
  // Preload the preview (1200px) — faster and more bandwidth-efficient than full resolution
  img.src = getAppApi().apiUrl(`/api/preview/${id}`);
  preloads.push(img);
  if (preloads.length > MAX_PRELOAD) preloads.shift();
}

export function clearPreloadCache(): void {
  while (preloads.length) {
    const img = preloads.pop();
    if (!img) continue;
    try { img.src = ''; } catch (_) { /* ignore */ }
  }
}

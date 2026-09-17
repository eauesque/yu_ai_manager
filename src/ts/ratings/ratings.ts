/**
 * ratings/ratings.ts — Rating API calls + card/modal UI integration.
 */

import { buildCardRatingHtml, createModalRatingWidget, updateModalRatingWidget } from './rating-widget';
import { getAppApi } from '../shared/browser-apis';

// Cache of ratings for visible cards
const _ratingsCache = new Map<number, number>();

/** Set rating for a file (0 = clear). Updates card and modal UI. */
export async function setRating(fileId: number, rating: number): Promise<void> {
  try {
    const response = await getAppApi().apiFetch('/api/ratings/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: fileId, rating }),
    });
    if (!response.ok) return;

    if (rating === 0) {
      _ratingsCache.delete(fileId);
    } else {
      _ratingsCache.set(fileId, rating);
    }

    // Update modal widget
    updateModalRatingWidget(fileId, rating);

    // Update card rating display
    _updateCardRating(fileId, rating);
  } catch (e) {
    console.error('setRating failed:', e);
  }
}

/** Fetch ratings for a batch of file IDs and update card displays. */
export async function getRatingsBatch(fileIds: number[]): Promise<Record<number, number>> {
  if (!fileIds || fileIds.length === 0) return {};
  try {
    const response = await getAppApi().apiFetch('/api/ratings/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_ids: fileIds }),
    });
    if (!response.ok) return {};
    const data = await response.json();
    const ratings: Record<string, number> = data.ratings || {};

    // Update cache and cards
    for (const [idStr, val] of Object.entries(ratings)) {
      const id = parseInt(idStr, 10);
      _ratingsCache.set(id, val);
      _updateCardRating(id, val);
    }
    return ratings;
  } catch (e) {
    console.error('getRatingsBatch failed:', e);
    return {};
  }
}

/** Get a single file's rating (from cache or API). */
export async function getRating(fileId: number): Promise<number> {
  if (_ratingsCache.has(fileId)) return _ratingsCache.get(fileId)!;
  try {
    const response = await getAppApi().apiFetch('/api/ratings/get?file_id=' + fileId);
    if (!response.ok) return 0;
    const data = await response.json();
    const rating = data.rating || 0;
    if (rating > 0) _ratingsCache.set(fileId, rating);
    return rating;
  } catch {
    return 0;
  }
}

/** Create an interactive rating widget for the detail modal. */
export function createRatingWidget(fileId: number): HTMLElement {
  const rating = _ratingsCache.get(fileId) || 0;
  return createModalRatingWidget(fileId, rating);
}

/** Build inline card rating HTML. */
export function getCardRatingHtml(fileId: number): string {
  const rating = _ratingsCache.get(fileId) || 0;
  return buildCardRatingHtml(fileId, rating);
}

function _updateCardRating(fileId: number, rating: number): void {
  const card = document.querySelector<HTMLElement>('.result-card[data-id="' + fileId + '"]');
  if (!card) return;

  let ratingEl = card.querySelector<HTMLElement>('.card-rating');
  if (rating <= 0) {
    if (ratingEl) ratingEl.remove();
    return;
  }

  const newHtml = buildCardRatingHtml(fileId, rating);
  if (!ratingEl) {
    // Insert after the fav button
    const favBtn = card.querySelector('.card-fav-btn');
    if (favBtn) {
      favBtn.insertAdjacentHTML('afterend', newHtml);
    }
  } else {
    ratingEl.outerHTML = newHtml;
  }
}

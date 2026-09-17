/**
 * virtual-grid/virtual-grid-render.ts
 *
 * Differential card rendering. Reuses existing cards
 * to avoid destroying/recreating unchanged cards (especially img elements).
 */

import {
  buildResultCardInnerHtml,
  applyResultCardData,
  bindResultCardInteractions,
} from '../search-results/results/render-card';
import { setupResultCardA11y } from '../search-results/results/a11y';
import { queueThumbnails, getCachedDataUrl } from '../search-results/results/thumbnail-batch';
import { getAppApi, getSearchResultsApi } from '../shared/browser-apis';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ResultRecord = Record<string, any>;

/** 1x1 transparent GIF (prevents immediate native thumbnail fetch in VirtualGrid path) */
const TRANSPARENT_PIXEL = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==';

function prepareVirtualGridThumb(card: HTMLElement): void {
  const img = card.querySelector<HTMLImageElement>('img.result-image');
  if (!img || img.dataset.vgPrepared === '1') return;
  const fileId = parseInt(card.dataset.id || '0', 10);
  const cached = getCachedDataUrl(fileId);
  if (cached) {
    // Cache hit: display real thumbnail immediately, no batch wait
    img.src = cached;
    img.dataset.loaded = '1';
    img.dataset.vgPrepared = '1'; // Guard against re-invocation (symmetric with non-cached path)
  } else {
    // Cache miss: show placeholder until batch API responds
    img.src = TRANSPARENT_PIXEL;
    img.dataset.vgPrepared = '1';
  }
}

/**
 * Differentially render cards for the given range into the DOM.
 *
 * Compares IDs of existing cards with new data:
 * matching cards are kept as-is (preventing img load interruption),
 * only obsolete cards are removed and only new cards are added.
 *
 * @param container - Results container (#results)
 * @param items - Array of items to display
 * @param startIndex - Starting index within the data array (for --i)
 */
export function renderCards(
  container: HTMLElement,
  items: ResultRecord[],
  startIndex: number,
): void {
  const searchResultsApi = getSearchResultsApi();
  // Remove skeleton cards (leftover from loading state before VirtualGrid activates)
  container.querySelectorAll<HTMLElement>('.skeleton-card').forEach(el => el.remove());

  // Build ID map of existing cards
  const existingCards = new Map<string, HTMLElement>();
  const existingChildren = container.querySelectorAll<HTMLElement>('.result-card');
  for (const card of existingChildren) {
    const id = card.dataset.id;
    if (id) existingCards.set(id, card);
  }

  // Set of new item IDs
  const newIds = new Set(items.map((r) => String(r.id)));

  // Remove obsolete cards
  for (const [id, card] of existingCards) {
    if (!newIds.has(id)) {
      card.remove();
      existingCards.delete(id);
    }
  }

  // Place new cards in correct order
  let newCardIds: number[] = [];
  const orderedCards: HTMLElement[] = [];

  for (let i = 0; i < items.length; i++) {
    const result = items[i];
    const id = String(result.id);
    let card = existingCards.get(id);

    if (card) {
      // Reuse existing card (only update --i)
      card.style.setProperty('--i', String(startIndex + i));
    } else {
      // Create new card
      card = document.createElement('div');
      card.className = 'result-card';
      card.style.setProperty('--i', String(startIndex + i));
      card.innerHTML = buildResultCardInnerHtml(result);
      applyResultCardData(card, result);
      bindResultCardInteractions(card);
      prepareVirtualGridThumb(card);
      newCardIds.push(result.id as number);
    }
    orderedCards.push(card);
  }

  // Rebuild DOM only if order has changed
  const currentChildren = Array.from(
    container.querySelectorAll<HTMLElement>('.result-card'),
  );
  const needsReorder =
    currentChildren.length !== orderedCards.length ||
    currentChildren.some((el, idx) => el !== orderedCards[idx]);

  if (needsReorder) {
    // In-place reorder via insertBefore — the container is never emptied,
    // so there is no intermediate blank-container paint even on fast wheel scroll.
    // replaceChildren() detaches-then-reattaches nodes internally and can produce
    // a blank frame in Chrome; insertBefore moves each node directly to its slot.
    for (let i = 0; i < orderedCards.length; i++) {
      const desired = orderedCards[i];
      const actual = container.children[i] as HTMLElement | undefined;
      if (actual !== desired) {
        container.insertBefore(desired, actual ?? null);
      }
    }
  }

  setupResultCardA11y();

  // Sync favorite status (new cards only)
  if (newCardIds.length > 0) {
    searchResultsApi.checkFavorites(newCardIds);
  }

  getAppApi().updateKeyboardGuideVisibility();

  // Batch thumbnails: enqueue visible range file_ids
  const visibleIds = orderedCards
    .map((card) => {
      const img = card.querySelector<HTMLImageElement>('img.result-image');
      if (!img || img.dataset.loaded === '1') return null;
      const id = parseInt(card.dataset.id || '0', 10);
      return Number.isFinite(id) && id > 0 ? id : null;
    })
    .filter((id): id is number => typeof id === 'number');
  if (visibleIds.length > 0) {
    queueThumbnails(visibleIds, { priority: true });
  }
}

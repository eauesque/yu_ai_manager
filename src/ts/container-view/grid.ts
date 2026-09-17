/**
 * container-view/grid.ts — Render thumbnail grid for container members.
 * Reuses `.results-grid.compact-grid` CSS for consistency with main grid.
 *
 * Performance optimizations:
 * - Bulk insert via DocumentFragment (single reflow)
 * - Chunked rendering (requestIdleCallback) to avoid blocking main thread
 * - IntersectionObserver enqueues thumbnails through the shared batch
 *   fetcher (`thumbnail-batch.ts`) instead of issuing N parallel
 *   `<img src=...>` requests. The batch endpoint serializes server-side
 *   reads in a single thread, dramatically reducing disk contention
 *   when opening a ZIP with dozens of members.
 */

import { getAppApi } from '../shared/browser-apis';
import {
  getCachedDataUrl,
  queueThumbnails,
} from '../search-results/results/thumbnail-batch';

/** Number of cards to render synchronously on first pass (viewport fill).
 * Kept small so the first paint after a panel transition is cheap; the rest
 * stream in via idle callbacks. */
const INITIAL_CHUNK = 8;
/** Number of cards per async chunk */
const ASYNC_CHUNK = 40;

/** Callback to cancel in-progress chunked rendering */
let _cancelChunked: (() => void) | null = null;

/** IntersectionObserver for lazy-loading thumbnails */
let _imgObserver: IntersectionObserver | null = null;

/**
 * Tear down the grid: cancel pending render, disconnect observer, drop card DOM.
 * Called on container-view close so no leftover <img> nodes keep loading or
 * occupy memory after the panel hides.
 *
 * Strategy: swap the grid element with a fresh empty clone in a single
 * `replaceChild` call. The old grid (with all its <img> descendants) becomes
 * an orphan that JS no longer references — the browser frees layout / paint
 * layers / GPU textures for those nodes on its own schedule, instead of all
 * during the close click. This avoids the cursor freeze that
 * `gridEl.replaceChildren()` produced for archives with hundreds of cards.
 *
 * The function still exports for callers that prefer to drive teardown
 * directly (e.g. emergency cleanup on page unload).
 */
export function teardownContainerGrid(gridEl: HTMLElement | null): void {
  if (_cancelChunked) {
    _cancelChunked();
    _cancelChunked = null;
  }
  if (_imgObserver) {
    _imgObserver.disconnect();
    _imgObserver = null;
  }
  if (!gridEl) return;

  const parent = gridEl.parentElement;
  if (!parent || gridEl.childElementCount === 0) {
    // Either detached already, or nothing to remove.
    if (gridEl.childElementCount > 0) gridEl.replaceChildren();
    return;
  }

  // Stop any inflight network loads before unparenting — cheap, no layout.
  const inflight = gridEl.querySelectorAll<HTMLImageElement>('img[src]');
  for (const img of inflight) {
    if (!img.complete) img.src = '';
  }

  // Single-shot swap: O(1) DOM mutation, no per-child layout work.
  const fresh = gridEl.cloneNode(false) as HTMLElement;
  parent.replaceChild(fresh, gridEl);
  // `gridEl` is now an orphan. Drop our last reference to its children
  // by *not* holding it; GC will reclaim it together with its <img> tree.
}

function _enqueueVisible(img: HTMLImageElement): void {
  const idStr = img.dataset.fileId;
  if (!idStr) return;
  const id = Number(idStr);
  if (!Number.isFinite(id)) return;
  if (img.dataset.loaded === '1') return;

  // Try the in-memory data-URL cache first (set by the batch fetcher in
  // earlier search results). This avoids a network round-trip when the
  // user re-opens a recently viewed archive.
  const cached = getCachedDataUrl(id);
  if (cached) {
    img.src = cached;
    img.dataset.loaded = '1';
    return;
  }

  // Hand off to the batch fetcher. Visible thumbnails get priority so
  // they jump ahead of any background prefetch queue.
  queueThumbnails([id], { priority: true });
}

function _getImgObserver(): IntersectionObserver {
  if (!_imgObserver) {
    _imgObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const img = entry.target as HTMLImageElement;
          _enqueueVisible(img);
          _imgObserver!.unobserve(img);
        }
      },
      { rootMargin: '200px' },  // Start loading 200px before entering viewport
    );
  }
  return _imgObserver;
}

/**
 * Create the DOM for a single card (does not appendChild).
 * The img is set up for the shared batch fetcher: `result-image` class +
 * `data-file-id` selector + `data-native-src` fallback. The IntersectionObserver
 * calls `queueThumbnails` once the card scrolls into view.
 */
function _createCard(
  id: number,
  onClickMember: (fileId: number) => void,
): HTMLDivElement {
  const card = document.createElement('div');
  card.className = 'result-card cv-member-card';
  card.tabIndex = 0;
  card.dataset.fileId = String(id);
  card.setAttribute('role', 'button');
  card.setAttribute(
    'aria-label',
    (window.tr?.('container_view.open_image', 'Open image') || 'Open image') + ' #' + id,
  );

  const img = document.createElement('img');
  img.decoding = 'async';
  img.className = 'result-image';
  img.dataset.fileId = String(id);
  img.dataset.nativeSrc = getAppApi().apiUrl('/api/thumbnail/' + id);
  img.alt = '';
  img.draggable = false;
  img.addEventListener('error', () => {
    // Recovery: a blob: URL may have been revoked by the batch fetcher's LRU.
    // Fall back to the native endpoint to re-fetch.
    const currentSrc = img.getAttribute('src') || '';
    const nativeSrc = img.dataset.nativeSrc;
    if (currentSrc.startsWith('blob:') && nativeSrc && currentSrc !== nativeSrc) {
      delete img.dataset.loaded;
      img.src = nativeSrc;
    }
  });

  card.appendChild(img);

  card.addEventListener('click', () => onClickMember(id));
  card.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClickMember(id);
    }
  });

  return card;
}

/**
 * Register all img elements in the fragment with IntersectionObserver.
 */
function _observeImages(container: HTMLElement | DocumentFragment): void {
  const obs = _getImgObserver();
  const imgs = container instanceof HTMLElement
    ? container.querySelectorAll<HTMLImageElement>('img.result-image[data-file-id]')
    : (container as DocumentFragment).querySelectorAll<HTMLImageElement>('img.result-image[data-file-id]');
  for (let i = 0; i < imgs.length; i++) {
    obs.observe(imgs[i]);
  }
}

/**
 * Render member thumbnails into the given grid element.
 * Renders the first INITIAL_CHUNK cards synchronously, then adds the rest incrementally via requestIdleCallback.
 */
export function renderContainerGrid(
  gridEl: HTMLElement,
  memberIds: number[],
  onClickMember: (fileId: number) => void,
): void {
  // Cancel previous chunked rendering if still in progress
  if (_cancelChunked) {
    _cancelChunked();
    _cancelChunked = null;
  }

  // Reset previous IntersectionObserver
  if (_imgObserver) {
    _imgObserver.disconnect();
    _imgObserver = null;
  }

  gridEl.replaceChildren();

  if (!memberIds.length) return;

  // -- Initial chunk: bulk insert via DocumentFragment (single reflow) --
  const firstBatch = Math.min(INITIAL_CHUNK, memberIds.length);
  const frag = document.createDocumentFragment();
  for (let i = 0; i < firstBatch; i++) {
    frag.appendChild(_createCard(memberIds[i], onClickMember));
  }
  _observeImages(frag);
  gridEl.appendChild(frag);

  // Initial-chunk thumbnails are visible; queue them all in one batch
  // request so the server reads them in a single thread (small batches
  // dramatically reduce disk contention vs N parallel <img src> fetches).
  queueThumbnails(memberIds.slice(0, firstBatch), { priority: true });

  // Done if everything fits in initial chunk
  if (firstBatch >= memberIds.length) return;

  // -- Add remaining via async chunks --
  let offset = firstBatch;
  let cancelled = false;

  _cancelChunked = () => { cancelled = true; };

  function renderNextChunk(deadline?: IdleDeadline): void {
    if (cancelled || offset >= memberIds.length) return;

    const chunkFrag = document.createDocumentFragment();
    const end = Math.min(offset + ASYNC_CHUNK, memberIds.length);

    for (let i = offset; i < end; i++) {
      chunkFrag.appendChild(_createCard(memberIds[i], onClickMember));
      // If deadline exists, split chunk on timeout
      if (deadline && deadline.timeRemaining() < 2 && i < end - 1) {
        offset = i + 1;
        _observeImages(chunkFrag);
        gridEl.appendChild(chunkFrag);
        _scheduleIdle(renderNextChunk);
        return;
      }
    }

    _observeImages(chunkFrag);
    gridEl.appendChild(chunkFrag);
    offset = end;

    if (offset < memberIds.length) {
      _scheduleIdle(renderNextChunk);
    }
  }

  _scheduleIdle(renderNextChunk);
}

/** requestIdleCallback (falls back to setTimeout for unsupported browsers) */
function _scheduleIdle(cb: (deadline?: IdleDeadline) => void): void {
  if (typeof requestIdleCallback === 'function') {
    requestIdleCallback(cb, { timeout: 200 });
  } else {
    setTimeout(() => cb(), 16);
  }
}

/**
 * Add .cv-active to the card matching fileId, removing from all others.
 */
export function highlightMember(gridEl: HTMLElement, fileId: number): void {
  const cards = gridEl.querySelectorAll<HTMLElement>('.cv-member-card');
  for (const card of cards) {
    const isTarget = card.dataset.fileId === String(fileId);
    card.classList.toggle('cv-active', isTarget);
  }
}

/**
 * Scroll the target card into view and optionally focus it.
 */
export function scrollToMember(gridEl: HTMLElement, fileId: number): void {
  const card = gridEl.querySelector<HTMLElement>(
    `.cv-member-card[data-file-id="${fileId}"]`,
  );
  if (!card) return;
  card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  card.focus({ preventScroll: true });
}

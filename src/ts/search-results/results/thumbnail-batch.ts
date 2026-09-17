/**
 * Thumbnail batch fetcher
 *
 * Fetches thumbnails for the visible range via /api/thumbnails/batch
 * and replaces <img> src with data URLs.
 * Speeds up image display by avoiding the HTTP/1.1 6-connection limit.
 */

import { getAppApi } from '../../shared/browser-apis';
import {
  getCachedDataUrl,
  makeObjectUrl,
  putCachedDataUrl,
  resetThumbnailCache,
} from './thumbnail-cache';

export { getCachedDataUrl };

/** Batch size (max thumbnails per request) -- matches server limit of 50 */
const BATCH_SIZE = 50;

/** Debounce interval (ms) -- prevents excessive requests during scrolling */
const DEBOUNCE_MS = 30; // 80ms → 30ms: faster response; MAX_INFLIGHT=4 remains the throughput bottleneck
const NATIVE_FALLBACK_DELAY_MS = 1400;

/** Track processed file_ids (prevents duplicate requests) */
const _fetched = new Map<number, 1>();
const MAX_FETCH_TRACK = 120000;

/** Track IDs that failed once (allows one retry, then gives up) */
const _failCount = new Map<number, number>();

/** Pending file_id queue */
let _pending: number[] = [];
const _pendingSet = new Set<number>();

/** Debounce timer */
let _timer: ReturnType<typeof setTimeout> | null = null;

/** Number of in-flight requests */
let _inflight = 0;

/** Max concurrent requests -- batch API allows higher throughput without connection pressure */
const MAX_INFLIGHT = 4;

interface QueueThumbnailOptions {
  /** Prioritize thumbnails that are currently visible over background prefetch work. */
  priority?: boolean;
}

/**
 * Add thumbnails for the given file_ids to the batch queue.
 * Batch fetch executes after debounce unless priority work can start immediately.
 */
export function queueThumbnails(ids: number[], options: QueueThumbnailOptions = {}): void {
  const priorityIds: number[] = [];
  for (const id of ids) {
    if (_fetched.has(id) && _isDomThumbnailLoaded(id)) {
      continue;
    }
    if (options.priority) {
      if (_pendingSet.has(id)) {
        _pending = _pending.filter((pendingId) => pendingId !== id);
      }
      if (!priorityIds.includes(id)) {
        priorityIds.push(id);
      }
      _pendingSet.add(id);
    } else if (!_pendingSet.has(id)) {
      _pending.push(id);
      _pendingSet.add(id);
    }
  }
  if (priorityIds.length > 0) {
    _pending = priorityIds.concat(_pending);
    if (_timer !== null) {
      clearTimeout(_timer);
      _timer = null;
    }
    if (_inflight < MAX_INFLIGHT) {
      void _flush();
    } else {
      _scheduleFlush();
    }
    return;
  }
  _scheduleFlush();
}

function _isDomThumbnailLoaded(id: number): boolean {
  const imgs = document.querySelectorAll<HTMLImageElement>(
    `img.result-image[data-file-id="${id}"]`,
  );
  if (imgs.length === 0) return false;
  for (const img of imgs) {
    if (img.dataset.loaded === '1') return true;
    if (img.complete && img.naturalWidth > 1 && img.naturalHeight > 1) return true;
  }
  return false;
}

function _markFetched(id: number): void {
  if (_fetched.has(id)) {
    _fetched.delete(id);
  }
  _fetched.set(id, 1);
  while (_fetched.size > MAX_FETCH_TRACK) {
    const oldest = _fetched.keys().next().value as number | undefined;
    if (typeof oldest !== 'number') break;
    _fetched.delete(oldest);
  }
}

function _scheduleFlush(): void {
  if (_timer !== null) return;
  _timer = setTimeout(() => {
    _timer = null;
    _flush();
  }, DEBOUNCE_MS);
}

async function _flush(): Promise<void> {
  // Drain as many batches as concurrency allows
  while (_inflight < MAX_INFLIGHT && _pending.length > 0) {
    const batch = _pending.splice(0, BATCH_SIZE);
    for (const id of batch) _pendingSet.delete(id);
    if (batch.length === 0) break;
    _inflight++;
    _fetchBatch(batch);
  }
}

async function _fetchBatch(batch: number[]): Promise<void> {
  let fallbackTimer: ReturnType<typeof setTimeout> | null = setTimeout(() => {
    fallbackTimer = null;
    _fallbackToNative(batch);
  }, NATIVE_FALLBACK_DELAY_MS);
  try {
    const resp = await fetch(getAppApi().apiUrl('/api/thumbnails/batch'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'multipart/mixed, application/json' },
      body: JSON.stringify({ ids: batch }),
    });
    if (fallbackTimer !== null) {
      clearTimeout(fallbackTimer);
      fallbackTimer = null;
    }
    if (!resp.ok) {
      // Batch request failed -- let individual <img> src handle it
      // Don't mark these IDs as fetched so they can be retried
      _fallbackToNative(batch);
      return;
    }

    const thumbnails = await _readThumbnailResponse(resp);
    const returnedIds = new Set<number>();

    // Replace <img> src with data URL in DOM
    for (const [id, dataUrl] of Object.entries(thumbnails)) {
      const numId = Number(id);
      returnedIds.add(numId);
      _markFetched(numId);

      putCachedDataUrl(numId, dataUrl);

      const imgs = document.querySelectorAll<HTMLImageElement>(
        `img.result-image[data-file-id="${id}"]`,
      );
      for (const img of imgs) {
        // Skip if already loaded with a real thumbnail (not a placeholder)
        if (img.complete && img.naturalWidth > 1 && img.naturalHeight > 1) {
          img.dataset.loaded = '1';
          continue;
        }
        img.src = dataUrl;
        img.dataset.loaded = '1';
        delete img.dataset.loadError;
        img.style.opacity = '';
      }
    }

    // IDs that were in the batch but NOT returned by server:
    // Mark as fetched but allow one retry by not adding to _fetched
    // if they haven't been tried before. This handles transient failures
    // (e.g. file being scanned, cache race) without infinite retries.
    for (const id of batch) {
      if (!returnedIds.has(id)) {
        _fallbackToNative([id]);
        if (_failCount.has(id)) {
          // Already retried once -- give up to prevent infinite loops
          _markFetched(id);
        } else {
          _failCount.set(id, 1);
          // Keep it eligible for one retry, but recover immediately via native src.
        }
      }
    }
  } catch {
    if (fallbackTimer !== null) {
      clearTimeout(fallbackTimer);
      fallbackTimer = null;
    }
    // Network error -- don't mark as fetched, individual <img> src
    // will attempt to load via browser's native mechanism
    _fallbackToNative(batch);
  } finally {
    _inflight--;
  }

  // After request completes, drain more pending items
  if (_pending.length > 0) {
    _scheduleFlush();
  }
}

async function _readThumbnailResponse(resp: Response): Promise<Record<string, string>> {
  const contentType = resp.headers.get('Content-Type') || '';
  if (contentType.toLowerCase().includes('multipart/mixed')) {
    return _parseMultipartThumbnails(resp, contentType);
  }
  const data = await resp.json();
  return data.thumbnails || {};
}

async function _parseMultipartThumbnails(resp: Response, contentType: string): Promise<Record<string, string>> {
  const boundaryMatch = contentType.match(/boundary="?([^";]+)"?/i);
  if (!boundaryMatch) return {};
  const boundary = new TextEncoder().encode('--' + boundaryMatch[1]);
  const body = new Uint8Array(await resp.arrayBuffer());
  const out: Record<string, string> = {};
  let pos = _indexOfBytes(body, boundary, 0);
  while (pos >= 0) {
    pos += boundary.length;
    if (body[pos] === 45 && body[pos + 1] === 45) break;
    if (body[pos] === 13 && body[pos + 1] === 10) pos += 2;
    const headerEnd = _indexOfBytes(body, new Uint8Array([13, 10, 13, 10]), pos);
    if (headerEnd < 0) break;
    const headerText = new TextDecoder('latin1').decode(body.slice(pos, headerEnd));
    const next = _indexOfBytes(body, boundary, headerEnd + 4);
    if (next < 0) break;
    let dataEnd = next;
    if (dataEnd >= 2 && body[dataEnd - 2] === 13 && body[dataEnd - 1] === 10) dataEnd -= 2;
    const id = headerText.match(/^X-File-Id:\s*(\d+)/im)?.[1];
    if (id) {
      const mime = headerText.match(/^Content-Type:\s*([^\r\n]+)/im)?.[1]?.trim() || 'image/jpeg';
      out[id] = makeObjectUrl(body.slice(headerEnd + 4, dataEnd), mime);
    }
    pos = next;
  }
  return out;
}

function _indexOfBytes(haystack: Uint8Array, needle: Uint8Array, from: number): number {
  outer: for (let i = from; i <= haystack.length - needle.length; i++) {
    for (let j = 0; j < needle.length; j++) {
      if (haystack[i + j] !== needle[j]) continue outer;
    }
    return i;
  }
  return -1;
}

function _fallbackToNative(ids: number[]): void {
  for (const id of ids) {
    const imgs = document.querySelectorAll<HTMLImageElement>(
      `img.result-image[data-file-id="${id}"]`,
    );
    for (const img of imgs) {
      if (img.dataset.loaded === '1') continue;
      const nativeSrc = img.dataset.nativeSrc;
      if (nativeSrc && img.getAttribute('src') !== nativeSrc) {
        img.src = nativeSrc;
      }
    }
  }
}

/** Clear batch cache (on new search) */
export function resetThumbnailBatch(): void {
  _fetched.clear();
  _failCount.clear();
  resetThumbnailCache();
  _pending = [];
  _pendingSet.clear();
  if (_timer !== null) {
    clearTimeout(_timer);
    _timer = null;
  }
}

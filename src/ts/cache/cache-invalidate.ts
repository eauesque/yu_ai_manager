/**
 * cache-invalidate.ts -- SSE event-driven cache invalidation
 *
 * Receives events from the shared SSE module and deletes matching cache entries.
 */

import { sseSubscribe } from '../sse';
import type { SseEventType } from '../sse';
import { openCacheDb } from './idb-store';
import { getPrefixesForEvent } from './cache-policy';

/** List of SSE event types that trigger invalidation */
const SSE_TYPES: SseEventType[] = [
  'scan.complete',
  'favorite.add',
  'favorite.remove',
  'collection.create',
  'collection.delete',
];

let _initialized = false;

/**
 * On SSE event reception, invalidate cache entries matching the relevant prefixes.
 */
async function invalidateForEvent(eventType: string): Promise<void> {
  const prefixes = getPrefixesForEvent(eventType);
  if (prefixes.length === 0) return;

  try {
    const db = await openCacheDb();
    const tx = db.transaction('api_cache', 'readwrite');
    const store = tx.objectStore('api_cache');
    const cursorReq = store.openCursor();

    cursorReq.onsuccess = () => {
      const cursor = cursorReq.result;
      if (!cursor) return;

      const url = (cursor.value as { url: string }).url;
      for (const prefix of prefixes) {
        if (url.startsWith(prefix)) {
          cursor.delete();
          break;
        }
      }
      cursor.continue();
    };
  } catch {
    // Silently ignore when IndexedDB is unavailable
  }
}

/**
 * Initialize SSE listeners for cache invalidation.
 * Safe to call multiple times (idempotent).
 */
export function initCacheInvalidation(): void {
  if (_initialized) return;
  _initialized = true;

  for (const t of SSE_TYPES) {
    sseSubscribe(t, () => {
      invalidateForEvent(t).catch(() => {});
    });
  }

  // On scan.complete, also clear Service Worker + metadata cache
  sseSubscribe('scan.complete', () => {
    _clearSwThumbCache();
    _clearMetadataCache();
  });
}

/** Instruct Service Worker to clear thumbnail cache */
function _clearSwThumbCache(): void {
  if (!navigator.serviceWorker?.controller) return;
  navigator.serviceWorker.controller.postMessage({ type: 'CLEAR_THUMB_CACHE' });
}

/** Clear the modal metadata prefetch cache */
function _clearMetadataCache(): void {
  try {
    // Use dynamic import to avoid circular references
    import('../detail-modal/runtime/metadata-prefetch').then(m => m.clearMetadataCache()).catch(() => {});
  } catch {
    // ignore
  }
}

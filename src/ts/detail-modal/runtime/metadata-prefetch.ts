/**
 * metadata-prefetch.ts
 *
 * Caches /api/file/{id} responses in memory and
 * prefetches metadata for neighboring images.
 * Enables instant response for modal navigation (left/right arrows).
 */

import { getAppApi } from '../../shared/browser-apis';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type FileData = Record<string, any>;

interface CacheEntry {
  data: FileData;
  ts: number;
}

/** Maximum number of cache entries */
const MAX_ENTRIES = 30;
/** TTL (ms) — 5 minutes */
const TTL = 5 * 60 * 1000;
/** Maximum concurrent prefetch requests */
const MAX_PREFETCH_INFLIGHT = 2;

const _cache = new Map<number, CacheEntry>();
let _prefetchInflight = 0;

/**
 * Retrieve metadata from the cache.
 * Returns the cached data on hit, or null on miss.
 */
export function getCachedMetadata(id: number): FileData | null {
  const entry = _cache.get(id);
  if (!entry) return null;
  if (Date.now() - entry.ts > TTL) {
    _cache.delete(id);
    return null;
  }
  return entry.data;
}

/**
 * Store metadata in the cache.
 */
export function cacheMetadata(id: number, data: FileData): void {
  // Size limit: evict the oldest entry
  if (_cache.size >= MAX_ENTRIES) {
    const oldest = _cache.keys().next().value;
    if (oldest !== undefined) _cache.delete(oldest);
  }
  _cache.set(id, { data, ts: Date.now() });
}

/**
 * Fetch /api/file/{id} and store in cache.
 * Skips the network request on cache hit.
 */
export async function fetchMetadata(id: number): Promise<FileData> {
  const cached = getCachedMetadata(id);
  if (cached) return cached;

  const resp = await getAppApi().apiFetch(`/api/file/${id}`);
  const data = await resp.json();
  cacheMetadata(id, data);
  return data;
}

/**
 * Warm one metadata entry in the background.
 * Safe to call repeatedly; cache hits are cheap and silent.
 */
export function warmMetadata(id: number): void {
  if (!Number.isFinite(id) || id <= 0) return;
  if (getCachedMetadata(id)) return;
  void fetchMetadata(id).catch(() => {});
}

/**
 * Prefetch metadata for neighboring images (fire-and-forget).
 * Called after showDetail completes.
 */
export function prefetchNeighborMetadata(ids: number[], currentIndex: number): void {
  const targets: number[] = [];
  // Prefetch 2 items before and after the current one
  for (const offset of [1, -1, 2, -2]) {
    const idx = currentIndex + offset;
    if (idx >= 0 && idx < ids.length) {
      const id = ids[idx];
      if (!getCachedMetadata(id)) targets.push(id);
    }
  }

  for (const id of targets) {
    if (_prefetchInflight >= MAX_PREFETCH_INFLIGHT) break;
    _prefetchInflight++;
    getAppApi().apiFetch(`/api/file/${id}`)
      .then(r => r.json())
      .then(data => {
        cacheMetadata(id, data);
        // If the neighbor is video/audio, warm up the first 2MB
        _warmupIfMedia(id, data);
      })
      .catch(() => {})
      .finally(() => { _prefetchInflight--; });
  }
}

const _VIDEO_EXTS = /\.(webm|mp4|avi|mov|mkv|m4v|ogv)$/i;
const _AUDIO_EXTS = /\.(mp3|wav|ogg|m4a|aac|flac|opus)$/i;

/** If the neighboring file is video/audio, prefetch the first 2MB. */
function _warmupIfMedia(id: number, data: FileData): void {
  const path = String(data?.path || '');
  if (!_VIDEO_EXTS.test(path) && !_AUDIO_EXTS.test(path)) return;
  fetch(getAppApi().apiUrl(`/api/original/${id}`), {
    method: 'GET',
    headers: { 'Range': 'bytes=0-2097151' },
  }).catch(() => {});
}

/**
 * Invalidate the cache (e.g. on scan.complete).
 */
export function clearMetadataCache(): void {
  _cache.clear();
}

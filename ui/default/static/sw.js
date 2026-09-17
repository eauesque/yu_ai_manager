/**
 * Service Worker — Cache acceleration for thumbnails and preview images
 *
 * Strategy:
 * - /api/thumbnail/*, /api/preview/*: Cache-First (immutable images)
 * - /api/original/*: Cache-First (ETag based)
 * - Others: Network-First (API JSON, HTML, etc.)
 *
 * Automatic eviction via cache size limits.
 */

// v4: Fix cache.keys() AbortError when cache grows too large
// v3: Fix empty/broken response caching in thumbnail cache
// v2: Fix 206 Partial Content caching bug
const CACHE_NAME = 'yu-media-v3';
const THUMB_CACHE = 'yu-thumbs-v3';
const PREVIEW_CACHE = 'yu-preview-v2';

/** Maximum entries for thumbnail cache */
const THUMB_MAX = 5000;
/** Maximum entries for preview cache */
const PREVIEW_MAX = 200;
/** Maximum entries for original image cache */
const ORIGINAL_MAX = 50;

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) => {
      return Promise.all(
        names
          .filter((n) => ![CACHE_NAME, THUMB_CACHE, PREVIEW_CACHE].includes(n))
          .map((n) => caches.delete(n))
      );
    }).then(() => self.clients.claim())
  );
});

/**
 * Limit cache size (LRU-like: delete oldest entries).
 * If cache.keys() fails (browser "Operation too large" AbortError),
 * delete the entire cache to recover rather than leaving it broken.
 */
async function trimCache(cacheName, maxItems) {
  const cache = await caches.open(cacheName);
  let keys;
  try {
    keys = await cache.keys();
  } catch {
    // Cache too large for keys() — nuke and start fresh
    await caches.delete(cacheName);
    return;
  }
  if (keys.length <= maxItems) return;
  const excess = keys.length - maxItems;
  for (let i = 0; i < excess; i++) {
    await cache.delete(keys[i]);
  }
}

/**
 * Cache-First strategy: skip network request on cache hit
 */
async function cacheFirst(request, cacheName, maxItems) {
  // Cache API only supports GET — skip non-GET (e.g. HEAD) to avoid errors
  if (request.method !== 'GET') {
    return fetch(request);
  }
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) {
    const ct = (cached.headers.get('content-type') || '').toLowerCase();
    // Thumbnails/previews must be image responses.
    if (!ct.startsWith('image/')) {
      cache.delete(request);
    } else {
    // Validate cached response has actual body content.
    // Use clone so the returned response body is still consumable.
      try {
        const buf = await cached.clone().arrayBuffer();
        if (buf.byteLength > 0) return cached;
      } catch { /* corrupted entry — fall through to re-fetch */ }
      // Empty or corrupted cache entry — evict and re-fetch from network
      cache.delete(request);
    }
  }

  try {
    const response = await fetch(request);
    const ct = (response.headers.get('content-type') || '').toLowerCase();
    if (response.status === 200 && ct.startsWith('image/')) {
      cache.put(request, response.clone());
      trimCache(cacheName, maxItems).catch(() => {});
    }
    return response;
  } catch (err) {
    throw err;
  }
}

/**
 * Cache-First strategy for original media only.
 *
 * Unlike regular cacheFirst, does not cache 206 Partial Content.
 * Prevents a critical bug where video/audio Range warmup responses (512KB)
 * get cached and <video> elements only receive fragments.
 */
async function cacheFirstFull200Only(request, cacheName, maxItems) {
  // Cache API only supports GET — skip non-GET (e.g. HEAD) to avoid errors
  if (request.method !== 'GET') {
    return fetch(request);
  }
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  // Only return 200 (full response) — ignore if 206 leaked into cache
  if (cached && cached.status === 200) return cached;

  try {
    const response = await fetch(request);
    // Only cache 200 (exclude 206 Partial Content)
    if (response.status === 200) {
      cache.put(request, response.clone());
      trimCache(cacheName, maxItems).catch(() => {});
    }
    return response;
  } catch (err) {
    // When offline: return even 206 (better than nothing)
    if (cached) return cached;
    throw err;
  }
}

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Thumbnails: Cache-First
  if (url.pathname.match(/^\/api\/thumbnail\/\d+$/)) {
    event.respondWith(cacheFirst(event.request, THUMB_CACHE, THUMB_MAX));
    return;
  }

  // Previews: Cache-First
  if (url.pathname.match(/^\/api\/preview\/\d+$/)) {
    event.respondWith(cacheFirst(event.request, PREVIEW_CACHE, PREVIEW_MAX));
    return;
  }

  // Original media: Range requests (video/audio streaming) go directly to network
  // Cache API matches by URL only, so Range warmup 206 responses would match
  // full requests from <video> elements and only return 512KB — prevent this bug
  if (url.pathname.match(/^\/api\/original\/\d+$/)) {
    if (event.request.headers.get('range')) {
      return; // Range requests bypass SW and go directly to network
    }
    event.respondWith(cacheFirstFull200Only(event.request, CACHE_NAME, ORIGINAL_MAX));
    return;
  }

  // Others: pass through to network (bypass SW)
});

// Message handler to clear thumbnail cache when scan.complete event is received
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'CLEAR_THUMB_CACHE') {
    caches.delete(THUMB_CACHE);
  }
  if (event.data && event.data.type === 'CLEAR_ALL_CACHE') {
    caches.delete(THUMB_CACHE);
    caches.delete(PREVIEW_CACHE);
    caches.delete(CACHE_NAME);
  }
});

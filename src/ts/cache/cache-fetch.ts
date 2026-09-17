/**
 * cache-fetch.ts — Cached fetch wrapper
 *
 * Applies policy-based IndexedDB caching for GET requests.
 * Falls back to normal fetch when caching is unavailable or no policy is defined.
 */

import { getCacheEntry, putCacheEntry, purgeExpiredEntries } from './idb-store';
import { findPolicy } from './cache-policy';
import { initCacheInvalidation } from './cache-invalidate';
import { getAppApi } from '../shared/browser-apis';

/** Timestamp of last purge execution (Date.now()) */
let _lastPurge = 0;
const _inflightGets = new Map<string, Promise<unknown>>();
/** Minimum purge interval (5 minutes) */
const PURGE_INTERVAL = 5 * 60 * 1000;

/** Skip if within PURGE_INTERVAL since last purge */
function maybePurge(): void {
  const now = Date.now();
  if (now - _lastPurge < PURGE_INTERVAL) return;
  _lastPurge = now;
  purgeExpiredEntries().catch(() => {});
}

/**
 * Extract the path portion (including query params, excluding origin) from a URL.
 * Returns relative URLs as-is.
 */
function extractPath(url: string): string {
  try {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      const u = new URL(url);
      return u.pathname + u.search;
    }
  } catch {
    // Return as-is on parse failure
  }
  return url;
}

/**
 * Internal fetch call. Uses window.apiFetch if available, otherwise fetch.
 * apiFetch returns a Response, which is used as-is.
 */
async function doFetch(url: string, options?: RequestInit): Promise<Response> {
  return getAppApi().apiFetch(url, options);
}

/**
 * Cache-aware API fetch wrapper.
 *
 * - Only GET requests are cached (POST/PUT/DELETE pass through)
 * - URLs without a matching policy also pass through
 * - Falls back gracefully when IndexedDB is unavailable (cache is purely optional)
 *
 * @param url - Request URL (relative path or absolute URL)
 * @param options - fetch options
 * @returns JSON-parsed response data
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function cachedApiFetch(url: string, options?: RequestInit): Promise<any> {
  // Pass through non-GET requests
  const method = (options?.method || "GET").toUpperCase();
  if (method !== "GET") {
    const res = await doFetch(url, options);
    return res.json();
  }

  // Find matching policy (by path portion)
  const path = extractPath(url);
  const policy = findPolicy(path);
  if (!policy) {
    const res = await doFetch(url, options);
    return res.json();
  }

  initCacheInvalidation();

  // Check for cache hit
  try {
    const cached = await getCacheEntry(path);
    if (cached) {
      return cached.data;
    }
  } catch {
    // Fall back on cache read failure
  }

  // Cache miss — network fetch
  let promise = _inflightGets.get(path);
  if (!promise) {
    promise = doFetch(url, options)
      .then((res) => res.json())
      .finally(() => {
        _inflightGets.delete(path);
      });
    _inflightGets.set(path, promise);
  }
  const data = await promise;

  // Save to cache in background + purge expired entries (rate-limited)
  putCacheEntry(path, data, policy.ttl).catch(() => {});
  maybePurge();

  return data;
}

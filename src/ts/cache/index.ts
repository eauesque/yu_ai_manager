/**
 * cache module — IndexedDB cache for API responses
 *
 * Re-exports the public API surface.
 */

export { openCacheDb, getCacheEntry, putCacheEntry, deleteCacheEntry, clearAllCache, purgeExpiredEntries } from './idb-store';
export type { CacheEntry } from './idb-store';
export { findPolicy, getPrefixesForEvent } from './cache-policy';
export type { CachePolicy } from './cache-policy';
export { cachedApiFetch } from './cache-fetch';
export { initCacheInvalidation } from './cache-invalidate';

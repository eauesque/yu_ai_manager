/**
 * cache-policy.ts — Per-API cache policy definitions
 *
 * Manages TTL and invalidation triggers based on URL prefixes.
 */

/** Cache policy type definition */
export interface CachePolicy {
  /** Cache TTL (milliseconds) */
  ttl: number;
  /** SSE event names that invalidate this cache */
  invalidateOn: string[];
}

/**
 * URL prefix -> policy mapping.
 * Longer prefixes take priority via longest-match in findPolicy.
 */
const policies: ReadonlyArray<[string, CachePolicy]> = [
  ["/api/file-detail/", { ttl: 300_000, invalidateOn: ["scan.complete"] }],
  ["/api/stats/",       { ttl: 300_000, invalidateOn: ["scan.complete"] }],
  ["/api/tags",         { ttl: 600_000, invalidateOn: ["scan.complete"] }],
  ["/api/collections",  { ttl: 120_000, invalidateOn: ["favorite.add", "favorite.remove", "collection.create", "collection.delete"] }],
  ["/api/suggest",      { ttl: 30_000,  invalidateOn: ["scan.complete"] }],
  ["/api/search",       { ttl: 60_000,  invalidateOn: ["scan.complete"] }],
];

/**
 * Find the cache policy matching a URL.
 * Returns the longest prefix match, or null if no match.
 *
 * @example
 * findPolicy("/api/search?q=test")  // -> { ttl: 60000, ... }
 * findPolicy("/api/scan/start")     // -> null
 */
export function findPolicy(url: string): CachePolicy | null {
  let best: CachePolicy | null = null;
  let bestLen = 0;

  for (const [prefix, policy] of policies) {
    if (url.startsWith(prefix) && prefix.length > bestLen) {
      best = policy;
      bestLen = prefix.length;
    }
  }

  return best;
}

/**
 * Return the list of URL prefixes that should be invalidated for the given SSE event.
 */
export function getPrefixesForEvent(eventName: string): string[] {
  const result: string[] = [];
  for (const [prefix, policy] of policies) {
    if (policy.invalidateOn.includes(eventName)) {
      result.push(prefix);
    }
  }
  return result;
}

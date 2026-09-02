/**
 * nav/utils — Resilient JSON fetch with exponential backoff retry.
 *
 * Used by nav subsystems (extensions-menu, lock-visibility) to cope
 * with transient failures during server startup.
 */

/**
 * Fetch JSON with automatic retry on failure.
 *
 * @param url      - The URL to fetch
 * @param opts     - Optional RequestInit (headers, method, etc.)
 * @param retries  - Number of remaining retry attempts
 * @param delay    - Current delay in ms before next retry (grows by 1.5x)
 * @returns Parsed JSON or null on exhausted retries
 */
export function navFetchJson<T = unknown>(
  url: string,
  opts: RequestInit | null,
  retries: number,
  delay: number,
): Promise<T | null> {
  return fetch(url, opts || {})
    .then((r) => {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json() as Promise<T>;
    })
    .catch((err: unknown) => {
      if (retries > 0) {
        return new Promise<T | null>((resolve) => {
          setTimeout(() => {
            resolve(navFetchJson<T>(url, opts, retries - 1, delay * 1.5));
          }, delay);
        });
      }
      const msg = err instanceof Error ? err.message : String(err);
      console.warn('[nav]', url, 'failed:', msg);
      return null;
    });
}

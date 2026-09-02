/**
 * Background-fetch the entire playing video/audio and store it
 * in the browser cache.
 *
 * This eliminates the need for Range requests to the server on seek,
 * serving data instantly from the cache.
 *
 * - Triggered on playback start (canplay event)
 * - Only targets files 50MB or smaller (to avoid memory pressure)
 * - Skips yufile:// URLs (direct filesystem access)
 * - Prevents duplicate fetches for the same URL
 */

const _fetching = new Set<string>();
const _fetched = new Set<string>();

/** Maximum size for background full fetch (bytes) */
const MAX_BACKGROUND_FETCH_SIZE = 80 * 1024 * 1024; // 80MB

/**
 * Set up background full fetch for a media element.
 * Triggered on canplay event, fetching the entire file with a non-Range GET.
 */
export function setupBackgroundFetch(media: HTMLMediaElement): void {
  const source = media.querySelector('source');
  const url = source?.src || (media as HTMLVideoElement).src;
  if (!url) return;

  // yufile:// provides direct filesystem access, no fetch needed
  if (url.startsWith('yufile://')) return;

  // Skip if already fetched or in progress
  if (_fetched.has(url) || _fetching.has(url)) return;

  const doFetch = () => {
    media.removeEventListener('canplay', doFetch);
    _backgroundFetch(url);
  };

  // canplay: triggered when playback becomes possible
  // (after metadata loading + first frame decode completion)
  if (media.readyState >= 3) {
    // Already past canplay
    _backgroundFetch(url);
  } else {
    media.addEventListener('canplay', doFetch, { once: true });
  }
}

/**
 * Fetch the entire file in the background.
 * Checks the size limit via the Content-Length header;
 * if within the limit, reads the entire file into the browser cache.
 */
async function _backgroundFetch(url: string): Promise<void> {
  if (_fetching.has(url) || _fetched.has(url)) return;
  _fetching.add(url);

  try {
    // Check size via HEAD (prevent unnecessary downloads)
    const head = await fetch(url, { method: 'HEAD' });
    const contentLength = parseInt(head.headers.get('Content-Length') || '0', 10);

    if (contentLength <= 0 || contentLength > MAX_BACKGROUND_FETCH_SIZE) {
      return;
    }

    // Fetch the entire file with a non-Range GET
    // Full data gets stored in the browser's HTTP cache
    const resp = await fetch(url, {
      method: 'GET',
      // No Range header = 200 OK full response
      // cache: 'force-cache' would prefer existing cache, but
      // cache: 'default' fetches from network if absent and stores in cache
      cache: 'default',
    });

    if (resp.ok) {
      // Consume the response body to ensure it is stored in the browser cache
      // arrayBuffer() reads the entire body (will be freed by GC)
      await resp.arrayBuffer();
      _fetched.add(url);
    }
  } catch {
    // Silently ignore network errors
  } finally {
    _fetching.delete(url);
  }
}

/**
 * Clean up fetch state when the modal closes, etc.
 * (AbortController is not used — background completion is prioritized)
 */
export function clearBackgroundFetchState(): void {
  // Let in-progress fetches complete (to store in browser cache)
  // _fetched is intentionally not cleared (to prevent re-fetching)
}

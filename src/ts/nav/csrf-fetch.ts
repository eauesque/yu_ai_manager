/**
 * Global fetch interceptor — automatically adds X-Requested-With header
 * to all requests for CSRF protection.
 *
 * This prevents cross-origin POST/PUT/DELETE requests because the custom
 * header triggers a CORS preflight that will be rejected (no CORS headers
 * are configured on the server).
 */

const HEADER_NAME = 'X-Requested-With';
const HEADER_VALUE = 'XMLHttpRequest';

let _installed = false;

export function installCsrfFetchInterceptor(): void {
  if (_installed) return;
  _installed = true;

  const originalFetch = window.fetch;
  window.fetch = function patchedFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    // Skip data:/blob: URLs — they don't traverse the network so CSRF headers
    // are unnecessary, and per Fetch spec attaching custom headers to a data:
    // URL produces a network error ("TypeError: Failed to fetch").
    let urlStr: string;
    if (typeof input === 'string') urlStr = input;
    else if (input instanceof URL) urlStr = input.href;
    else urlStr = (input as Request).url;
    if (urlStr.startsWith('data:') || urlStr.startsWith('blob:')) {
      return originalFetch.call(this, input, init);
    }
    const headers = new Headers(init?.headers);
    if (!headers.has(HEADER_NAME)) {
      headers.set(HEADER_NAME, HEADER_VALUE);
    }
    return originalFetch.call(this, input, { ...init, headers });
  };
}

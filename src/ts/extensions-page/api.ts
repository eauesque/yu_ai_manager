/**
 * Extensions API utilities — fetch wrapper with timeout and HTML escaping.
 * Converted from static/js/extensions/extensions-api.js
 */

const EXTENSION_API_TIMEOUT = 15000;

/**
 * Fetch wrapper with 15-second abort timeout.
 * Throws on non-OK responses or timeout.
 */
export async function extensionApiFetch(
  url: string,
  options: RequestInit = {},
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), EXTENSION_API_TIMEOUT);
  const headers = new Headers(options.headers);
  if (!headers.has('X-Requested-With')) {
    headers.set('X-Requested-With', 'XMLHttpRequest');
  }
  try {
    const response = await fetch(url, { ...options, headers, signal: controller.signal });
    clearTimeout(timeoutId);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response;
  } catch (err: unknown) {
    clearTimeout(timeoutId);
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('Request timed out (15s)');
    }
    throw err;
  }
}

/**
 * Escape a string for safe HTML insertion using DOM textContent.
 */
export function extensionEsc(str: string | undefined | null): string {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

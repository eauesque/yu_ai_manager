/**
 * API utilities — URL builder, fetch wrapper, HTML escaping.
 * Converted from static/js/main/main-api-utils.js
 */

import { captureApiFailure } from '../shared/error-reporter';
import { apiUrl } from '../shared/api-base';

export { apiUrl };

let _authRedirectShown = false;

function isBenignAbortedRequest(err: unknown, signal?: AbortSignal | null): boolean {
  if (!signal?.aborted) return false;
  if (err instanceof DOMException && err.name === 'AbortError') return true;
  if (err instanceof Error && err.name === 'AbortError') return true;
  const message = err instanceof Error ? err.message : String(err || '');
  return message === 'signal is aborted without reason';
}

/**
 * Try to translate an API error code via ui_runtime i18n.
 * Falls back to the original error message if no translation is found.
 */
function translateApiError(code: string, fallbackMessage: string): string {
  if (!code) return fallbackMessage;
  try {
    if (typeof window.tr === 'function') {
      const translated = String(window.tr(`api_error.${code}`));
      // tr() returns the key path itself when no translation is found
      if (translated && translated !== `api_error.${code}`) return translated;
    }
  } catch {
    // ignore — tr may not be ready
  }
  return fallbackMessage;
}

export type ApiFetchOpts = RequestInit & {
  /** When true, network/HTTP errors are not reported to the error bundle. Use for non-critical background fetches. */
  silent?: boolean;
};

export async function apiFetch(path: string, opts?: ApiFetchOpts): Promise<Response> {
  const { silent, ...fetchOpts } = opts ?? {};
  const url = apiUrl(path);
  // Inject X-Requested-With header for CSRF protection on all requests
  const headers = new Headers(fetchOpts?.headers);
  if (!headers.has('X-Requested-With')) {
    headers.set('X-Requested-With', 'XMLHttpRequest');
  }
  const method = (fetchOpts?.method || 'GET').toUpperCase();
  let res: Response;
  try {
    res = await fetch(url, { ...fetchOpts, headers });
  } catch (err) {
    if (isBenignAbortedRequest(err, fetchOpts?.signal ?? null)) {
      throw err;
    }
    if (!silent) {
      captureApiFailure({
        url,
        method,
        status: 0,
        statusText: 'NETWORK_ERROR',
        responsePreview: err instanceof Error ? err.message : String(err || ''),
        context: {
          source: 'apiFetch.network',
        },
      });
    }
    throw err;
  }
  if (!res.ok) {
    let body = '';
    try {
      body = await res.text();
    } catch {
      // ignore
    }
    body = (body || '').slice(0, 200);

    // Try to parse JSON error with code field for i18n translation
    let errorMessage = `HTTP ${res.status} ${res.statusText} for ${url}`;
    let parsedCode = '';
    try {
      const parsed = JSON.parse(body);
      if (parsed && typeof parsed === 'object' && parsed.error) {
        parsedCode = parsed.code || '';
        const original = String(parsed.error);
        errorMessage = translateApiError(parsedCode, original);
      } else if (body) {
        errorMessage += ' :: ' + body;
      }
    } catch {
      if (body) errorMessage += ' :: ' + body;
    }
    // Session expired (PIN auth required) -- same handling as the HTML PIN
    // page branch below: redirect to login once, do NOT report as a bug.
    if (res.status === 401 && path.startsWith('/api/') && parsedCode === 'pin_auth_required') {
      if (!_authRedirectShown) {
        _authRedirectShown = true;
        console.warn('[apiFetch] session expired (401 pin_auth_required):', path);
        setTimeout(() => { location.href = '/'; }, 200);
      }
      throw new Error('Session expired — redirecting to login');
    }
    if (!silent) {
      captureApiFailure({
        url,
        method,
        status: res.status,
        statusText: res.statusText,
        requestId: res.headers.get('X-Request-Id') || '',
        responsePreview: body,
        context: {
          source: 'apiFetch.http',
        },
      });
    }
    throw new Error(errorMessage);
  }

  // Detect PIN auth page returned instead of JSON (session expired or not authenticated)
  const ct = res.headers.get('content-type') || '';
  if (path.startsWith('/api/') && ct.includes('text/html')) {
    if (!_authRedirectShown) {
      _authRedirectShown = true;
      console.warn('[apiFetch] API returned HTML instead of JSON — session may have expired:', path);
      // Redirect to login after a short delay so the user sees the issue
      setTimeout(() => { location.href = '/'; }, 200);
    }
    captureApiFailure({
      url,
      method,
      status: res.status,
      statusText: 'HTML_RESPONSE',
      requestId: res.headers.get('X-Request-Id') || '',
      responsePreview: ct,
      context: {
        source: 'apiFetch.html_response',
      },
    });
    throw new Error('Session expired — redirecting to login');
  }

  return res;
}

export function escapeHtml(text: unknown): string {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export function decodeHtmlEntities(text: string): string {
  const textarea = document.createElement('textarea');
  textarea.innerHTML = text;
  return textarea.value;
}

export function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}

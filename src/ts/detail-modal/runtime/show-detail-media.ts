import type { state as runtimeState } from './state';

/**
 * Progressive loading: thumbnail -> preview (1200px) -> full resolution.
 *
 * 1. Start with the thumbnail displayed (with blur)
 * 2. Background-load the preview (1200px), swap and remove blur on completion
 * 3. Schedule full-resolution load on idle, swap on completion
 *
 * Each stage checks loadSeq to skip if navigation to another image has occurred.
 *
 * Pending loaders are tracked module-level so navigation aborts in-flight
 * fetches by clearing `.src`. Without this, repeated arrow-key navigation can
 * pile up multiple `<img>` requests against the HTTP/1.1 6-connection limit
 * and cause tail latency of 5+ seconds for the visible image.
 */

let _pendingPreviewLoader: HTMLImageElement | null = null;
let _pendingOriginalLoader: HTMLImageElement | null = null;
let _pendingIdleHandle: number | null = null;

function _abortPending(): void {
  if (_pendingPreviewLoader) {
    try { _pendingPreviewLoader.src = ''; } catch (_) { /* ignore */ }
    _pendingPreviewLoader = null;
  }
  if (_pendingOriginalLoader) {
    try { _pendingOriginalLoader.src = ''; } catch (_) { /* ignore */ }
    _pendingOriginalLoader = null;
  }
  if (_pendingIdleHandle != null) {
    const cancel = (window as unknown as { cancelIdleCallback?: (h: number) => void }).cancelIdleCallback;
    if (typeof cancel === 'function') {
      try { cancel(_pendingIdleHandle); } catch (_) { /* ignore */ }
    } else {
      try { clearTimeout(_pendingIdleHandle); } catch (_) { /* ignore */ }
    }
    _pendingIdleHandle = null;
  }
}

function _scheduleIdle(fn: () => void, timeoutMs = 1500): void {
  const ric = (window as unknown as {
    requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
  }).requestIdleCallback;
  if (typeof ric === 'function') {
    _pendingIdleHandle = ric(fn, { timeout: timeoutMs });
  } else {
    _pendingIdleHandle = window.setTimeout(fn, 50) as unknown as number;
  }
}

export function upgradeToFullImage(loadSeq: number, currentState: typeof runtimeState): void {
  _abortPending();

  const img = document.getElementById('modalImage') as HTMLImageElement | null;
  if (!img) return;

  const previewSrc = img.dataset.previewSrc;
  const fullSrc = img.dataset.fullSrc;
  if (!fullSrc) return;

  const isCurrent = () => {
    if (currentState.detailLoadSeq !== loadSeq) return false;
    const el = document.getElementById('modalImage') as HTMLImageElement | null;
    return !!(el && el.dataset.fullSrc === fullSrc);
  };

  const swapSrc = (el: HTMLImageElement, src: string, clearBlur: boolean) => {
    el.src = src;
    if (clearBlur) el.style.filter = '';
    el.dataset.loaded = '1';
  };

  if (previewSrc) {
    const previewLoader = new Image();
    previewLoader.decoding = 'async';
    _pendingPreviewLoader = previewLoader;
    previewLoader.onload = () => {
      if (_pendingPreviewLoader === previewLoader) _pendingPreviewLoader = null;
      if (!isCurrent()) return;
      const el = document.getElementById('modalImage') as HTMLImageElement | null;
      if (!el) return;
      swapSrc(el, previewSrc, true);
      delete el.dataset.previewSrc;
      _scheduleOriginal(fullSrc, loadSeq, currentState);
    };
    previewLoader.onerror = () => {
      // If we've been aborted (`_abortPending` set src='', clearing this
      // pointer), don't proceed to load the original — that would overwrite
      // the next navigation's idle handle and leak a request the user no
      // longer wants. The aborted img's onerror is delivered async by the
      // browser, so this guard catches the race.
      if (_pendingPreviewLoader !== previewLoader) return;
      _pendingPreviewLoader = null;
      _scheduleOriginal(fullSrc, loadSeq, currentState);
    };
    previewLoader.src = previewSrc;
    return;
  }

  _scheduleOriginal(fullSrc, loadSeq, currentState);
}

function _scheduleOriginal(fullSrc: string, loadSeq: number, currentState: typeof runtimeState): void {
  // Defer the full-resolution fetch to idle time. Preview is already displayed,
  // and the visible result on a typical viewport is nearly indistinguishable
  // from the original at 1200px. This yields HTTP/1.1 connection slots back
  // to /api/search and other in-flight requests instead of competing with them.
  _scheduleIdle(() => {
    _pendingIdleHandle = null;
    if (currentState.detailLoadSeq !== loadSeq) return;
    _loadOriginal(fullSrc, loadSeq, currentState);
  });
}

function _loadOriginal(fullSrc: string, loadSeq: number, currentState: typeof runtimeState): void {
  const loader = new Image();
  loader.decoding = 'async';
  _pendingOriginalLoader = loader;
  loader.onload = () => {
    if (_pendingOriginalLoader === loader) _pendingOriginalLoader = null;
    if (currentState.detailLoadSeq !== loadSeq) return;
    const el = document.getElementById('modalImage') as HTMLImageElement | null;
    if (!el || el.dataset.fullSrc !== fullSrc) return;
    el.src = fullSrc;
    el.style.filter = '';
    el.dataset.loaded = '1';
    delete el.dataset.fullSrc;
  };
  loader.onerror = () => {
    if (_pendingOriginalLoader === loader) _pendingOriginalLoader = null;
  };
  loader.src = fullSrc;
}

/**
 * Start preloading video/audio via <link rel="preload">.
 * Begins downloading at the browser's network layer before the <video>/<audio>
 * element is inserted into the DOM, so that when the media element connects,
 * data can be served from the cache.
 */
export function preloadMediaLink(url: string, as: 'video' | 'audio'): void {
  const old = document.getElementById('_mediaPreload');
  if (old) old.remove();

  const link = document.createElement('link');
  link.id = '_mediaPreload';
  link.rel = 'preload';
  link.as = as;
  link.href = url;
  document.head.appendChild(link);
}

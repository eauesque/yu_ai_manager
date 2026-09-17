/** Object/data URL cache used by thumbnail batch loading. */

const _dataUrlCache = new Map<number, string>();
let _dataUrlCacheChars = 0;
const _objectUrls = new Set<string>();
const _deferredRevokeUrls = new Set<string>();
let _revokeSweepTimer: ReturnType<typeof setTimeout> | null = null;

const REVOKE_SWEEP_INTERVAL_MS = 5000;
const MAX_CACHE = 1200;
const MAX_CACHE_CHARS = 48 * 1024 * 1024;

export function getCachedDataUrl(id: number): string | null {
  const val = _dataUrlCache.get(id);
  if (val === undefined) return null;
  _dataUrlCache.delete(id);
  _dataUrlCache.set(id, val);
  return val;
}

export function putCachedDataUrl(id: number, dataUrl: string): void {
  const old = _dataUrlCache.get(id);
  if (old !== undefined) {
    _dataUrlCache.delete(id);
    _releaseCachedUrl(old);
  }
  _dataUrlCache.set(id, dataUrl);
  _dataUrlCacheChars += dataUrl.length;
  while (_dataUrlCache.size > MAX_CACHE || _dataUrlCacheChars > MAX_CACHE_CHARS) {
    const lru = _dataUrlCache.keys().next().value;
    if (lru === undefined) break;
    const evicted = _dataUrlCache.get(lru);
    _dataUrlCache.delete(lru);
    if (evicted !== undefined) _releaseCachedUrl(evicted);
  }
}

export function makeObjectUrl(bytes: Uint8Array, mime: string): string {
  const copy = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(copy).set(bytes);
  const url = URL.createObjectURL(new Blob([copy], { type: mime || 'image/jpeg' }));
  _objectUrls.add(url);
  return url;
}

export function resetThumbnailCache(): void {
  for (const url of _objectUrls) URL.revokeObjectURL(url);
  _objectUrls.clear();
  _deferredRevokeUrls.clear();
  _dataUrlCache.clear();
  _dataUrlCacheChars = 0;
  if (_revokeSweepTimer !== null) {
    clearTimeout(_revokeSweepTimer);
    _revokeSweepTimer = null;
  }
}

function _releaseCachedUrl(url: string): void {
  _dataUrlCacheChars -= url.length;
  if (!url.startsWith('blob:')) return;
  _tryRevokeObjectUrl(url);
}

function _tryRevokeObjectUrl(url: string): void {
  if (!_objectUrls.has(url)) return;
  const imgs = document.querySelectorAll<HTMLImageElement>(
    `img.result-image[src="${CSS.escape(url)}"]`,
  );
  if (imgs.length > 0) {
    _deferredRevokeUrls.add(url);
    for (const img of imgs) {
      if (!img.complete) {
        const cleanup = (): void => _tryRevokeObjectUrl(url);
        img.addEventListener('load', cleanup, { once: true });
        img.addEventListener('error', cleanup, { once: true });
      }
    }
    _scheduleRevokeSweep();
    return;
  }
  URL.revokeObjectURL(url);
  _objectUrls.delete(url);
  _deferredRevokeUrls.delete(url);
}

function _scheduleRevokeSweep(): void {
  if (_revokeSweepTimer !== null) return;
  if (_deferredRevokeUrls.size === 0) return;
  _revokeSweepTimer = setTimeout(() => {
    _revokeSweepTimer = null;
    for (const url of Array.from(_deferredRevokeUrls)) {
      _tryRevokeObjectUrl(url);
    }
    if (_deferredRevokeUrls.size > 0) _scheduleRevokeSweep();
  }, REVOKE_SWEEP_INTERVAL_MS);
}

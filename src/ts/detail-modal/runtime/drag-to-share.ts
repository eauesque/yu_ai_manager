/**
 * drag-to-share.ts
 *
 * Drag-to-share for modal images.
 *
 * Since .modal-image has pointer-events: none (for pan/zoom), the img's own
 * dragstart does not fire. Instead, the parent .modal-image-stage is made
 * draggable and the image URL is set on dataTransfer during dragstart.
 *
 * Limitations:
 * - File drag from web browser to native apps is not possible
 *   (DownloadURL is unsupported in modern browsers, items.add(File) doesn't work natively)
 * - Use the Tauri desktop version if native file transfer is needed
 * - This implementation only provides URL text sharing (text/uri-list, text/plain)
 */

/** Last prefetched image cache */
let _cachedBlob: Blob | null = null;
let _cachedUrl = '';
let _cachedFilename = '';
let _cachedMime = '';
let _installedStage: HTMLElement | null = null;

/**
 * Initialize drag-to-share for modal images.
 * Called after each showDetail rendering completes.
 */
export function initDragToShare(): void {
  const img = document.getElementById('modalImage') as HTMLImageElement | null;
  if (!img || !(img instanceof HTMLImageElement)) return;

  // Make the parent stage draggable (since .modal-image has pointer-events: none)
  const stage = img.closest('.modal-image-stage') as HTMLElement | null;
  if (!stage) return;

  stage.draggable = true;

  // Start prefetch when image loading is complete
  if (img.complete && img.naturalWidth > 0) {
    _prefetch(img);
  } else {
    img.addEventListener('load', () => _prefetch(img), { once: true });
  }

  // Remove listener from previous stage (prevent duplicates during navigation)
  if (_installedStage && _installedStage !== stage) {
    _installedStage.removeEventListener('dragstart', _onDragStart);
  }
  if (_installedStage !== stage) {
    stage.addEventListener('dragstart', _onDragStart);
    _installedStage = stage;
  }
}

/** Prefetch the image and cache it */
async function _prefetch(img: HTMLImageElement): Promise<void> {
  const url = img.src;
  if (!url || url === _cachedUrl) return;

  _cachedBlob = null;
  _cachedUrl = url;
  _cachedMime = '';

  try {
    const resp = await fetch(url);
    if (!resp.ok) return;
    _cachedBlob = await resp.blob();
    _cachedMime = _cachedBlob.type || '';
    // Determine filename after Blob is obtained (accurately infer extension from MIME)
    _cachedFilename = _resolveFilename(img);
    // Discard if the URL has changed
    if (img.src !== _cachedUrl) {
      _cachedBlob = null;
    }
  } catch {
    // Fallback on network error
    _cachedFilename = _resolveFilename(img);
  }
}

/** Infer file extension from MIME type */
function _mimeToExt(mime: string): string {
  if (mime.includes('jpeg') || mime.includes('jpg')) return '.jpg';
  if (mime.includes('png')) return '.png';
  if (mime.includes('webp')) return '.webp';
  if (mime.includes('gif')) return '.gif';
  if (mime.includes('avif')) return '.avif';
  if (mime.includes('bmp')) return '.bmp';
  return '.png';
}

/** Resolve the filename */
function _resolveFilename(img: HTMLImageElement): string {
  // Get filename from alt text
  const alt = img.alt || '';
  if (alt && alt !== 'Image' && !alt.startsWith('detail.')) {
    const cleaned = alt.replace(/[<>:"/\\|?*]/g, '_');
    if (cleaned.match(/\.\w{3,4}$/)) return cleaned;
  }

  // Infer filename from URL path
  const url = new URL(img.src, location.origin);
  const pathParts = url.pathname.split('/');
  const lastPart = pathParts[pathParts.length - 1];

  // Generate filename for /api/original/<id> paths
  if (url.pathname.includes('/api/original/')) {
    const ext = _mimeToExt(_cachedMime);
    return `image_${lastPart}${ext}`;
  }

  return lastPart || 'image.png';
}

function _onDragStart(e: DragEvent): void {
  if (!e.dataTransfer) return;

  const img = document.getElementById('modalImage') as HTMLImageElement | null;
  const imgUrl = img?.src || _cachedUrl;
  if (!imgUrl) return;

  const absoluteUrl = new URL(imgUrl, location.origin).href;
  const filename = _cachedFilename || 'image.png';

  e.dataTransfer.effectAllowed = 'copy';

  // Set drag image to the image itself (show only the image, not the entire stage)
  if (img) {
    e.dataTransfer.setDragImage(img, 0, 0);
  }

  // URL text sharing: can be dropped into browser text fields, etc.
  e.dataTransfer.setData('text/uri-list', absoluteUrl);
  e.dataTransfer.setData('text/plain', absoluteUrl);

  // Chromium web-to-web: also provide as File if Blob is available
  if (_cachedBlob) {
    try {
      const file = new File([_cachedBlob], filename, { type: _cachedBlob.type });
      e.dataTransfer.items.add(file);
    } catch { /* Firefox: not supported */ }
  }
}

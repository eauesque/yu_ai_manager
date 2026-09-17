/**
 * progress-stack — Shared container for stacking progress bars at screen bottom.
 *
 * Multiple progress bars (scan job, thumbnail preload, etc.) can be active
 * simultaneously. This module ensures they stack vertically instead of
 * overlapping at the same fixed position.
 *
 * When more than MAX_VISIBLE bars are active, excess bars are hidden and
 * a compact overflow badge shows "+N more jobs".
 */

/** Maximum number of progress bars shown simultaneously. */
const MAX_VISIBLE = 2;

let _container: HTMLElement | null = null;
let _observer: MutationObserver | null = null;
let _overflowBadge: HTMLElement | null = null;

/**
 * Return (or lazily create) the #progress-bar-stack container.
 * All `.scan-progress-bar` elements should be appended here.
 */
export function getProgressStack(): HTMLElement {
  if (_container && _container.isConnected) return _container;

  const existing = document.getElementById('progress-bar-stack');
  if (existing) {
    _container = existing;
    _startObserver();
    return existing;
  }

  const el = document.createElement('div');
  el.id = 'progress-bar-stack';
  document.body.appendChild(el);
  _container = el;
  _startObserver();
  return el;
}

/** Base bottom for toast container (matches CSS default). */
const TOAST_BASE_BOTTOM = 62;

function _ensureOverflowBadge(): HTMLElement {
  if (_overflowBadge && _overflowBadge.isConnected) return _overflowBadge;

  const existing = document.getElementById('progress-overflow-badge');
  if (existing) {
    _overflowBadge = existing;
    return existing;
  }

  const badge = document.createElement('div');
  badge.id = 'progress-overflow-badge';
  badge.className = 'progress-overflow-badge';
  badge.style.cssText =
    'position:fixed;left:50%;transform:translateX(-50%);z-index:791;' +
    'background:rgba(0,0,0,0.85);color:#60a5fa;padding:4px 14px;' +
    'border-radius:12px 12px 0 0;font-size:12px;font-weight:600;' +
    'pointer-events:none;opacity:0;transition:opacity .2s ease;' +
    'backdrop-filter:blur(6px);border:1px solid rgba(96,165,250,0.3);border-bottom:none;';
  document.body.appendChild(badge);
  _overflowBadge = badge;
  return badge;
}

/** Known bar height (px) — used as fallback when offsetHeight is 0 (transition). */
const BAR_HEIGHT = 60;

/** Re-calculate bottom offsets for all active bars in the stack. */
function _relayout(): void {
  if (!_container) return;

  const allActive = Array.from(
    _container.querySelectorAll<HTMLElement>('.scan-progress-bar.active'),
  );

  // Split into visible and overflow
  const visible = allActive.slice(0, MAX_VISIBLE);
  const overflow = allActive.slice(MAX_VISIBLE);

  // Position visible bars
  let offset = 0;
  visible.forEach((bar) => {
    bar.style.bottom = offset + 'px';
    bar.style.display = '';
    // offsetHeight can be 0 during CSS transition; use known height as fallback
    const h = bar.offsetHeight || BAR_HEIGHT;
    offset += h;
  });

  // Hide overflow bars
  overflow.forEach((bar) => {
    bar.style.display = 'none';
  });

  // Show/hide overflow badge
  const badge = _ensureOverflowBadge();
  if (overflow.length > 0) {
    badge.textContent = `+${overflow.length} jobs`;
    badge.style.bottom = offset + 'px';
    badge.style.opacity = '1';
    offset += 24; // badge height
  } else {
    badge.style.opacity = '0';
  }

  // Reset bottom for inactive bars so they slide out correctly
  _container.querySelectorAll<HTMLElement>('.scan-progress-bar:not(.active)').forEach((bar) => {
    bar.style.bottom = '';
    bar.style.display = '';
  });

  // Shift toast container above the progress bars
  const toastContainer = document.getElementById('toast-container');
  if (toastContainer) {
    toastContainer.style.bottom = (TOAST_BASE_BOTTOM + offset) + 'px';
  }

  // Add body bottom padding so page content isn't hidden behind bars
  document.body.style.paddingBottom = offset > 0 ? offset + 'px' : '';
}

function _startObserver(): void {
  if (_observer) return;
  if (!_container) return;
  _observer = new MutationObserver(() => {
    // Debounce with rAF
    requestAnimationFrame(_relayout);
  });
  _observer.observe(_container, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class'],
  });
}

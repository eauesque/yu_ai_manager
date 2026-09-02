/**
 * nav/overflow-menu — ⋯ overflow menu for less-used nav utilities.
 *
 * Toggles the overflow popup on button click. Closes on outside click.
 * Shows a badge on ⋯ with the count of visible menu items.
 */

export function initOverflowMenu(): void {
  // On extension pages, the nav DOM may not be ready when the module
  // first executes.  Try immediately, then retry after DOM is ready.
  if (_bindOverflow()) return;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => _bindOverflow(), { once: true });
  } else {
    // DOM already parsed but elements not found — retry on next microtask
    // (covers edge cases where module runs between parse events)
    requestAnimationFrame(() => _bindOverflow());
  }
}

function _bindOverflow(): boolean {
  const btn = document.getElementById('navOverflowBtn');
  const popup = document.getElementById('navOverflowMenu');
  if (!btn || !popup) return false;

  btn.addEventListener('click', (e: Event) => {
    e.stopPropagation();
    const isOpen = popup.style.display !== 'none';
    popup.style.display = isOpen ? 'none' : 'block';
    btn.setAttribute('aria-expanded', String(!isOpen));
  });

  document.addEventListener('click', (e: Event) => {
    const target = e.target as HTMLElement;
    if (!target.closest('.nav-overflow-wrap')) {
      popup.style.display = 'none';
      btn.setAttribute('aria-expanded', 'false');
    }
  });

  updateOverflowBadge(popup);
  return true;
}

/** Count visible (non-divider) items and show badge on ⋯ button. */
function updateOverflowBadge(popup: HTMLElement): void {
  const badge = document.getElementById('navOverflowBadge');
  if (!badge) return;
  const items = popup.querySelectorAll(
    '.nav-overflow-item:not([style*="display:none"]):not([style*="display: none"])',
  );
  if (items.length > 0) {
    badge.textContent = String(items.length);
    badge.style.display = '';
  }
}

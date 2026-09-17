/**
 * nav/extensions-menu — macOS Launchpad-style Extension Launcher.
 *
 * Full-viewport overlay with categorized grid of extension cards.
 * Categories are collapsible (state persisted in localStorage).
 * Search bar filters extensions in real-time.
 * Keyboard shortcut: E (when not typing in an input).
 *
 * Grid construction and search logic are in extensions-menu-grid.ts.
 */

import { navFetchJson } from './utils';
import {
  buildGrid,
  onSearch,
  DEFAULT_CATEGORY_ORDER,
} from './extensions-menu-grid';

import type {
  ExtensionInfo,
  ExtensionsResponse,
} from './extensions-menu-grid';

// Re-export types for backward compatibility
export type {
  ExtensionNavChild,
  ExtensionNav,
  ExtensionInfo,
  ExtensionsResponse,
} from './extensions-menu-grid';
export { DEFAULT_CATEGORY_ORDER, escHtml, escAttr, buildGrid, onSearch } from './extensions-menu-grid';

/* ── Module state ── */

let overlay: HTMLElement | null = null;
let searchInput: HTMLInputElement | null = null;
let bodyEl: HTMLElement | null = null;
let noResults: HTMLElement | null = null;
let cachedData: { extensions: ExtensionInfo[]; categoryOrder: string[] } | null = null;
let isOpen = false;

/* ── DOM construction ── */

function createOverlay(): HTMLElement {
  const el = document.createElement('div');
  el.className = 'ext-launcher-overlay';
  el.innerHTML = `
    <div class="ext-launcher-backdrop"></div>
    <div class="ext-launcher-container">
      <div class="ext-launcher-header">
        <input class="ext-launcher-search" type="text" placeholder="Search extensions\u2026" spellcheck="false" autocomplete="off">
        <button class="ext-launcher-close" aria-label="Close" title="Close (Esc)">\u00D7</button>
      </div>
      <div class="ext-launcher-body">
        <div class="ext-launcher-empty">Loading\u2026</div>
      </div>
      <div class="ext-launcher-no-results">No matching extensions</div>
      <div class="ext-launcher-footer">
        <a href="/extensions">\u2699 Manage Extensions</a>
        <span class="ext-launcher-kbd">E</span>
      </div>
    </div>`;

  // Close handlers
  el.querySelector('.ext-launcher-backdrop')!.addEventListener('click', closeLauncher);
  el.querySelector('.ext-launcher-close')!.addEventListener('click', closeLauncher);

  // Stop clicks inside container from closing
  el.querySelector('.ext-launcher-container')!.addEventListener('click', (e: Event) => {
    e.stopPropagation();
  });

  // Search input
  searchInput = el.querySelector('.ext-launcher-search') as HTMLInputElement;
  searchInput.addEventListener('input', () => {
    if (bodyEl && searchInput && noResults) {
      onSearch(bodyEl, searchInput, noResults);
    }
  });
  searchInput.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Escape') { closeLauncher(); e.preventDefault(); }
    e.stopPropagation(); // prevent nav keyboard shortcuts
  });

  bodyEl = el.querySelector('.ext-launcher-body');
  noResults = el.querySelector('.ext-launcher-no-results');

  document.body.appendChild(el);
  return el;
}

/* ── Open / close ── */

export function openExtensionLauncher(): void {
  if (isOpen) return;
  if (!overlay) overlay = createOverlay();

  isOpen = true;
  overlay.classList.add('open');
  document.body.style.overflow = 'hidden';

  // Close overflow menu if open
  const overflowMenu = document.getElementById('navOverflowMenu');
  if (overflowMenu) overflowMenu.style.display = 'none';

  // Load data if needed
  if (!cachedData) {
    navFetchJson<ExtensionsResponse>('/api/extensions', null, 2, 1500).then((d) => {
      if (!d) {
        if (bodyEl) bodyEl.innerHTML = '<div class="ext-launcher-empty">Failed to load</div>';
        return;
      }
      cachedData = {
        extensions: d.extensions || [],
        categoryOrder: d.category_order || DEFAULT_CATEGORY_ORDER,
      };
      if (bodyEl) {
        buildGrid(cachedData.extensions, cachedData.categoryOrder, bodyEl);
      }
    });
  }

  // Focus search after animation
  setTimeout(() => {
    if (searchInput) { searchInput.value = ''; searchInput.focus(); }
  }, 50);
}

function closeLauncher(): void {
  if (!isOpen || !overlay) return;
  isOpen = false;
  overlay.classList.remove('open');
  document.body.style.overflow = '';

  // Close any children popovers
  if (bodyEl) {
    bodyEl.querySelectorAll('.ext-launcher-card.show-children').forEach((c) => {
      c.classList.remove('show-children');
    });
  }
}

export function toggleLauncher(): void {
  if (isOpen) closeLauncher();
  else openExtensionLauncher();
}

/* ── Init ── */

export function initExtensionsMenu(): void {
  const btn = document.getElementById('navExtBtn');
  if (btn) {
    btn.addEventListener('click', (e: Event) => {
      e.stopPropagation();
      toggleLauncher();
    });
  }

  // Keyboard shortcut: E (when not typing)
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Escape' && isOpen) {
      closeLauncher();
      e.preventDefault();
      return;
    }
    if (e.key.toLowerCase() === 'e' && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if ((e.target as HTMLElement).isContentEditable) return;
      e.preventDefault();
      toggleLauncher();
    }
  });

  // Close on page navigation (view transition support)
  window.addEventListener('pagehide', closeLauncher);
}

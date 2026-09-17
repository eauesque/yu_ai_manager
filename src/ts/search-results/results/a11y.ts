/**
 * results/a11y.ts
 *
 * Accessibility helpers for result cards: ARIA roles, roving tabindex,
 * keyboard guide visibility, and live-region announcements.
 *
 * Converted from runtime-results-a11y.js (bare globals -> named exports).
 */

import { isVirtualScrollActive, vsGetAllIds } from './virtual-scroll-bridge';
import { getAppApi } from '../../shared/browser-apis';

declare const window: Window & {
  tr: (key: string, fallback?: string | Record<string, unknown>) => string;
};

export function getResultCards(): HTMLElement[] {
  const grid = document.getElementById('results');
  if (!grid) return [];
  return Array.from(grid.querySelectorAll<HTMLElement>('.result-card'));
}

export function estimateCardsPerRow(cards: HTMLElement[]): number {
  if (!cards || cards.length <= 1) return 1;
  const firstTop = (cards[0] as HTMLElement).offsetTop;
  let count = 0;
  for (const c of cards) {
    if ((c as HTMLElement).offsetTop !== firstTop) break;
    count++;
  }
  return Math.max(1, count);
}

export function focusResultCardByIndex(index: number): boolean {
  const cards = getResultCards();
  if (!cards.length) return false;
  const i = Math.max(0, Math.min(cards.length - 1, index));
  cards[i].focus({ preventScroll: false });
  cards[i].scrollIntoView({ block: 'nearest', inline: 'nearest' });
  return true;
}

export function setupResultCardA11y(): void {
  const grid = document.getElementById('results');
  const cards = getResultCards();
  if (!cards.length) return;
  if (grid) {
    // Use grid pattern (not listbox) to allow nested interactive elements (WCAG nested-interactive)
    if (!grid.hasAttribute('role')) {
      grid.setAttribute('role', 'grid');
      grid.setAttribute('aria-label', window.tr('a11y.results_list_label', 'Search results'));
    }
  }
  // 280K optimization: skip already-configured cards (detected by role attribute)
  cards.forEach((card, idx) => {
    if (card.getAttribute('role') === 'row' && card.dataset.cardIndex) {
      // Already a11y configured — only update index
      if (card.dataset.cardIndex !== String(idx)) {
        card.dataset.cardIndex = String(idx);
        card.setAttribute('aria-rowindex', String(idx + 1));
        card.id = `result-card-${idx + 1}`;
      }
      return;
    }
    const cardId = `result-card-${idx + 1}`;
    card.id = cardId;
    card.tabIndex = idx === 0 ? 0 : -1;
    card.setAttribute('role', 'row');
    card.setAttribute('aria-selected', idx === 0 ? 'true' : 'false');
    card.setAttribute('aria-rowindex', String(idx + 1));
    card.setAttribute('aria-keyshortcuts', 'Enter Space C M ContextMenu ArrowLeft ArrowRight ArrowUp ArrowDown Home End PageUp PageDown Escape');
    card.dataset.cardIndex = String(idx);
    const img = card.querySelector<HTMLImageElement>('img.result-image');
    const alt = (img?.getAttribute('alt') || '').trim();
    if (alt) card.setAttribute('aria-label', alt);
  });
  if (grid && cards[0] && cards[0].id) grid.setAttribute('aria-activedescendant', cards[0].id);
  getAppApi().updateKeyboardGuideVisibility();
}

export function ensureSingleTabstopOnResultCards(activeCard: HTMLElement | null): void {
  const grid = document.getElementById('results');
  const cards = getResultCards();
  cards.forEach((c) => {
    c.tabIndex = -1;
    c.setAttribute('aria-selected', 'false');
  });
  if (activeCard && cards.includes(activeCard)) {
    activeCard.tabIndex = 0;
    activeCard.setAttribute('aria-selected', 'true');
    if (grid && activeCard.id) grid.setAttribute('aria-activedescendant', activeCard.id);
  } else if (cards[0]) {
    cards[0].tabIndex = 0;
    cards[0].setAttribute('aria-selected', 'true');
    if (grid && cards[0].id) grid.setAttribute('aria-activedescendant', cards[0].id);
  }
}

export function announceResultCardStatus(card: HTMLElement | null): void {
  const el = document.getElementById('resultA11yStatus');
  if (!el || !card) return;
  const cards = getResultCards();
  const idx = cards.indexOf(card);
  if (idx < 0) return;
  // When virtual scroll is active, get total count from DataStore
  const total = isVirtualScrollActive() ? vsGetAllIds().length : cards.length;
  const label = card.getAttribute('aria-label') || '';
  const msg = window.tr('a11y.result_focus', { index: idx + 1, total, label });
  el.textContent = '';
  requestAnimationFrame(() => {
    el.textContent = msg;
  });
}

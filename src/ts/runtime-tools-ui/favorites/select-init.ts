/**
 * favorites/select-init.ts -- Initialization for explorer-style selection.
 * Delegated click handling and rubber-band (rectangle drag) selection.
 */

import {
  isSelectMode, setSelectMode, favSelectToggle, updateCount,
} from './select-actions';

let _lastClickedIndex = -1;

function _ensureSelectMode(): void {
  if (isSelectMode()) return;
  favSelectToggle(); // turns it ON
}

function _getAllCheckboxes(): HTMLInputElement[] {
  return Array.prototype.slice.call(document.querySelectorAll('.fav-select-cb'));
}

function _cardIndexOf(card: HTMLElement): number {
  // Return the index within visible cards in the DOM
  // (only considers cards present in the DOM, even during virtual scroll)
  const cards: HTMLElement[] = Array.prototype.slice.call(
    document.querySelectorAll('.result-card[data-id]'),
  );
  return cards.indexOf(card);
}

/**
 * Initialize selection mode: delegated click on #results grid
 * and rubber-band (rectangle drag) selection.
 */
export function initFavSelect(): void {
  // Delegated click on #results grid
  document.addEventListener('DOMContentLoaded', () => {
    const grid = document.getElementById('results');
    if (!grid) return;

    grid.addEventListener('click', (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      const card = target.closest('.result-card[data-id]') as HTMLElement | null;
      if (!card) return;
      // Let checkbox / fav-btn handle themselves
      if (target.classList.contains('fav-select-cb') || target.classList.contains('card-fav-btn'))
        return;
      // Let prompt-toggle handle itself
      if (target.closest('.prompt-toggle')) return;

      const idx = _cardIndexOf(card);

      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        _ensureSelectMode();
        const cb = card.querySelector('.fav-select-cb') as HTMLInputElement | null;
        if (cb) cb.checked = !cb.checked;
        _lastClickedIndex = idx;
        updateCount();
      } else if (e.shiftKey && _lastClickedIndex >= 0) {
        e.preventDefault();
        _ensureSelectMode();
        const cbs = _getAllCheckboxes();
        const from = Math.min(_lastClickedIndex, idx);
        const to = Math.max(_lastClickedIndex, idx);
        for (let i = from; i <= to; i++) {
          if (cbs[i]) cbs[i].checked = true;
        }
        updateCount();
      } else if (isSelectMode()) {
        // In select mode, plain click toggles checkbox
        const cb2 = card.querySelector('.fav-select-cb') as HTMLInputElement | null;
        if (cb2) cb2.checked = !cb2.checked;
        _lastClickedIndex = idx;
        updateCount();
      }
      // else: normal click -- inline onclick on <img> calls showDetail
    });
  });

  // Rubber-band (rectangle drag) selection on #results grid
  document.addEventListener('DOMContentLoaded', () => {
    const grid = document.getElementById('results');
    if (!grid) return;

    let _dragging = false;
    let _startX = 0;
    let _startY = 0;
    let _band: HTMLElement | null = null;

    grid.addEventListener('mousedown', (e: MouseEvent) => {
      // Only start on blank area of the grid (not on a card)
      if (e.target !== grid && (e.target as HTMLElement).closest('.result-card')) return;
      if (e.button !== 0) return;
      _dragging = true;
      _startX = e.clientX;
      _startY = e.clientY;
      _band = document.createElement('div');
      _band.className = 'fav-rubberband';
      _band.style.left = _startX + 'px';
      _band.style.top = _startY + 'px';
      _band.style.width = '0';
      _band.style.height = '0';
      document.body.appendChild(_band);
      e.preventDefault();
    });

    document.addEventListener('mousemove', (e: MouseEvent) => {
      if (!_dragging || !_band) return;
      const x = Math.min(e.clientX, _startX);
      const y = Math.min(e.clientY, _startY);
      const w = Math.abs(e.clientX - _startX);
      const h = Math.abs(e.clientY - _startY);
      _band.style.left = x + 'px';
      _band.style.top = y + 'px';
      _band.style.width = w + 'px';
      _band.style.height = h + 'px';
    });

    document.addEventListener('mouseup', (e: MouseEvent) => {
      if (!_dragging || !_band) return;
      _dragging = false;
      const bandRect = _band.getBoundingClientRect();
      document.body.removeChild(_band);
      _band = null;

      // Ignore tiny drags (accidental clicks)
      if (bandRect.width < 5 && bandRect.height < 5) return;

      _ensureSelectMode();
      const cards = document.querySelectorAll('.result-card[data-id]');
      // Without Ctrl/Meta, clear existing selection first
      if (!e.ctrlKey && !e.metaKey) {
        _getAllCheckboxes().forEach((cb) => { cb.checked = false; });
      }
      cards.forEach((card) => {
        const r = card.getBoundingClientRect();
        if (
          r.right > bandRect.left &&
          r.left < bandRect.right &&
          r.bottom > bandRect.top &&
          r.top < bandRect.bottom
        ) {
          const cb = card.querySelector('.fav-select-cb') as HTMLInputElement | null;
          if (cb) cb.checked = true;
        }
      });
      updateCount();
    });
  });
}

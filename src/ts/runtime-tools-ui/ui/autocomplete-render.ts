/**
 * ui/autocomplete-render.ts — Tag autocomplete: box positioning and rendering.
 * Converted from runtime-ui-autocomplete-render.js
 */

import { getCaretCoordinates } from '../../shared/caret-position';
import { getAppApi } from '../../shared/browser-apis';

export function positionBox(input: HTMLInputElement, box: HTMLElement): void {
  const rect = input.getBoundingClientRect();
  const caret = getCaretCoordinates(input, input.selectionStart || 0);
  const caretAbsLeft = rect.left + caret.left;
  const caretAbsTop = rect.top + caret.top;
  box.style.left = Math.max(12, caretAbsLeft + window.scrollX) + 'px';
  box.style.top = caretAbsTop + caret.height + window.scrollY + 4 + 'px';
}

export function hideBox(box: HTMLElement): void {
  box.style.display = 'none';
  box.innerHTML = '';
}

export function renderBox(
  input: HTMLInputElement,
  box: HTMLElement,
  items: string[],
  active: number,
): void {
  if (!items.length) {
    hideBox(box);
    return;
  }

  positionBox(input, box);
  const esc: (s: unknown) => string = getAppApi().escapeHtml;

  box.innerHTML = items
    .map((item, idx) => {
      const isActive = idx === active;
      const style = isActive
        ? 'background: rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.25);'
        : 'border:1px solid transparent;';
      return `<div data-idx="${idx}" style="padding:6px 8px;border-radius:8px;cursor:pointer;${style}">${esc(item)}</div>`;
    })
    .join('');
  box.style.display = 'block';
}

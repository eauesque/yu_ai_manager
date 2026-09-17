/**
 * Vim-style editing helpers for text inputs.
 * Provides word-motion, kill-line, and delete-word operations.
 * Converted from static/js/keyboard/power-vim-edit.js
 */

import { getRuntimeInitApi } from '../shared/browser-apis';

/**
 * Move cursor forward to the start of the next word.
 */
function moveCursorToNextWord(el: HTMLInputElement): void {
  const text = el.value;
  let newPos = el.selectionStart ?? 0;
  while (newPos < text.length && /\S/.test(text[newPos])) newPos++;
  while (newPos < text.length && /\s/.test(text[newPos])) newPos++;
  el.setSelectionRange(newPos, newPos);
}

/**
 * Move cursor backward to the start of the previous word.
 */
function moveCursorToPrevWord(el: HTMLInputElement): void {
  const text = el.value;
  const pos = el.selectionStart ?? 0;
  if (pos === 0) return;
  let newPos = pos - 1;
  while (newPos > 0 && /\s/.test(text[newPos])) newPos--;
  while (newPos > 0 && /\S/.test(text[newPos - 1])) newPos--;
  el.setSelectionRange(newPos, newPos);
}

/**
 * Delete the word before the cursor (Ctrl+W style).
 */
function deleteWordBackward(el: HTMLInputElement): void {
  const runtimeInitApi = getRuntimeInitApi();
  const text = el.value;
  const pos = el.selectionStart ?? 0;
  if (pos === 0) return;
  let newPos = pos - 1;
  while (newPos > 0 && /\s/.test(text[newPos])) newPos--;
  while (newPos > 0 && /\S/.test(text[newPos - 1])) newPos--;
  el.value = text.slice(0, newPos) + text.slice(pos);
  el.setSelectionRange(newPos, newPos);
  runtimeInitApi.saveSearchState();
  el.dispatchEvent(new Event('input', { bubbles: true }));
}

/**
 * Handle Alt+key vim-style navigation shortcuts.
 * Keys: w (next word), b (prev word), 0 (line start), $/4 (line end), x (delete char).
 */
export function handleVimNavigation(e: KeyboardEvent, el: HTMLInputElement): void {
  const key = e.key.toLowerCase();
  const pos = el.selectionStart ?? 0;
  const text = el.value;
  switch (key) {
    case 'w':
      e.preventDefault();
      moveCursorToNextWord(el);
      break;
    case 'b':
      e.preventDefault();
      moveCursorToPrevWord(el);
      break;
    case '0':
      e.preventDefault();
      el.setSelectionRange(0, 0);
      break;
    case '4':
    case '$':
      e.preventDefault();
      el.setSelectionRange(text.length, text.length);
      break;
    case 'x':
      e.preventDefault();
      if (pos < text.length) {
        el.value = text.slice(0, pos) + text.slice(pos + 1);
        el.setSelectionRange(pos, pos);
      }
      break;
  }
}

/**
 * Handle Ctrl+key editing shortcuts.
 * Keys: k (kill to end), u (kill line), w (delete prev word).
 */
export function handleCtrlShortcuts(e: KeyboardEvent, el: HTMLInputElement): void {
  const runtimeInitApi = getRuntimeInitApi();
  const key = e.key.toLowerCase();
  const pos = el.selectionStart ?? 0;
  const text = el.value;
  switch (key) {
    case 'k':
      e.preventDefault();
      el.value = text.slice(0, pos);
      el.setSelectionRange(pos, pos);
      runtimeInitApi.saveSearchState();
      el.dispatchEvent(new Event('input', { bubbles: true }));
      break;
    case 'u':
      e.preventDefault();
      el.value = '';
      runtimeInitApi.saveSearchState();
      el.dispatchEvent(new Event('input', { bubbles: true }));
      break;
    case 'w':
      e.preventDefault();
      deleteWordBackward(el);
      break;
  }
}

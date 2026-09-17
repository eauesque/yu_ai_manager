/**
 * ui/autocomplete-core.ts — Tag autocomplete: main binding logic.
 * Converted from runtime-ui-autocomplete-core.js
 */

import { createSuggestBox, getCurrentToken, replaceLastToken, fetchSuggest } from './autocomplete-utils';
import { positionBox, hideBox, renderBox } from './autocomplete-render';
import { bindCommaSpaceFix, bindListMouse, bindKeyboard, bindDismissHandlers } from './autocomplete-events';

export function bindAutocomplete(input: HTMLInputElement | null): void {
  if (!input || input.dataset.suggestBound) return;
  input.dataset.suggestBound = '1';

  bindCommaSpaceFix(input);

  const box = createSuggestBox();
  let items: string[] = [];
  let active = -1;
  let fetchTimer: ReturnType<typeof setTimeout> | null = null;

  const itemsRef = {
    get: (): string[] => items,
    set: (v: string[]): void => { items = v; },
  };
  const activeRef = {
    get: (): number => active,
    set: (v: number): void => { active = v; },
  };

  function hide(): void {
    hideBox(box);
    itemsRef.set([]);
    activeRef.set(-1);
  }

  function render(): void {
    const current = itemsRef.get();
    if (!current.length) return hide();
    renderBox(input!, box, current, activeRef.get());
  }

  async function update(): Promise<void> {
    const token = getCurrentToken(input!);
    if (!token || token.length < 1) return hide();
    try {
      const sugg = await fetchSuggest(token);
      if (getCurrentToken(input!) !== token) return;
      itemsRef.set(sugg.filter(Boolean));
      activeRef.set(itemsRef.get().length ? 0 : -1);
      render();
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === 'AbortError') return;
      hide();
    }
  }

  function pickItem(item: string): void {
    replaceLastToken(input!, item);
  }

  bindListMouse(box, itemsRef, pickItem, hide);
  bindKeyboard(input, box, itemsRef, activeRef, render, pickItem, hide);

  input.addEventListener('input', () => {
    if (fetchTimer) clearTimeout(fetchTimer);
    fetchTimer = setTimeout(update, 220);
  });

  const repositionIfVisible = (): void => {
    if (box.style.display === 'block') positionBox(input!, box);
  };
  bindDismissHandlers(input, box, hide, repositionIfVisible);

  input.addEventListener('focus', () => {
    if (getCurrentToken(input!)) update();
  });
}

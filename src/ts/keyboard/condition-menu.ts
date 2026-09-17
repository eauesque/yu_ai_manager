/**
 * Condition menu keyboard navigation — arrow/Home/End cycling through
 * condition menu buttons when the menu is open and focused.
 * Converted from static/js/keyboard/power-condition-menu.js
 */

/**
 * Set up keyboard navigation within the condition menu.
 * Handles ArrowRight/ArrowDown (next), ArrowLeft/ArrowUp (prev),
 * Home (first), and End (last) button focusing.
 */

import { getConditionBuilderApi } from '../shared/browser-apis';

export function setupConditionMenuKeyboard(): void {
  const conditionBuilderApi = getConditionBuilderApi();
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    const menu = document.getElementById('conditionMenu');
    if (!menu || menu.style.display === 'none') return;

    const activeEl = document.activeElement;
    if (!activeEl || !menu.contains(activeEl)) return;

    const buttons: HTMLButtonElement[] = conditionBuilderApi.getConditionMenuButtons();
    if (!buttons.length) return;

    const idx = buttons.indexOf(activeEl as HTMLButtonElement);
    if (idx < 0) return;

    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      buttons[(idx + 1) % buttons.length].focus();
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      buttons[(idx - 1 + buttons.length) % buttons.length].focus();
    } else if (e.key === 'Home') {
      e.preventDefault();
      buttons[0].focus();
    } else if (e.key === 'End') {
      e.preventDefault();
      buttons[buttons.length - 1].focus();
    }
  });
}

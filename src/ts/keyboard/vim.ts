/**
 * Vim navigation setup — attaches keyboard listeners to search text inputs.
 * Wires together vim-edit (motions/editing) and vim-hint (focus hints).
 * Converted from static/js/keyboard/power-vim.js
 */

import { handleVimNavigation, handleCtrlShortcuts } from './vim-edit';

/** Input IDs that receive vim-style key bindings. */
const TEXT_INPUT_IDS: readonly string[] = ['tagQuery', 'artist', 'inPrompt'];

/**
 * Set up vim-style navigation on all search text inputs.
 * Attaches keydown (Alt+key motion, Ctrl+key editing, Escape clear),
 * focus (show hint), and blur (hide hint) listeners.
 */
export function setupVimNavigation(): void {
  TEXT_INPUT_IDS.forEach((id: string) => {
    const el = document.getElementById(id) as HTMLInputElement | null;
    if (!el) return;

    el.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.altKey && !e.ctrlKey && !e.shiftKey) handleVimNavigation(e, el);
      if (e.ctrlKey && !e.altKey) handleCtrlShortcuts(e, el);
      if (e.key === 'Escape' && !e.defaultPrevented) {
        e.preventDefault();
        el.blur();
      }
    });

  });
}

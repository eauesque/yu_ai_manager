import { isKeyboardPowerActive } from '../shared/runtime-state/keyboard-state';
import { getNavApi } from '../shared/browser-apis';

/**
 * nav/keyboard — Non-index global keyboard shortcuts.
 *
 * On the index page, power-global.js provides a comprehensive handler.
 * This minimal handler covers all other pages:
 *   - '/' — navigate to search page
 *   - 'L' — activate quick lock
 *
 * Skips if power-global.js has already loaded (checked via
 * `window.keyboardPowerGlobal`).
 */

const TYPEABLE_TAGS = ['INPUT', 'TEXTAREA', 'SELECT'];
let _navGlobalKeyboardBound = false;

/** Check whether the active element is a text-input-like element. */
function isTyping(): boolean {
  const active = document.activeElement;
  if (!active) return false;
  return (
    TYPEABLE_TAGS.indexOf(active.tagName) >= 0 ||
    (active as HTMLElement).isContentEditable
  );
}

/** Initialize non-index keyboard shortcuts (idempotent via window flag). */
export function initKeyboard(): void {
  if (_navGlobalKeyboardBound) return;
  _navGlobalKeyboardBound = true;
  const navApi = getNavApi();

  document.addEventListener('keydown', (e: KeyboardEvent) => {
    // Skip if power-global.js already loaded (index page)
    if (isKeyboardPowerActive()) return;

    if (isTyping()) return;

    // '/' — navigate to search page
    if (e.key === '/' && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      window.location.href = '/';
      return;
    }

    // 'L' — activate quick lock
    if (
      e.key.toLowerCase() === 'l' &&
      !e.altKey &&
      !e.metaKey &&
      !e.shiftKey
    ) {
      e.preventDefault();
      navApi.activateQuickLockFromNav();
    }
  });
}

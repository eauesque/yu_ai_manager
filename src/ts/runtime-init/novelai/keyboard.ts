/**
 * Keyboard hint bar for detail modal navigation.
 *
 * The full-width hint bar (.keyboard-hint-bar) is no longer shown because
 * the modal already contains a compact keyboard guide (.modal-kbd-guide)
 * with the same information.  The functions remain as no-ops so that
 * existing callers (closeModal, window bridges) don't break.
 */

// eslint-disable-next-line @typescript-eslint/no-empty-function
export function showKeyboardHint(): void {}

export function hideKeyboardHint(): void {
  // Defensively hide if an element was created by a prior session/version
  const hint = document.getElementById('keyboardHint');
  if (hint) hint.classList.remove('active');
}

/**
 * Previously monkey-patched window.showDetail — now a no-op.
 */
// eslint-disable-next-line @typescript-eslint/no-empty-function
export function initKeyboardHint(): void {}

/**
 * Keyboard hint bar — DEPRECATED.
 * Bottom-of-viewport hint bar has been merged into the search-area
 * shortcut hint (#shortcutHintInline). These exports are kept as
 * no-ops so that existing callers don't need changes at import time.
 */

/** @deprecated No-op. Hints are now shown inline near the search field. */
export function showInputHint(_inputId: string): void { /* no-op */ }

/** @deprecated No-op. */
export function hideInputHint(): void { /* no-op */ }

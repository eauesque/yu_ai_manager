/**
 * Global keyboard shortcuts — document-level key bindings.
 * Handles /, ?, Escape, Ctrl+Enter, L/Ctrl+L, and Ctrl+Shift+A.
 * Converted from static/js/keyboard/power-global.js
 */

import { getAppApi, getConditionBuilderApi, getContainerViewApi, getNavApi, getRuntimeInitApi } from '../shared/browser-apis';

/** Tag names whose focus state counts as "typing in a form field". */
const TYPING_TAGS: readonly string[] = ['INPUT', 'TEXTAREA', 'SELECT'];

/**
 * Determine whether the active element is a text-input or editable region.
 */
function isTypingContext(active: Element | null): boolean {
  if (!active) return false;
  return (
    TYPING_TAGS.includes(active.tagName) ||
    (active as HTMLElement).isContentEditable
  );
}

/**
 * Register all global keyboard shortcuts on the document.
 */
export function setupGlobalKeyboardShortcuts(): void {
  const conditionBuilderApi = getConditionBuilderApi();
  const containerViewApi = getContainerViewApi();
  const navApi = getNavApi();
  const appApi = getAppApi();
  const runtimeInitApi = getRuntimeInitApi();
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    const active = document.activeElement;
    const isTyping = isTypingContext(active);

    // "/" — focus search
    if (e.key === '/' && !isTyping && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      runtimeInitApi.openSearchOrModal();
    }

    // "?" — toggle keyboard help
    if (e.key === '?' && !isTyping && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      window.keyboardHelpApi?.show?.();
    }

    // Ctrl+Shift+A — open condition menu
    if (e.ctrlKey && e.shiftKey && (e.key === 'A' || e.key === 'a')) {
      e.preventDefault();
      conditionBuilderApi.setLastConditionTriggerEl(
        document.getElementById('addConditionBtn') || document.activeElement as HTMLElement,
      );
      conditionBuilderApi.openConditionMenu({ focusFirst: true });
    }

    // Escape — cascading dismiss
    if (e.key === 'Escape') {
      if (window.keyboardHelpApi?.isVisible?.()) {
        e.preventDefault();
        window.keyboardHelpApi?.hide?.();
      } else if (document.getElementById('conditionMenu')?.style.display !== 'none') {
        e.preventDefault();
        conditionBuilderApi.closeConditionMenu({ restoreFocus: true });
      } else if (document.getElementById('searchModal')?.style.display === 'flex') {
        e.preventDefault();
        runtimeInitApi.closeSearchModal();
      } else if (containerViewApi.isContainerViewOpen()) {
        e.preventDefault();
        containerViewApi.closeContainerViewPanel();
      } else if (document.querySelector('.regex-intro-overlay[style*="flex"]')) {
        const overlay = document.querySelector('.regex-intro-overlay') as HTMLElement | null;
        if (overlay) overlay.style.display = 'none';
      } else if (active?.classList?.contains('result-card')) {
        e.preventDefault();
        const q = document.getElementById('tagQuery') as HTMLInputElement | null;
        if (q && typeof q.focus === 'function') {
          q.focus();
          try {
            conditionBuilderApi.announceA11yStatus(appApi.tr('a11y.focus_search'));
          } catch (_) {
            // intentionally empty
          }
        } else if (active && typeof (active as HTMLElement).blur === 'function') {
          (active as HTMLElement).blur();
        }
      } else if (isTyping && active?.id === 'tagQuery') {
        e.preventDefault();
        (active as HTMLElement).blur();
      }
    }

    // Ctrl+Enter — execute search
    if (e.ctrlKey && e.key === 'Enter') {
      e.preventDefault();
      const searchBtn = document.getElementById('searchBtn');
      if (searchBtn) searchBtn.click();
    }

    // \ — toggle sidebar
    if (e.key === '\\' && !isTyping && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      const collapseBtn = document.getElementById('csCollapseBtn');
      if (collapseBtn) collapseBtn.click();
    }

    // L or Ctrl+L — screen lock
    const isPlainL = e.key.toLowerCase() === 'l' && !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey;
    const isCtrlL = e.key.toLowerCase() === 'l' && e.ctrlKey && !e.altKey && !e.shiftKey;
    if ((isPlainL && !isTyping) || isCtrlL) {
      e.preventDefault();
      navApi.activateQuickLockFromNav();
    }
  });
}

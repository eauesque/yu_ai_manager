/**
 * Regex cheat sheet dock — keyboard shortcuts.
 *
 * Registers global keydown listeners for:
 *   Ctrl+/ (or Cmd+/)  — toggle dock
 *   Escape             — close dock (when open)
 *   Ctrl+Alt+O         — toggle keyboard-details section
 *   Alt+Arrow/Home/End/PgUp/PgDn — horizontal scroll (when dock is open)
 */

import { toggleDock, closeDock, toggleKbDetails } from './state';

/* ------------------------------------------------------------------ */
/*  DOM helper                                                        */
/* ------------------------------------------------------------------ */

function $(id: string): HTMLElement | null {
  return document.getElementById(id);
}

/* ------------------------------------------------------------------ */
/*  Constants                                                         */
/* ------------------------------------------------------------------ */

const SCROLL_STEP  = 260;
const SCROLL_MICRO =  70;

/* ------------------------------------------------------------------ */
/*  Bind hotkeys (idempotent — only binds once)                       */
/* ------------------------------------------------------------------ */

export function bindCheatDockHotkeys(): void {
  if (document.body.dataset.cheatHotkeysBound) return;
  document.body.dataset.cheatHotkeysBound = '1';

  document.addEventListener(
    'keydown',
    (e: KeyboardEvent): void => {
      const panel   = $('regexCheatPanel');
      const scroller = $('regexCheatScroller');
      if (!panel || !scroller) return;

      /* --- Ctrl/Cmd + / : toggle dock --- */
      const isCtrlOrCmd = e.ctrlKey || e.metaKey;
      if (
        isCtrlOrCmd &&
        (e.code === 'Slash' ||
         e.code === 'IntlRo' ||
         e.code === 'NumpadDivide' ||
         e.key === '/' ||
         e.key === '?' ||
         e.key === '\uFF0F' ||   // fullwidth solidus
         e.key === '\uFF1F')     // fullwidth question mark
      ) {
        e.preventDefault();
        toggleDock();
        return;
      }

      /* --- Escape : close dock --- */
      if (panel.classList.contains('open') && e.key === 'Escape') {
        e.preventDefault();
        closeDock(false);
        return;
      }

      /* --- Ctrl+Alt+O : toggle keyboard-details --- */
      if (
        e.ctrlKey && e.altKey && !e.shiftKey &&
        (e.code === 'KeyO' || e.key === 'o' || e.key === 'O')
      ) {
        e.preventDefault();
        toggleKbDetails();
        return;
      }

      /* Remaining shortcuts require the dock to be open */
      if (!panel.classList.contains('open')) return;

      /* Skip when focus is in an editable control */
      const t   = e.target as HTMLElement | null;
      const tag = t?.tagName?.toLowerCase() ?? '';
      if (tag === 'input' || tag === 'textarea' || t?.isContentEditable) return;

      /* --- Alt+Arrow / Home / End / PgUp / PgDn : horizontal scroll --- */
      if (e.altKey && !e.ctrlKey && !e.metaKey) {
        let dx = 0;
        switch (e.code) {
          case 'ArrowLeft':  dx = -(e.shiftKey ? SCROLL_MICRO : SCROLL_STEP); break;
          case 'ArrowRight': dx =   e.shiftKey ? SCROLL_MICRO : SCROLL_STEP;  break;
          case 'Home':       dx = -99999;          break;
          case 'End':        dx =  99999;          break;
          case 'PageUp':     dx = -SCROLL_STEP * 2; break;
          case 'PageDown':   dx =  SCROLL_STEP * 2; break;
          default:           return;
        }
        scroller.scrollBy({ left: dx, behavior: 'smooth' });
        e.preventDefault();
      }
    },
    { capture: true },
  );
}

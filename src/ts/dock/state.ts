/**
 * Regex cheat sheet dock — state and toggles.
 *
 * Manages open/close state, keyboard-details expansion,
 * and localStorage persistence for the regex cheat panel.
 */

/* ------------------------------------------------------------------ */
/*  DOM helper                                                        */
/* ------------------------------------------------------------------ */

import { safeViewTransition } from '../shared/view-transition';

function $(id: string): HTMLElement | null {
  return document.getElementById(id);
}

/* ------------------------------------------------------------------ */
/*  localStorage keys                                                 */
/* ------------------------------------------------------------------ */

const LS_OPEN = 'regexCheatSheetOpen' as const;
const LS_KB_EXPANDED = 'regexCheatKbExpanded' as const;

/* ------------------------------------------------------------------ */
/*  Regex-mode query                                                  */
/* ------------------------------------------------------------------ */

export function isRegexModeOn(): boolean {
  return !!($('inPromptRegex') as HTMLInputElement | null)?.checked;
}

/* ------------------------------------------------------------------ */
/*  Dock open / close / toggle                                        */
/* ------------------------------------------------------------------ */

export function openDock(): void {
  const panel = $('regexCheatPanel');
  if (!panel) return;
  const doOpen = () => { panel.classList.add('open'); };
  safeViewTransition(doOpen);
  localStorage.setItem(LS_OPEN, '1');
}

export function closeDock(silent?: boolean): void {
  const panel = $('regexCheatPanel');
  if (!panel) return;
  const doClose = () => { panel.classList.remove('open'); };
  safeViewTransition(doClose);
  if (!silent) localStorage.setItem(LS_OPEN, '0');
}

export function toggleDock(): void {
  const panel = $('regexCheatPanel');
  if (!panel) return;
  const open = !panel.classList.contains('open');
  const doToggle = () => { panel.classList.toggle('open', open); };
  safeViewTransition(doToggle);
  localStorage.setItem(LS_OPEN, open ? '1' : '0');
}

/* ------------------------------------------------------------------ */
/*  Keyboard-details expand / collapse                                */
/* ------------------------------------------------------------------ */

function applyKbDetailsState(expanded: boolean): void {
  const details = $('cheatKbDetails');
  const btn = document.querySelector('.cheat-controls-toggle') as HTMLElement | null;
  if (!details || !btn) return;

  const doApply = () => {
    if (expanded) {
      details.classList.remove('is-collapsed');
      btn.setAttribute('aria-expanded', 'true');
      btn.textContent =
        (typeof window.tr === 'function' ? window.tr('conditions.toggle.close') : '') || 'Details \u25BE';
    } else {
      details.classList.add('is-collapsed');
      btn.setAttribute('aria-expanded', 'false');
      btn.textContent =
        (typeof window.tr === 'function' ? window.tr('conditions.toggle.more') : '') || 'Details \u25B8';
    }
  };
  safeViewTransition(doApply);
  localStorage.setItem(LS_KB_EXPANDED, expanded ? '1' : '0');
}

export function toggleKbDetails(): void {
  const details = $('cheatKbDetails');
  if (!details) return;
  const expanded = details.classList.contains('is-collapsed');
  applyKbDetailsState(expanded);
}

/* ------------------------------------------------------------------ */
/*  Restore persisted state on page load                              */
/* ------------------------------------------------------------------ */

export function restoreDockState(): void {
  const open = localStorage.getItem(LS_OPEN) === '1';
  const kbExpanded = localStorage.getItem(LS_KB_EXPANDED) === '1';

  if (open) {
    requestAnimationFrame(() => {
      const panel = $('regexCheatPanel');
      if (panel) panel.classList.add('open');
    });
  }
  applyKbDetailsState(kbExpanded);
}

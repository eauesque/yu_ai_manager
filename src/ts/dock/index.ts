/**
 * Dock entry point — regex cheat sheet dock bundle.
 */

import {
  isRegexModeOn,
  openDock,
  closeDock,
  toggleDock,
  toggleKbDetails,
  restoreDockState,
} from './state';
import './hotkeys';
import './scroller';
import './resize';
import { initCheatDockInteractions } from './interactions';
import { installWindowApi } from '../shared/window-api';

/* ================================================================== */
/*  Boot: restore persisted state + wire interactions + bind button    */
/* ================================================================== */

function initCheatDock(): void {
  restoreDockState();
  initCheatDockInteractions();

  const btn = document.getElementById('regexCheatBtn');
  if (btn) {
    btn.addEventListener('click', (e: Event): void => {
      e.preventDefault();
      toggleDock();
    });
  }
}

installWindowApi('dockApi', {
  toggleRegexCheatDock: toggleDock,
  closeRegexCheatDock: () => closeDock(false),
  toggleCheatKbDetails: toggleKbDetails,
  isRegexModeOn,
});

/* ================================================================== */
/*  Register load-time init                                           */
/* ================================================================== */

window.addEventListener('load', initCheatDock);

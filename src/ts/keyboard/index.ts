/**
 * keyboard entry point — bootstraps all keyboard modules.
 */

import { keyboardHelpApi, showKeyboardHelp, hideKeyboardHelp } from './help';
import './vim-edit';
import { setupVimNavigation } from './vim';
import { setupGlobalKeyboardShortcuts } from './global-shortcuts';
import { setupConditionMenuKeyboard } from './condition-menu';
import { installWindowApi } from '../shared/window-api';
import { setKeyboardPowerActive } from '../shared/runtime-state/keyboard-state';

// --- window.* bridges (onclick handlers) ---

// Help overlay
installWindowApi('keyboardApi', {
  keyboardHelpApi,
  showKeyboardHelp,
  hideKeyboardHelp,
}, {
  keyboardHelpApi: 'keyboardHelpApi',
  showKeyboardHelp: 'showKeyboardHelp',
  hideKeyboardHelp: 'hideKeyboardHelp',
});

// Flag for nav/keyboard.ts to detect index page (full keyboard module active)
setKeyboardPowerActive(true);

// --- Initialize ---
setupVimNavigation();
setupGlobalKeyboardShortcuts();
setupConditionMenuKeyboard();

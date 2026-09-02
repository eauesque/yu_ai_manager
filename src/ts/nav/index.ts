/**
 * nav entry point — Initializes all navigation bar subsystems.
 *
 * This bundle replaces the inline <script> in templates/_nav.html.
 * It runs synchronously on page load so that the theme applies before
 * the first paint (no FOUC).
 *
 * Window globals exposed:
 *   - window.navApi.logoutFromNav       — async logout handler
 *   - window.navApi.activateQuickLockFromNav — async quick-lock handler
 */

import { initTrustedTypes } from './trusted-types';
import { initEventDelegation } from './event-delegation';
import { installCsrfFetchInterceptor } from './csrf-fetch';
import { initTheme } from './theme';
import { initHamburger } from './hamburger';
import { logoutFromNav, activateQuickLockFromNav } from './auth';
import { initKeyboard } from './keyboard';
import { initOverflowMenu } from './overflow-menu';
import { initLockVisibility } from './lock-visibility';
import { sseSubscribe, sseUnsubscribe } from '../sse';
import { initTimezone } from '../shared/date-format';
import { initSoundEngine } from '../sound';
import { initAgentKillButton } from './agent-kill';
import { initJobProgress } from './job-progress';
import { showToast } from '../shared/toast';
import { installGlobalErrorReporter, openErrorReportModal } from '../shared/error-reporter';
import { installWindowApi } from '../shared/window-api';
import { initAgentJournalBadge } from './agent-badge';
import { initExtensionsMenuLazy, initKonamiLazy, initTextareaDragLazy, openExtensionLauncher } from './lazy-load';
import { enhanceJsonEditor, initJsonEditorEnhance } from '../shared/json-editor-enhance';

// i18n — loaded in nav.js so every page (including extension pages) gets translations
import '../i18n/tr-shim';
import '../i18n/core-shared';
import '../i18n/core';
import '../i18n/init';

declare global {
  interface Window {
    logoutFromNav: typeof logoutFromNav;
    activateQuickLockFromNav: typeof activateQuickLockFromNav;
    openExtensionLauncher: () => void | Promise<void>;
    sseSubscribe: typeof sseSubscribe;
    sseUnsubscribe: typeof sseUnsubscribe;
    showToast: typeof showToast;
    enhanceJsonEditor: typeof enhanceJsonEditor;
  }
}

/* ------------------------------------------------------------------ */
/*  Window bridges: functions used by inline onclick handlers          */
/* ------------------------------------------------------------------ */

// Focus search field or navigate to index page
function navSearchFocus(): void {
  const q = document.getElementById('tagQuery');
  if (q) {
    q.focus();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else {
    window.location.href = '/';
  }
}

installWindowApi('navApi', {
  logoutFromNav,
  activateQuickLockFromNav,
  openExtensionLauncher,
  navSearchFocus,
  openErrorReportModal,
  sseSubscribe,
  sseUnsubscribe,
  showToast,
  enhanceJsonEditor,
}, {
  // Legacy aliases: used by extension inline scripts
  sseSubscribe: 'sseSubscribe',
  sseUnsubscribe: 'sseUnsubscribe',
  showToast: 'showToast',
  enhanceJsonEditor: 'enhanceJsonEditor',
});

/* ------------------------------------------------------------------ */
/*  Initialize all subsystems (runs on parse, before DOMContentLoaded) */
/* ------------------------------------------------------------------ */

// Trusted Types — must be before any DOM manipulation
initTrustedTypes();

// Event delegation — replaces inline onclick/onchange/oninput handlers
initEventDelegation();

// CSRF protection — must be before any fetch calls
installCsrfFetchInterceptor();

// Global client-side error reporter
installGlobalErrorReporter();

// Theme must be first — prevents flash of wrong theme
initTheme();

// Hamburger menu
initHamburger();

// Konami code easter egg (loaded only after a relevant key sequence starts)
initKonamiLazy();

// Non-index keyboard shortcuts (/, L)
initKeyboard();

// Nav overflow (⋯) menu
initOverflowMenu();

// Extension popup menu (lazy-loaded on first click)
initExtensionsMenuLazy();

// Lock/logout button visibility (async server-info check)
initLockVisibility();

// Textarea drag-and-drop text movement (loaded on first textarea interaction)
initTextareaDragLazy();

// Timezone initialization (all pages, async)
initTimezone();

// Sound effects engine (all pages)
initSoundEngine();

// Agent Kill Switch button (all pages, async)
initAgentKillButton();

// Agent Journal approval badge (all pages, SSE + poll)
initAgentJournalBadge();

// Global job progress bar (all pages, SSE + poll)
initJobProgress();

// JSON editor enhance — bracket colouring + error bar on [data-json-enhance] textareas
initJsonEditorEnhance();

// View Transitions (Chromium only — inserted via JS because @view-transition causes parse errors in Firefox)
if (CSS.supports?.('view-transition-name', 'none')) {
  const vt = document.createElement('style');
  vt.textContent = [
    '@view-transition{navigation:auto}',
    '#fixedNav{view-transition-name:nav-bar}',
    '::view-transition-old(root){animation:vt-fade-out 180ms ease-out}',
    '::view-transition-new(root){animation:vt-fade-in 220ms ease-in}',
    '::view-transition-old(nav-bar),::view-transition-new(nav-bar){animation:none}',
    '@keyframes vt-fade-out{from{opacity:1}to{opacity:0}}',
    '@keyframes vt-fade-in{from{opacity:0}to{opacity:1}}',
  ].join('');
  document.head.appendChild(vt);
}

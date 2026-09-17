/**
 * extensions-page entry point — initializes the extensions management page.
 * Replaces 4 individual <script> tags with one bundled IIFE.
 *
 * Exposes window.* bridges for onclick handlers in templates.
 */

import { extensionApiFetch, extensionEsc } from './api';
import { loadExtensionHooks } from './hooks';
import { toggleExtension, updateExtension, updateAllExtensions, installExtension, uninstallExtension } from './actions';
import { loadExtensions, initExtensionsList } from './list';
import { showPermissionsModal, approveExtPermissions, revokeExtPermissions } from './permissions-modal';
import { installWindowApi } from '../shared/window-api';
import { createPagePerfTracker } from '../shared/page-perf';
const _perf = createPagePerfTracker('extensions');
_perf.markOnce('module_ready');

/* ------------------------------------------------------------------ */
/*  Window bridges: functions used by inline onclick handlers          */
/* ------------------------------------------------------------------ */

installWindowApi('extensionsPageApi', {
  extensionApiFetch,
  extensionEsc,
  loadExtensionHooks,
  toggleExtension,
  updateExtension,
  updateAllExtensions,
  installExtension,
  uninstallExtension,
  loadExtensions,
  showPermissionsModal,
  approveExtPermissions,
  revokeExtPermissions,
});

/* ------------------------------------------------------------------ */
/*  Initialize                                                         */
/* ------------------------------------------------------------------ */

initExtensionsList();

function _observeHooksSection(): void {
  const target = document.getElementById('extensionHooks');
  if (!target) return;
  let loaded = false;
  const run = () => {
    if (loaded) return;
    loaded = true;
    void loadExtensionHooks();
    _perf.markOnce('hooks_started');
  };
  if (typeof IntersectionObserver !== 'function') {
    run();
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      observer.disconnect();
      run();
      break;
    }
  }, {
    rootMargin: '300px 0px',
    threshold: 0.01,
  });
  observer.observe(target);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _observeHooksSection, { once: true });
} else {
  _observeHooksSection();
}

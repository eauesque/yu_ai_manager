/**
 * nav/lock-visibility — Show/hide lock and logout buttons based on PIN config.
 *
 * Queries /api/server-info to check whether a PIN is configured.
 * If so, reveals the lock and logout buttons in the nav bar.
 * Uses resilient fetch to handle transient startup failures.
 */

import { applyServerInfoPayload, loadServerInfo, primeCachedServerInfo } from '../shared/runtime-state/server-info-state';

interface ServerInfo {
  has_pin?: boolean;
  config_has_pin?: boolean;
}

/** Check server PIN config and show lock/logout buttons if enabled. */
export function initLockVisibility(): void {
  const lockBtn = document.getElementById('navLockBtn');
  const logoutBtn = document.getElementById('navLogoutBtn');

  loadServerInfo().then((d) => {
    if (!d) return;
    // Cache for cross-bundle reuse (one-shot, consumed by server-info.ts)
    primeCachedServerInfo(d);
    applyServerInfoPayload(d);
    if (d.has_pin || d.config_has_pin) {
      if (lockBtn) lockBtn.style.display = '';
      if (logoutBtn) logoutBtn.style.display = '';
    } else if (lockBtn) {
      // PIN not configured — show guidance link to Settings
      lockBtn.style.display = '';
      lockBtn.textContent = '\uD83D\uDD10 PIN';
      lockBtn.title = 'Set a PIN in Settings to enable screen lock';
      lockBtn.removeAttribute('data-action');
      lockBtn.addEventListener('click', () => {
        window.location.href = '/settings';
      });
    }
  });
}

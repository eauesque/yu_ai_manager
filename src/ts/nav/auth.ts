/**
 * nav/auth — Logout and quick-lock functions for the navigation bar.
 *
 * Both functions are exposed on `window` by the entry point so that
 * inline `onclick` handlers in _nav.html can call them.
 */

import { getBossLockApi } from '../shared/browser-apis';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

/**
 * Log out the current session and redirect to the PIN page.
 * Falls back to the PIN page even on network failure.
 */
export async function logoutFromNav(): Promise<void> {
  try {
    const res = await fetch('/api/auth/logout', {
      method: 'POST',
      headers: XHR_HEADERS,
    });
    const data: { success?: boolean } = await res.json();
    if (data && data.success) {
      window.location.href = '/_pin';
      return;
    }
  } catch {
    // Network failure — fall through to redirect
  }
  window.location.href = '/_pin';
}

/**
 * Activate quick lock.
 *
 * If `window.bossLockApi.activateQuickLock` is available, delegate
 * to it. Otherwise, attempt the lock API directly. If the server
 * reports that PIN is not configured, redirect to boss mode.
 */
export async function activateQuickLockFromNav(): Promise<void> {
  const bossLockApi = getBossLockApi();
  if (window.bossLockApi?.activateQuickLock) {
    bossLockApi.activateQuickLock();
    return;
  }

  // Non-index pages: try PIN lock API, fall back to boss mode
  try {
    const res = await fetch('/api/lock/activate', {
      method: 'POST',
      headers: XHR_HEADERS,
    });
    let data: { success?: boolean } = {};
    try {
      data = await res.json();
    } catch {
      // JSON parse failure — treat as unsuccessful
    }
    if (res.ok && data && data.success) {
      window.location.reload();
      return;
    }
  } catch {
    // Network failure — fall through to boss mode
  }
  window.location.href = '/?boss=1';
}

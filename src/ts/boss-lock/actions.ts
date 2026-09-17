/**
 * boss-lock / actions — URL query-param activation and PIN-based quick-lock.
 * Converted from static/js/boss-lock/runtime-actions.js
 */

import { stopAllMediaPlayback } from './utils';
import { showBossMode } from './render';
import { getAppApi, getNavApi } from '../shared/browser-apis';
import { getServerInfoHasPin, loadServerInfo, setServerInfoHasPin } from '../shared/runtime-state/server-info-state';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

/* ------------------------------------------------------------------ */
/*  Internal helpers                                                   */
/* ------------------------------------------------------------------ */

/**
 * Check whether the server has a PIN configured for quick-lock.
 * Caches the result in shared server-info state.
 *
 * @returns `true` if PIN is set, `false` if not, `null` on error.
 */
async function hasPinEnabledForQuickLock(): Promise<boolean | null> {
  const cached = getServerInfoHasPin();
  if (typeof cached === 'boolean') return cached;
  try {
    const data = await loadServerInfo(getAppApi().apiFetch);
    if (!data) return null;
    const hasPin = !!data.has_pin;
    setServerInfoHasPin(hasPin);
    return hasPin;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */

/**
 * If the current URL contains `?boss=1`, activate boss mode and strip
 * the query parameter from the address bar.
 */
export function maybeLaunchBossModeFromQuery(): void {
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.get('boss') === '1') {
      showBossMode();
      url.searchParams.delete('boss');
      const next = `${url.pathname}${url.search}${url.hash}`;
      window.history.replaceState({}, '', next);
    }
  } catch {
    // ignore — URL parsing may fail in edge cases
  }
}

/**
 * Quick-lock activation: try PIN lock first, fall back to boss mode.
 *
 * - If no PIN is configured, show boss mode directly.
 * - If PIN lock succeeds (server returns success), reload the page.
 * - If PIN lock fails (400 / PIN error), fall back to boss mode.
 * - On other errors, show a toast warning when possible.
 */
export async function activateQuickLock(): Promise<void> {
  stopAllMediaPlayback();
  const hasPin = await hasPinEnabledForQuickLock();

  if (hasPin === false) {
    showBossMode();
    return;
  }

  try {
    const res  = await fetch('/api/lock/activate', {
      method: 'POST',
      headers: XHR_HEADERS,
    });
    const data = (await res.json().catch(() => ({}))) as { success?: boolean; error?: string };

    if (res.ok && data.success) {
      window.location.reload();
    } else if (res.status === 400 || /PIN/i.test(String(data.error || ''))) {
      showBossMode();
    } else if (data.error) {
      getNavApi().showToast(data.error, true);
    }
  } catch {
    if (!hasPin) showBossMode();
  }
}

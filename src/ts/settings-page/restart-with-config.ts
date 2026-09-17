/**
 * Settings page — unified "save config changes + restart" helper.
 * Used by DB path change, UI theme switch, and profile DB update.
 *
 * In Tauri mode: saves config via API, then uses Tauri IPC to restart Flask
 * (Tauri manages the process lifecycle and re-authenticates automatically).
 * In WebUI mode: saves config and triggers Flask self-restart via API.
 */

import { getAppApi } from '../shared/browser-apis';
import { waitForServerBack } from './security-actions';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

/** Check if running inside Tauri WebView */
function isTauri(): boolean {
  return !!(window as any).__TAURI_INTERNALS__;
}

/**
 * Save config changes and restart the server.
 * Shows progress in #saveStatus element.
 */
export async function restartWithConfig(
  changes: Record<string, string>,
  reason: string,
): Promise<boolean> {
  const status = document.getElementById('saveStatus');

  if (status) status.textContent = '\uD83D\uDD04 ' + reason + '...';

  try {
    // Step 1: Save config changes via API (works in both modes)
    const res = await fetch('/api/server/restart-with-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // In Tauri mode, don't trigger Flask self-restart — just save config
      body: JSON.stringify({
        changes,
        confirm: isTauri() ? 'save_only' : 'restart',
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || 'HTTP ' + res.status);
    }

    // Step 2: Restart
    if (isTauri()) {
      // Tauri mode: use IPC to restart Flask process
      if (status) status.textContent = '\uD83D\uDD04 ' + _t('settings.restart_tauri', 'Restarting server via Tauri...');
      const { invoke } = (window as any).__TAURI_INTERNALS__;
      const restartToken = (window as any).__TAURI_RESTART_TOKEN__ || '';
      await invoke('restart_flask_server', { token: restartToken });
      // Tauri handles navigation + auto-PIN — nothing more to do
      return true;
    } else {
      // WebUI mode: Flask restarts itself, wait and reload
      if (status) status.textContent = '\uD83D\uDD04 ' + _t('settings.restart_waiting', 'Restart accepted. Waiting for server to come back...');
      const back = await waitForServerBack(90000);
      if (back) {
        if (status) status.textContent = '\u2705 ' + _t('settings.restart_back', 'Server is back. Reloading...');
        setTimeout(() => window.location.reload(), 700);
        return true;
      } else {
        if (status) status.textContent = '\u26A0 ' + _t('settings.restart_timeout', 'Restart request sent but server did not respond within 90 seconds.');
        return false;
      }
    }
  } catch (e) {
    if (status) status.textContent = '\u274C ' + _t('settings.config_restart_failed', 'Config change + restart failed') + ': ' + (e instanceof Error ? e.message : String(e));
    return false;
  }
}

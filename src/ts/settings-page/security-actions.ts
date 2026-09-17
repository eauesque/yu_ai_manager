/**
 * Settings page — server restart, lock, wait-for-server, profile switch, RFS calc.
 * Converted from static/js/settings/settings-security-actions.js
 */

import { getAppApi } from '../shared/browser-apis';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export async function quickLockFromSettings(): Promise<void> {
  try {
    const res = await fetch('/api/lock/activate', {
      method: 'POST',
      headers: XHR_HEADERS,
    });
    const data = await res.json();
    if (data.success) {
      window.location.reload();
    } else {
      alert(data.error || _t('settings.failed', 'Failed'));
    }
  } catch (e) {
    alert(_t('settings.lock_failed', 'Lock failed') + ': ' + (e instanceof Error ? e.message : String(e)));
  }
}

export async function waitForServerBack(maxWaitMs = 90000): Promise<boolean> {
  const started = Date.now();
  while (Date.now() - started < maxWaitMs) {
    await new Promise<void>((r) => setTimeout(r, 1500));
    try {
      const r = await fetch('/api/server-info?ts=' + Date.now(), { cache: 'no-store' });
      // 200 = OK, 401 = server is back but needs re-auth (e.g. after PIN restart)
      if (r.ok || r.status === 401) return true;
    } catch {
      // server not yet back
    }
  }
  return false;
}

export async function restartServerFromSettings(): Promise<void> {
  if (!confirm(_t('settings.restart_confirm', 'Restart the server? (inaccessible for a few seconds)'))) return;

  const status = document.getElementById('saveStatus');
  const btn = document.getElementById('restartServerBtn') as HTMLButtonElement | null;
  const token = ((document.getElementById('cfg-server-restart-token') as HTMLInputElement | null)?.value || '').trim();

  if (btn) btn.disabled = true;
  if (status) status.textContent = '\uD83D\uDD04 ' + _t('settings.restart_sending', 'Sending restart request...');

  try {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    };
    if (token) headers['X-Restart-Token'] = token;
    const res = await fetch('/api/server/restart', {
      method: 'POST',
      headers,
      body: JSON.stringify({ confirm: 'restart', restart_token: token || undefined }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || 'HTTP ' + res.status);
    }
    if (status) status.textContent = '\uD83D\uDD04 ' + _t('settings.restart_waiting', 'Restart accepted. Waiting for server to come back...');
    const back = await waitForServerBack(90000);
    if (back) {
      if (status) status.textContent = '\u2705 ' + _t('settings.restart_back', 'Server is back. Reloading...');
      setTimeout(() => window.location.reload(), 700);
    } else {
      if (status) status.textContent = '\u26A0 ' + _t('settings.restart_timeout', 'Restart request sent but server did not respond within 90 seconds.');
    }
  } catch (e) {
    if (status) status.textContent = '\u274C ' + _t('settings.restart_failed', 'Restart failed') + ': ' + (e instanceof Error ? e.message : String(e));
  } finally {
    if (btn) btn.disabled = false;
  }
}

export async function switchProfileFromSettings(name: string, label: string): Promise<void> {
  const msg = _t('settings.profile_switch_confirm', 'Switch to profile "{label}"? The server will restart.').replace('{label}', label);
  if (!confirm(msg)) return;

  const status = document.getElementById('saveStatus');
  if (status) status.textContent = '\uD83D\uDD04 ' + _t('settings.profile_switch_sending', 'Sending profile switch request...');

  try {
    const res = await fetch('/api/server/switch-profile', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ profile: name, confirm: 'switch' }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || 'HTTP ' + res.status);
    }
    if (status) status.textContent = '\uD83D\uDD04 ' + _t('settings.profile_switch_waiting', 'Profile switch accepted. Waiting for server to come back...');
    const back = await waitForServerBack(90000);
    if (back) {
      if (status) status.textContent = '\u2705 ' + _t('settings.profile_switch_back', 'Server is back with new profile. Reloading...');
      setTimeout(() => window.location.reload(), 700);
    } else {
      if (status) status.textContent = '\u26A0 ' + _t('settings.profile_switch_timeout', 'Profile switch request sent but server did not respond within 90 seconds.');
    }
  } catch (e) {
    if (status) status.textContent = '\u274C ' + _t('settings.profile_switch_failed', 'Profile switch failed') + ': ' + (e instanceof Error ? e.message : String(e));
  }
}

export function calcRfsWait(): void {
  const pr = parseInt((document.getElementById('cfg-rfs-probe_retries') as HTMLInputElement | null)?.value || '6') || 6;
  const pw = parseFloat((document.getElementById('cfg-rfs-probe_wait') as HTMLInputElement | null)?.value || '5') || 5;
  const er = parseInt((document.getElementById('cfg-rfs-enumerate_retries') as HTMLInputElement | null)?.value || '5') || 5;
  const ew = parseFloat((document.getElementById('cfg-rfs-enumerate_wait') as HTMLInputElement | null)?.value || '10') || 10;

  let probeTotal = 0;
  for (let i = 0; i < pr - 1; i++) probeTotal += pw * Math.pow(1.5, i);
  let enumTotal = 0;
  for (let i = 0; i < er - 1; i++) enumTotal += ew * (i + 1);

  const total = probeTotal + enumTotal;
  const el = document.getElementById('rfsCalc');
  if (el) {
    el.innerHTML =
      _t('settings.rfs_probe_max', 'Probe max') + ': <b>' + Math.round(probeTotal) + _t('settings.unit_sec', 's') + '</b> + ' +
      _t('settings.rfs_enum_max', 'Enumerate max') + ': <b>' + Math.round(enumTotal) + _t('settings.unit_sec', 's') + '</b> = ' +
      _t('settings.rfs_total_max', 'Total max') + ': <b>' + Math.round(total) + _t('settings.unit_sec', 's') + '</b> (' + (total / 60).toFixed(1) + _t('settings.unit_min', 'min') + ')';
  }
}

export function bindRfsInputs(): void {
  const tab = document.getElementById('tab-remote');
  if (tab) {
    tab.querySelectorAll('input').forEach((el) => el.addEventListener('input', calcRfsWait));
  }
}

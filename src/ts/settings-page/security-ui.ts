/**
 * Settings page — LAN toggle, PIN/restart-token visibility.
 * Converted from static/js/settings/settings-security-ui.js
 */

import { getAppApi } from '../shared/browser-apis';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export function onLanToggle(): void {
  const lanOn = (document.getElementById('cfg-server-lan') as HTMLInputElement | null)?.checked ?? false;
  const hostInput = document.getElementById('cfg-server-host') as HTMLInputElement | null;
  if (hostInput) {
    if (lanOn) {
      hostInput.disabled = false;
      if (hostInput.value === '127.0.0.1') hostInput.value = '0.0.0.0';
    } else {
      hostInput.value = '127.0.0.1';
      hostInput.disabled = true;
    }
  }
  updateLanBadge(lanOn);
}

export function updateLanBadge(lanOn: boolean): void {
  const badge = document.getElementById('lanStatusBadge');
  if (!badge) return;
  if (lanOn) {
    badge.textContent = '\uD83C\uDF10 ' + _t('settings.lan_public', 'LAN Public');
    badge.style.background = 'rgba(231,76,60,0.15)';
    badge.style.color = '#d32f2f';
  } else {
    badge.textContent = '\uD83D\uDD12 ' + _t('settings.local_only', 'Local Only');
    badge.style.background = 'rgba(46,204,113,0.15)';
    badge.style.color = '#166534';
  }
}

export function togglePinVisibilitySetting(): void {
  const inp = document.getElementById('cfg-server-pin') as HTMLInputElement | null;
  const eye = document.getElementById('cfg-pin-eye');
  if (!inp || !eye) return;
  const show = inp.type === 'password';
  inp.type = show ? 'text' : 'password';
  eye.textContent = show ? '\uD83D\uDE48' : '\uD83D\uDC41';
}

export function toggleRestartTokenVisibilitySetting(): void {
  const inp = document.getElementById('cfg-server-restart-token') as HTMLInputElement | null;
  const eye = document.getElementById('cfg-restart-token-eye');
  if (!inp || !eye) return;
  const show = inp.type === 'password';
  inp.type = show ? 'text' : 'password';
  eye.textContent = show ? '\uD83D\uDE48' : '\uD83D\uDC41';
}

export function updatePinSourceNotice(d: { pin_source?: string } | null): void {
  const el = document.getElementById('pinSourceNotice');
  if (!el) return;
  el.style.display = d && d.pin_source === 'cli' ? 'block' : 'none';
}

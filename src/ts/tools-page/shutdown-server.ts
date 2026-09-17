/**
 * shutdown-server.ts -- WebUI server-shutdown button handler.
 *
 * Calls /api/admin/shutdown/info to find out whether the current request is
 * loopback (no PIN needed) or LAN (PIN required). For loopback we ask one
 * confirmation; for LAN we prompt for the boss/approval PIN.
 */

import { getAppApi } from '../shared/browser-apis';
import { apiUrl } from '../shared/api-base';
import { apiFetch } from './api';
import { showToast } from '../shared/toast';
import { customConfirm, customPrompt } from '../shared/dialog';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function _setStatus(text: string, isError = false): void {
  const el = document.getElementById('shutdownStatus');
  if (!el) return;
  el.textContent = text;
  el.style.color = isError ? 'rgba(220,80,80,0.95)' : 'var(--muted,#aab2c0)';
}

interface ShutdownInfo {
  loopback: boolean;
  pin_required: boolean;
}

export async function shutdownServer(): Promise<void> {
  let info: ShutdownInfo;
  try {
    const res = await apiFetch(apiUrl('/api/admin/shutdown/info'));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    info = (json.data || json) as ShutdownInfo;
  } catch (err) {
    showToast(_t('tools.shutdown.info_failed', 'シャットダウン情報の取得に失敗'), true);
    console.warn('[shutdown] info fetch failed:', err);
    return;
  }

  const confirmMsg = _t(
    'tools.shutdown.confirm',
    'サーバーを停止しますか? WebUI は使用できなくなります。',
  );
  if (!(await customConfirm(confirmMsg, { danger: true }))) return;

  let pin = '';
  if (info.pin_required) {
    const promptMsg = _t(
      'tools.shutdown.pin_prompt',
      'LAN 経由のため、ボスモード PIN を入力してください:',
    );
    const entered = await customPrompt(promptMsg, '');
    if (!entered) return;
    pin = entered.trim();
  }

  _setStatus(_t('tools.shutdown.in_progress', 'サーバーを停止しています…'));

  try {
    const res = await apiFetch(apiUrl('/api/admin/shutdown'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pin ? { pin } : {}),
    });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        msg = j.error || j.message || msg;
      } catch { /* ignore */ }
      showToast(`${_t('tools.shutdown.failed', 'シャットダウン失敗')}: ${msg}`, true);
      _setStatus(`${_t('tools.shutdown.failed', 'シャットダウン失敗')}: ${msg}`, true);
      return;
    }
  } catch (err) {
    showToast(_t('tools.shutdown.failed', 'シャットダウン失敗'), true);
    _setStatus(_t('tools.shutdown.failed', 'シャットダウン失敗'), true);
    console.warn('[shutdown] POST failed:', err);
    return;
  }

  // Server is going down — surface a final state and stop further requests.
  showToast(_t('tools.shutdown.success', 'サーバーは停止しました。タブを閉じてください。'));
  _setStatus(_t('tools.shutdown.success', 'サーバーは停止しました。タブを閉じてください。'));
  // Disable the button so it can't be re-clicked.
  document
    .querySelectorAll<HTMLButtonElement>('[data-action="toolsPageApi.shutdownServer"]')
    .forEach((btn) => {
      btn.disabled = true;
      btn.style.opacity = '0.5';
    });
}

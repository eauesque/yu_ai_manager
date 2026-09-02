/**
 * Settings page — save config to API.
 * Converted from static/js/settings/settings-save.js
 */

import { getAppApi } from '../shared/browser-apis';
import { customConfirm } from '../shared/dialog';
import { getEnhanceHandle } from '../shared/json-editor-enhance';
import { getConfig, setConfig, getServerInfo, collectForm, populateForm, type AppConfig } from './config-form';
import { loadServerStatus } from './server-status';

function _t(key: string, fallback: string, replacements?: Record<string, string>): string {
  const raw = getAppApi().tr(key, fallback);
  if (!replacements) return raw;
  return Object.entries(replacements).reduce((s, [k, v]) => s.replaceAll(`{${k}}`, v), raw);
}

function normStr(v: unknown): string {
  return v == null ? '' : String(v).trim();
}

export async function saveSettings(
  uiEls?: { btnId?: string; statusId?: string },
): Promise<{ ok: boolean; msg: string }> {
  const data = collectForm();
  const _config = getConfig();
  const beforeServer = _config.server || {};
  const afterServer = data.server || {};

  const restartReasons: string[] = [];
  if (normStr(beforeServer.host) !== normStr(afterServer.host)) restartReasons.push('host');
  if (parseInt(String(beforeServer.port || 5000)) !== parseInt(String(afterServer.port || 5000))) restartReasons.push('port');
  if (Boolean(beforeServer.lan) !== Boolean(afterServer.lan)) restartReasons.push('lan');

  const beforePin = (beforeServer.pin || '').trim();
  const afterPin = (afterServer.pin || '').trim();
  const beforePinConfigured = Boolean(beforeServer._pin_configured) || beforePin !== '';
  const pinChanged = afterPin !== '' && (!beforePinConfigured || beforePin === '' || beforePin !== afterPin);
  if (pinChanged) restartReasons.push('pin');

  const beforePinBossUi = beforeServer.pin_boss_login_ui !== false;
  const afterPinBossUi = afterServer.pin_boss_login_ui !== false;
  if (beforePinBossUi !== afterPinBossUi) restartReasons.push('pin_boss_login_ui');

  const beforeRemoteRestart = Boolean(beforeServer.allow_remote_restart);
  const afterRemoteRestart = Boolean(afterServer.allow_remote_restart);
  if (beforeRemoteRestart !== afterRemoteRestart) restartReasons.push('allow_remote_restart');

  const beforeRestartToken = (beforeServer.restart_token || '').trim();
  const afterRestartToken = (afterServer.restart_token || '').trim();
  const beforeRestartTokenConfigured = Boolean(beforeServer._restart_token_configured) || beforeRestartToken !== '';
  const restartTokenChanged = afterRestartToken !== '' && (
    !beforeRestartTokenConfigured || beforeRestartToken === '' || beforeRestartToken !== afterRestartToken
  );
  if (restartTokenChanged) restartReasons.push('restart_token');

  const restartNeeded = restartReasons.length > 0;
  const pinCliOverride = getServerInfo().pin_source === 'cli';

  const btn = document.getElementById(uiEls?.btnId ?? 'saveBtn') as HTMLButtonElement | null;
  const status = document.getElementById(uiEls?.statusId ?? 'saveStatus');
  if (btn) btn.disabled = true;
  if (status) status.textContent = _t('settings.saving', 'Saving...');

  let _msg = '';
  try {
    const res = await fetch('/api/settings/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const result = await res.json();
    if (result.status === 'saved') {
      if (status) {
        if (pinChanged && pinCliOverride) {
          _msg = _t('settings.saved_cli_override', 'Saved (CLI --pin takes precedence. Review startup options to apply)');
          status.textContent = _msg;
        } else if (restartNeeded) {
          _msg = _t('settings.saved_restart_needed', 'Saved (restart required to apply)');
          status.textContent = _msg;
        } else {
          _msg = _t('settings.saved', 'Saved');
          status.textContent = _msg;
        }
      } else if (pinChanged && pinCliOverride) {
        _msg = _t('settings.saved_cli_override', 'Saved (CLI --pin takes precedence. Review startup options to apply)');
      } else if (restartNeeded) {
        _msg = _t('settings.saved_restart_needed', 'Saved (restart required to apply)');
      } else {
        _msg = _t('settings.saved', 'Saved');
      }
      const merged = {
        ..._config,
        ...data,
        server: {
          ...(_config.server || {}),
          ...(data.server || {}),
        },
        remote_fs: {
          ...(_config.remote_fs || {}),
          ...(data.remote_fs || {}),
        },
      } as AppConfig;
      setConfig(merged);
      const editor = document.getElementById('jsonEditor') as HTMLTextAreaElement | null;
      if (editor) {
        editor.value = JSON.stringify(merged, null, 2);
        editor.dispatchEvent(new Event('input'));
      }
      await loadServerStatus();
    } else {
      _msg = '\u274C ' + (result.error || _t('settings.save_failed', 'Save failed'));
      if (status) status.textContent = _msg;
    }
    return { ok: result.status === 'saved', msg: _msg };
  } catch (err) {
    _msg = '\u274C ' + (err instanceof Error ? err.message : String(err));
    if (status) status.textContent = _msg;
    return { ok: false, msg: _msg };
  } finally {
    if (btn) btn.disabled = false;
    setTimeout(() => {
      if (status) status.textContent = '';
    }, 3000);
  }
}

export async function saveTomlDirect(): Promise<void> {
  const editorTa = document.getElementById('tomlEditor') as HTMLTextAreaElement | null;
  const raw = editorTa?.value ?? '';
  const status = document.getElementById('save-status-cat-dev');

  if (!(await customConfirm(
    _t('settings.toml_save_confirm', 'config.toml を直接上書きします。不正な TOML を保存するとアプリが起動しなくなる場合があります。保存しますか？'),
    { danger: true },
  ))) return;

  try {
    const res = await fetch('/api/settings/config-toml', {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      body: raw,
    });
    const result = await res.json();
    if (result.status === 'saved') {
      if (status) status.textContent = _t('settings.toml_saved', 'TOML saved');
    } else {
      if (status) status.textContent = '❌ ' + (result.error || _t('settings.save_failed', 'Save failed'));
    }
  } catch (err) {
    if (status) status.textContent = '❌ ' + (err instanceof Error ? err.message : String(err));
  }
  setTimeout(() => { if (status) status.textContent = ''; }, 3000);
}

export async function saveJsonDirect(): Promise<void> {
  const editorTa = document.getElementById('jsonEditor') as HTMLTextAreaElement | null;
  const handle = editorTa ? getEnhanceHandle(editorTa) : undefined;
  const issues = handle?.getValidationIssues() ?? [];

  // Merge validation issues into the existing danger confirm (1 dialog only, never 2)
  const baseMsg = _t(
    'settings.json_save_confirm',
    'config.json を直接上書きします。誤った JSON を保存するとアプリが起動しなくなる場合があります。保存しますか？',
  );
  const msg =
    issues.length > 0
      ? _t('json_doctor.issues_prefix', '{n} issue(s) found:', { n: String(issues.length) }) +
        '\n' +
        issues.map(i => `• ${i.path ? i.path + ': ' : ''}${i.message}`).join('\n') +
        '\n\n' +
        baseMsg
      : baseMsg;

  if (!(await customConfirm(msg, { danger: true }))) return;

  const raw = editorTa?.value ?? '';
  const status = document.getElementById('save-status-cat-dev');
  try {
    const data = JSON.parse(raw) as AppConfig;
    const res = await fetch('/api/settings/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const result = await res.json();
    if (result.status === 'saved') {
      if (status) status.textContent = _t('settings.json_saved', 'JSON saved');
      setConfig(data);
      populateForm();
    }
  } catch (err) {
    if (status)
      status.textContent =
        '\u274C JSON parse error: ' + (err instanceof Error ? err.message : String(err));
  }
  setTimeout(() => {
    if (status) status.textContent = '';
  }, 3000);
}

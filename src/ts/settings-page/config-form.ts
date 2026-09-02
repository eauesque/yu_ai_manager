/**
 * Settings page — form data collection and population.
 * Converted from static/js/settings/settings-config-form.js
 *
 * Manages the _config / _serverInfo global state and provides
 * populateForm() / collectForm() for reading/writing the config UI.
 */

import { getAppApi } from '../shared/browser-apis';
import { updateLanBadge } from './security-ui';
import { calcRfsWait } from './security-actions';

/* ---- shared state ---- */

export interface ServerConfig {
  host?: string;
  port?: number;
  lan?: boolean;
  pin?: string | null;
  _pin_configured?: boolean;
  pin_boss_login_ui?: boolean;
  allow_remote_restart?: boolean;
  restart_token?: string | null;
  _restart_token_configured?: boolean;
}

export interface RemoteFsConfig {
  probe_retries?: number;
  probe_wait?: number;
  enumerate_retries?: number;
  enumerate_wait?: number;
}

export interface AppConfig {
  server?: ServerConfig;
  remote_fs?: RemoteFsConfig;
  extract_a1111?: boolean;
  extract_comfyui?: boolean;
  lowercase_tags?: boolean;
  compute_hash?: boolean;
  enable_fts?: boolean;
  fast_mode_source?: string;
  [key: string]: unknown;
}

export interface ServerInfo {
  pin_source?: string;
  [key: string]: unknown;
}

let _config: AppConfig = {};
let _serverInfo: ServerInfo = {};

export function getConfig(): AppConfig {
  return _config;
}
export function setConfig(c: AppConfig): void {
  _config = c;
}

export function getServerInfo(): ServerInfo {
  return _serverInfo;
}
export function setServerInfo(info: ServerInfo): void {
  _serverInfo = info;
}

/* ---- helpers ---- */

function el<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

/* ---- load / populate / collect ---- */

export async function loadConfig(): Promise<void> {
  try {
    const res = await fetch('/api/settings/config');
    _config = (await res.json()) as AppConfig;
    populateForm();
    const editor = el<HTMLTextAreaElement>('jsonEditor');
    if (editor) {
      editor.value = JSON.stringify(_config, null, 2);
      // Notify the json-editor-enhance overlay to re-sync highlight.
      // Programmatic .value assignment does NOT fire the native 'input' event,
      // so syncHighlight() would never be called without this dispatch.
      editor.dispatchEvent(new Event('input'));
    }
  } catch (err) {
    console.error('Config load failed:', err);
  }
}

interface LegacyMigrationStatus { pending: boolean; keys: string[]; }
interface LegacyMigrationResult { migrated: boolean; merged_keys: string[]; backup: string | null; error: string | null; }

function setLegacyMigrationResult(message: string, isError = false): void {
  const result = el<HTMLParagraphElement>('legacyMigrationResult');
  if (!result) return;
  result.textContent = message;
  result.hidden = false;
  result.style.color = isError ? 'var(--danger)' : 'var(--success)';
}

export async function loadLegacyMigrationStatus(): Promise<void> {
  const section = el<HTMLElement>('legacyMigrationSection');
  if (!section) return;
  try {
    const response = await fetch('/api/settings/config/legacy-migration');
    const status = (await response.json()) as LegacyMigrationStatus;
    section.hidden = !status.pending;
    if (!status.pending) return;
    const keys = el<HTMLElement>('legacyMigrationKeys');
    if (keys) keys.textContent = status.keys.join(', ');
  } catch (err) { console.error('Legacy config migration status load failed:', err); }
}

export async function runLegacyMigration(): Promise<void> {
  if (!confirm(_t('settings.legacy_migration_confirm', 'Import the remaining settings from config.json?'))) return;
  try {
    const response = await fetch('/api/settings/config/legacy-migration', { method: 'POST' });
    const result = (await response.json()) as LegacyMigrationResult;
    if (result.error) { setLegacyMigrationResult(result.error, true); return; }
    const summary = _t('settings.legacy_migration_success', 'Imported settings: {keys}. Backup: {backup}.').replace('{keys}', result.merged_keys.join(', ')).replace('{backup}', result.backup || '—');
    setLegacyMigrationResult(summary);
    await loadLegacyMigrationStatus();
  } catch (err) { console.error('Legacy config migration failed:', err); }
}

export async function loadTomlConfig(): Promise<void> {
  try {
    const res = await fetch('/api/settings/config-toml');
    const text = await res.text();
    const editor = el<HTMLTextAreaElement>('tomlEditor');
    if (editor) {
      editor.value = text;
      editor.dispatchEvent(new Event('input'));
    }
  } catch (err) {
    console.error('TOML config load failed:', err);
  }
}

export function populateForm(): void {
  const c = _config;
  const s = c.server || {};
  const r = c.remote_fs || {};

  const lanOn = s.lan || false;
  const lanCheck = el<HTMLInputElement>('cfg-server-lan');
  if (lanCheck) lanCheck.checked = lanOn;

  const hostInput = el<HTMLInputElement>('cfg-server-host');
  if (hostInput) {
    hostInput.value = lanOn ? s.host || '0.0.0.0' : '127.0.0.1';
    hostInput.disabled = !lanOn;
  }

  const portInput = el<HTMLInputElement>('cfg-server-port');
  if (portInput) portInput.value = String(s.port || 5000);

  const pinInput = el<HTMLInputElement>('cfg-server-pin');
  if (pinInput) {
    const pinValue = s.pin || '';
    const pinConfigured = s._pin_configured === true || pinValue.trim() !== '';
    pinInput.value = pinValue;
    pinInput.placeholder = !pinValue && pinConfigured
      ? _t('settings.pin_pending', 'PIN set (restart required)')
      : '';
    pinInput.title = pinConfigured
      ? 'Leave blank to keep the current PIN'
      : '';
  }

  const pinBossUi = el<HTMLInputElement>('cfg-server-pin-boss-ui');
  if (pinBossUi) pinBossUi.checked = s.pin_boss_login_ui !== false;

  const remoteRestart = el<HTMLInputElement>('cfg-server-allow-remote-restart');
  if (remoteRestart) remoteRestart.checked = s.allow_remote_restart === true;

  const restartToken = el<HTMLInputElement>('cfg-server-restart-token');
  if (restartToken) {
    const restartTokenValue = s.restart_token || '';
    const restartTokenConfigured = s._restart_token_configured === true || restartTokenValue.trim() !== '';
    restartToken.value = restartTokenValue;
    restartToken.placeholder = !restartTokenValue && restartTokenConfigured
      ? _t('settings.token_set', 'Token: set')
      : '';
    restartToken.title = restartTokenConfigured
      ? 'Leave blank to keep the current restart token'
      : '';
  }

  updateLanBadge(lanOn);

  const checks: Array<[string, boolean]> = [
    ['cfg-extract_a1111', c.extract_a1111 !== false],
    ['cfg-extract_comfyui', c.extract_comfyui !== false],
    ['cfg-lowercase_tags', c.lowercase_tags !== false],
    ['cfg-compute_hash', c.compute_hash === true],
    ['cfg-enable_fts', c.enable_fts !== false],
  ];
  for (const [id, val] of checks) {
    const cb = el<HTMLInputElement>(id);
    if (cb) cb.checked = val;
  }

  const rfsFields: Array<[string, number]> = [
    ['cfg-rfs-probe_retries', r.probe_retries || 6],
    ['cfg-rfs-probe_wait', r.probe_wait || 5],
    ['cfg-rfs-enumerate_retries', r.enumerate_retries || 5],
    ['cfg-rfs-enumerate_wait', r.enumerate_wait || 10],
  ];
  for (const [id, val] of rfsFields) {
    const inp = el<HTMLInputElement>(id);
    if (inp) inp.value = String(val);
  }

  const tzSelect = el<HTMLSelectElement>('cfg-timezone');
  if (tzSelect) tzSelect.value = (c as Record<string, unknown>).timezone as string || '';

  const fastModeSelect = el<HTMLSelectElement>('cfg-fast_mode_source');
  if (fastModeSelect) {
    // `fast_mode_build: true` is the setting this replaced and meant
    // "download, and build if that fails" -- the same thing "auto" means now.
    // fast_mode.py reads the legacy key the same way; the two must agree or
    // the form would show a different answer than the launcher acts on.
    const legacyBuild = (c as Record<string, unknown>).fast_mode_build === true;
    const configured = c.fast_mode_source;
    fastModeSelect.value = typeof configured === 'string' && configured
      ? configured
      : (legacyBuild ? 'auto' : 'download');
  }

  calcRfsWait();
}

export function collectForm(): AppConfig {
  const pinVal = (el<HTMLInputElement>('cfg-server-pin')?.value || '').trim();
  const restartTokenVal = (el<HTMLInputElement>('cfg-server-restart-token')?.value || '').trim();
  const lanOn = el<HTMLInputElement>('cfg-server-lan')?.checked || false;

  const tzVal = el<HTMLSelectElement>('cfg-timezone')?.value || '';

  return {
    timezone: tzVal || null,
    server: {
      host: lanOn ? el<HTMLInputElement>('cfg-server-host')?.value || '0.0.0.0' : '127.0.0.1',
      port: parseInt(el<HTMLInputElement>('cfg-server-port')?.value || '5000') || 5000,
      lan: lanOn,
      pin: pinVal || null,
      pin_boss_login_ui: el<HTMLInputElement>('cfg-server-pin-boss-ui')?.checked ?? true,
      allow_remote_restart: el<HTMLInputElement>('cfg-server-allow-remote-restart')?.checked ?? false,
      restart_token: restartTokenVal || null,
    },
    extract_a1111: el<HTMLInputElement>('cfg-extract_a1111')?.checked ?? true,
    extract_comfyui: el<HTMLInputElement>('cfg-extract_comfyui')?.checked ?? true,
    lowercase_tags: el<HTMLInputElement>('cfg-lowercase_tags')?.checked ?? true,
    compute_hash: el<HTMLInputElement>('cfg-compute_hash')?.checked ?? false,
    enable_fts: el<HTMLInputElement>('cfg-enable_fts')?.checked ?? true,
    fast_mode_source: el<HTMLSelectElement>('cfg-fast_mode_source')?.value || 'download',
    remote_fs: {
      probe_retries: parseInt(el<HTMLInputElement>('cfg-rfs-probe_retries')?.value || '6') || 6,
      probe_wait: parseFloat(el<HTMLInputElement>('cfg-rfs-probe_wait')?.value || '5') || 5,
      enumerate_retries: parseInt(el<HTMLInputElement>('cfg-rfs-enumerate_retries')?.value || '5') || 5,
      enumerate_wait: parseFloat(el<HTMLInputElement>('cfg-rfs-enumerate_wait')?.value || '10') || 10,
    },
  };
}

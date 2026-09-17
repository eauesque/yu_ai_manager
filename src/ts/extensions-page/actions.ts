/**
 * Extension actions — toggle, update, install, uninstall operations.
 * Converted from static/js/extensions/extensions-actions.js
 */

import { getAppApi } from '../shared/browser-apis';
import { extensionApiFetch, extensionEsc } from './api';
import { loadExtensions } from './list';

/** i18n helper: use window.tr if available, otherwise return fallback. */
function _t(key: string, fallback: string = ''): string {
  return getAppApi().tr(key, fallback);
}

interface UpdateResult {
  message: string;
  pip?: { status: string; packages?: number };
}

interface UpdateAllResult {
  message: string;
  results?: Array<{
    name: string;
    status: string;
    reason?: string;
  }>;
}

interface InstallResult {
  message: string;
  warning?: string;
  pip?: { status: string; packages?: number };
}

/**
 * Toggle an extension on/off by name.
 */
export async function toggleExtension(name: string): Promise<void> {
  try {
    await extensionApiFetch(`/api/extensions/${encodeURIComponent(name)}/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    loadExtensions();
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    alert(_t('ext.toggle_failed', 'Toggle failed') + ': ' + message);
  }
}

/**
 * Update a single extension by name (git pull + pip install).
 */
export async function updateExtension(name: string): Promise<void> {
  const rb = document.getElementById('extensionResult');
  if (!rb) return;

  rb.classList.add('show');
  rb.innerHTML = `<div style="padding:8px;color:#888;">\uD83D\uDD04 ${extensionEsc(name)} ${_t('ext.updating', 'updating...')}</div>`;

  try {
    const res = await extensionApiFetch(`/api/extensions/${encodeURIComponent(name)}/update`, {
      method: 'POST',
    });
    const data: UpdateResult = await res.json();
    let html = `<div style="padding:8px;color:#2ecc71;">\u2713 ${extensionEsc(data.message)}</div>`;
    if (data.pip) {
      html += `<div style="padding:4px 8px;font-size:11px;color:#888;">pip: ${data.pip.status} (${data.pip.packages || 0} packages)</div>`;
    }
    rb.innerHTML = html;
    loadExtensions();
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    rb.innerHTML = `<div style="padding:8px;color:#e74c3c;">${_t('ext.update_failed', 'Update failed')}: ${extensionEsc(message)}</div>`;
  }
}

/**
 * Update all extensions at once.
 */
export async function updateAllExtensions(): Promise<void> {
  const btn = document.getElementById('updateAllExtBtn') as HTMLButtonElement | null;
  const rb = document.getElementById('extensionResult');
  if (!btn || !rb) return;

  btn.disabled = true;
  btn.textContent = '\uD83D\uDD04 ' + _t('ext.updating', 'updating...');
  rb.classList.add('show');
  rb.innerHTML = '<div style="padding:8px;color:#888;">'
    + _t('ext.updating_all', 'Updating all extensions...') + '</div>';

  try {
    const res = await extensionApiFetch('/api/extensions/update-all', { method: 'POST' });
    const data: UpdateAllResult = await res.json();
    let html = `<div style="padding:8px;"><strong>${extensionEsc(data.message)}</strong></div>`;

    for (const r of data.results || []) {
      const icon = r.status === 'updated' ? '\u2713'
        : r.status === 'unchanged' ? '\u2014'
        : r.status === 'skipped' ? '\u23ED'
        : '\u2717';
      const color = r.status === 'updated' ? '#2ecc71'
        : r.status === 'error' ? '#e74c3c'
        : '#888';
      html += `<div style="padding:2px 8px;font-size:12px;color:${color};">${icon} ${extensionEsc(r.name)}: ${r.status}${r.reason ? ` (${extensionEsc(r.reason)})` : ''}</div>`;
    }

    rb.innerHTML = html;
    loadExtensions();
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    rb.innerHTML = `<div style="padding:8px;color:#e74c3c;">${_t('ext.update_all_failed', 'Bulk update failed')}: ${extensionEsc(message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '\uD83D\uDD04 ' + _t('ext.update_all_btn', 'Update All');
  }
}

/**
 * Install a new extension from a Git URL.
 */
export async function installExtension(): Promise<void> {
  const urlInput = document.getElementById('extensionGitUrl') as HTMLInputElement | null;
  if (!urlInput) return;

  const url = urlInput.value.trim();
  if (!url) {
    alert(_t('ext.enter_url', 'Please enter a Git URL'));
    return;
  }

  const confirmMsg = _t('ext.install_confirm', 'Extensions execute arbitrary code.\nIs this a trusted source?')
    + '\n\nURL: ' + url;
  if (!confirm(confirmMsg)) return;

  const rb = document.getElementById('extensionResult');
  if (!rb) return;

  rb.classList.add('show');
  rb.innerHTML = '<div style="padding:8px;color:#888;">\uD83D\uDCE6 '
    + _t('ext.installing', 'Installing... (git clone + pip install)') + '</div>';

  try {
    const res = await extensionApiFetch('/api/extensions/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data: InstallResult = await res.json();
    let html = `<div style="padding:8px;color:#2ecc71;">\u2713 ${extensionEsc(data.message)}</div>`;
    if (data.warning) {
      html += `<div style="padding:4px 8px;font-size:11px;color:#e67e22;">${extensionEsc(data.warning)}</div>`;
    }
    if (data.pip) {
      html += `<div style="padding:4px 8px;font-size:11px;color:#888;">pip: ${data.pip.status} (${data.pip.packages || 0} packages)</div>`;
    }
    rb.innerHTML = html;
    urlInput.value = '';
    loadExtensions();
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    rb.innerHTML = `<div style="padding:8px;color:#e74c3c;">${_t('ext.install_failed', 'Install failed')}: ${extensionEsc(message)}</div>`;
  }
}

/**
 * Uninstall (delete) an extension by name.
 */
export async function uninstallExtension(name: string): Promise<void> {
  const confirmMsg = _t('ext.uninstall_confirm', 'Delete extension "' + name + '"?\nThis cannot be undone.');
  if (!confirm(confirmMsg)) return;

  try {
    await extensionApiFetch(`/api/extensions/${encodeURIComponent(name)}/uninstall`, {
      method: 'DELETE',
    });
    loadExtensions();
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    alert(_t('ext.uninstall_failed', 'Delete failed') + ': ' + message);
  }
}

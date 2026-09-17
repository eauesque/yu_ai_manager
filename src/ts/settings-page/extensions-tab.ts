/**
 * Settings page — Extensions tab controller.
 * 3 sub-tabs: Installed / Install / Marketplace.
 */

import { getAppApi } from '../shared/browser-apis';
import {
  renderExtensionCard,
  renderMarketplaceCard,
  type ExtensionDetail,
  type MarketplaceEntry,
} from './extensions-card';
import { openConfigModal } from './extensions-config-modal';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function _toast(msg: string): void {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3000);
}

/* ---- Sub-tab switching ---- */

export function switchExtSubTab(panelId: string): void {
  const panels = document.querySelectorAll<HTMLElement>('.ext-sub-panel');
  panels.forEach((p) => (p.style.display = p.id === panelId ? '' : 'none'));

  const btns = document.querySelectorAll<HTMLElement>('.ext-sub-tab');
  btns.forEach((b) => {
    const isActive = b.dataset.panel === panelId;
    b.style.borderBottomColor = isActive ? 'var(--accent)' : 'transparent';
    b.style.color = isActive ? 'var(--accent)' : 'var(--muted)';
  });
}

/* ---- Installed tab ---- */

export async function loadExtensionsFull(): Promise<void> {
  const container = document.getElementById('ext-installed-list');
  if (!container) return;
  container.textContent = _t('common.loading', 'Loading...');

  try {
    const resp = await fetch('/api/extensions');
    const json = await resp.json();
    const exts: ExtensionDetail[] = (json.data?.extensions || json.extensions || []).map(
      (e: Record<string, unknown>) => ({
        name: e.name || e.id || '',
        enabled: !!e.enabled,
        version: e.version || '',
        description: e.description || '',
        author: e.author || '',
        source: e.source || (e.builtin ? 'builtin' : 'local'),
        has_config: !!e.has_config || (e.config_schema != null && typeof e.config_schema === 'object' && Object.keys(e.config_schema as object).length > 0),
      }),
    );

    container.innerHTML = '';
    if (exts.length === 0) {
      container.textContent = _t('settings.no_extensions', 'No extensions installed.');
      return;
    }

    const callbacks = {
      onToggle: toggleExtensionState,
      onConfig: (name: string) => openConfigModal(name),
      onUpdate: updateExtension,
      onUninstall: uninstallExtension,
    };

    for (const ext of exts) {
      container.appendChild(renderExtensionCard(ext, callbacks));
    }
  } catch {
    container.textContent = _t('settings.load_failed', 'Load failed');
  }
}

export async function toggleExtensionState(name: string, enabled: boolean): Promise<void> {
  try {
    const resp = await fetch(`/api/extensions/${encodeURIComponent(name)}/toggle`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ enabled }),
    });
    const json = await resp.json();
    if (!resp.ok) throw new Error(json.error || json.data?.error || `HTTP ${resp.status}`);
    _toast(
      (enabled
        ? _t('settings.ext_enabled_msg', 'Extension enabled.')
        : _t('settings.ext_disabled_msg', 'Extension disabled.')) +
        ' ' +
        _t('settings.ext_restart_required', 'Restart required to apply.'),
    );
    loadExtensionsFull();
  } catch (err) {
    _toast(
      _t('settings.ext_toggle_failed', 'Extension toggle failed') +
        ': ' +
        (err instanceof Error ? err.message : String(err)),
    );
  }
}

export async function updateExtension(name: string): Promise<void> {
  _toast(_t('settings.ext_updating', 'Updating...'));
  try {
    const resp = await fetch(`/api/extensions/${encodeURIComponent(name)}/update`, {
      method: 'POST',
      headers: XHR_HEADERS,
    });
    const json = await resp.json();
    if (!resp.ok) throw new Error(json.error || json.data?.error || `HTTP ${resp.status}`);
    _toast(
      _t('settings.ext_updated', 'Updated') + `: ${name}`,
    );
    loadExtensionsFull();
  } catch (err) {
    _toast(
      _t('settings.ext_update_failed', 'Update failed') +
        ': ' +
        (err instanceof Error ? err.message : String(err)),
    );
  }
}

export async function updateAllExtensions(): Promise<void> {
  _toast(_t('settings.ext_updating_all', 'Updating all extensions...'));
  try {
    const resp = await fetch('/api/extensions/update-all', {
      method: 'POST',
      headers: XHR_HEADERS,
    });
    const json = await resp.json();
    if (!resp.ok) throw new Error(json.error || json.data?.error || `HTTP ${resp.status}`);
    const results = json.data?.results || [];
    const ok = results.filter((r: Record<string, unknown>) => r.success).length;
    const fail = results.length - ok;
    _toast(`${ok} updated, ${fail} failed`);
    loadExtensionsFull();
  } catch (err) {
    _toast(
      _t('settings.ext_update_failed', 'Update failed') +
        ': ' +
        (err instanceof Error ? err.message : String(err)),
    );
  }
}

export async function uninstallExtension(name: string): Promise<void> {
  if (!confirm(_t('settings.ext_uninstall_confirm', `Uninstall extension "${name}"?`))) return;
  try {
    const resp = await fetch(`/api/extensions/${encodeURIComponent(name)}/uninstall`, {
      method: 'DELETE',
      headers: XHR_HEADERS,
    });
    const json = await resp.json();
    if (!resp.ok) throw new Error(json.error || json.data?.error || `HTTP ${resp.status}`);
    _toast(`${name} ${_t('settings.ext_uninstalled', 'uninstalled')}`);
    loadExtensionsFull();
  } catch (err) {
    _toast(
      _t('settings.ext_uninstall_failed', 'Uninstall failed') +
        ': ' +
        (err instanceof Error ? err.message : String(err)),
    );
  }
}

/* ---- Install tab ---- */

export async function installExtension(): Promise<void> {
  const input = document.getElementById('extInstallUrl') as HTMLInputElement | null;
  const status = document.getElementById('extInstallStatus');
  if (!input || !status) return;

  const url = input.value.trim();
  if (!url) {
    _toast(_t('settings.ext_url_required', 'URL is required'));
    return;
  }

  status.style.display = 'block';
  status.style.color = 'var(--muted)';
  status.textContent = _t('settings.ext_installing', 'Installing...');

  try {
    const resp = await fetch('/api/extensions/install', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ url }),
    });
    const json = await resp.json();
    if (resp.ok) {
      status.style.color = '#27ae60';
      status.textContent = _t('settings.ext_install_success', 'Installed successfully. Restart required.');
      input.value = '';
      loadExtensionsFull();
    } else {
      status.style.color = '#dc3545';
      status.textContent = json.error || json.data?.error || 'Install failed';
    }
  } catch {
    status.style.color = '#dc3545';
    status.textContent = _t('settings.ext_install_failed', 'Install request failed');
  }
}

/* ---- Marketplace tab ---- */

export async function searchMarketplace(): Promise<void> {
  const input = document.getElementById('extMarketSearch') as HTMLInputElement | null;
  const container = document.getElementById('ext-marketplace-list');
  if (!container) return;

  const query = input?.value.trim() || '';
  container.textContent = _t('common.loading', 'Loading...');

  try {
    const resp = await fetch(`/api/extensions/marketplace?q=${encodeURIComponent(query)}`);
    const json = await resp.json();
    const entries: MarketplaceEntry[] = json.data?.extensions || json.extensions || [];

    container.innerHTML = '';
    if (entries.length === 0) {
      container.textContent = _t('settings.ext_marketplace_empty', 'No extensions found.');
      return;
    }

    for (const entry of entries) {
      container.appendChild(
        renderMarketplaceCard(entry, (url: string) => _installFromMarketplace(url)),
      );
    }
  } catch {
    container.textContent = _t('settings.ext_marketplace_error', 'Failed to load marketplace.');
  }
}

async function _installFromMarketplace(url: string): Promise<void> {
  _toast(_t('settings.ext_installing', 'Installing...'));
  try {
    const resp = await fetch('/api/extensions/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const json = await resp.json();
    if (resp.ok) {
      _toast(_t('settings.ext_install_success', 'Installed successfully. Restart required.'));
      searchMarketplace();
      loadExtensionsFull();
    } else {
      _toast(json.error || json.data?.error || 'Install failed');
    }
  } catch {
    _toast(_t('settings.ext_install_failed', 'Install request failed'));
  }
}

export async function refreshMarketplace(): Promise<void> {
  _toast(_t('settings.ext_marketplace_refreshing', 'Refreshing marketplace...'));
  try {
    const resp = await fetch('/api/extensions/marketplace/refresh', {
      method: 'POST',
      headers: XHR_HEADERS,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    _toast(_t('settings.ext_marketplace_refreshed', 'Marketplace cache updated'));
    searchMarketplace();
  } catch {
    _toast(_t('settings.ext_marketplace_refresh_failed', 'Refresh failed'));
  }
}

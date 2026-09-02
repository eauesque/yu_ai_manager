/**
 * Settings page — UI management tab.
 * List, switch, install, uninstall custom UIs.
 */

import { getAppApi } from '../shared/browser-apis';
import { restartWithConfig } from './restart-with-config';

interface UiEntry {
  name: string;
  active: boolean;
  manifest: {
    name: string;
    version: string;
    description?: string;
    author?: string;
    label?: string;
    preview_image?: string;
    is_sample?: boolean;
  };
  has_templates: boolean;
  has_static: boolean;
}

/* ---- State ---- */
let _initialized = false;
let _restartAvailable = false;

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

/* ---- Helpers ---- */

function _toast(msg: string): void {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3000);
}

/** Cache restart availability from server-info. */
export function setRestartAvailable(available: boolean): void {
  _restartAvailable = available;
}

/* ---- Load UI list ---- */

export async function loadUiList(): Promise<void> {
  const container = document.getElementById('uiList');
  if (!container) return;

  try {
    const resp = await fetch('/api/ui/list');
    const json = await resp.json();
    if (!json.ok) {
      container.textContent = json.error || 'Failed to load';
      return;
    }
    const uis: UiEntry[] = json.data?.uis ?? [];
    if (uis.length === 0) {
      container.textContent = 'No UIs installed.';
      return;
    }
    renderUiList(container, uis);
  } catch {
    container.textContent = 'Failed to load UI list.';
  }
  _initialized = true;
}

function renderUiList(container: HTMLElement, uis: UiEntry[]): void {
  container.textContent = '';
  // Switch to grid card layout
  container.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px;';

  for (const ui of uis) {
    const label = ui.manifest.label || ui.manifest.name || ui.name;
    const isSample = ui.manifest.is_sample;

    const card = document.createElement('div');
    card.style.cssText = 'border:1px solid rgba(128,128,128,0.2);border-radius:8px;padding:12px;background:var(--card);';

    // Preview image or placeholder
    if (ui.manifest.preview_image) {
      const img = document.createElement('img');
      img.src = `/ui/${ui.name}/${ui.manifest.preview_image}`;
      img.alt = `${label} preview`;
      img.style.cssText = 'width:100%;height:120px;object-fit:cover;border-radius:4px;margin-bottom:8px;background:rgba(128,128,128,0.1);display:block;';
      img.onerror = () => { img.style.display = 'none'; };
      card.appendChild(img);
    } else {
      const placeholder = document.createElement('div');
      placeholder.style.cssText = 'height:120px;border-radius:4px;background:rgba(128,128,128,0.1);display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:12px;margin-bottom:8px;';
      placeholder.textContent = 'No preview';
      card.appendChild(placeholder);
    }

    // Title row with badges
    const titleRow = document.createElement('div');
    titleRow.style.cssText = 'font-weight:600;font-size:13px;';
    titleRow.textContent = label;

    if (ui.active) {
      const activeBadge = document.createElement('span');
      activeBadge.style.cssText = 'font-size:10px;padding:2px 6px;border-radius:3px;background:rgba(22,163,74,0.15);color:#16a34a;margin-left:6px;';
      activeBadge.textContent = '使用中';
      titleRow.appendChild(activeBadge);
    }
    if (isSample) {
      const sampleBadge = document.createElement('span');
      sampleBadge.style.cssText = 'font-size:10px;padding:2px 6px;border-radius:3px;background:rgba(245,158,11,0.15);color:#d97706;margin-left:6px;';
      sampleBadge.textContent = 'サンプル';
      titleRow.appendChild(sampleBadge);
    }
    card.appendChild(titleRow);

    // Meta: name + version + author
    const meta = document.createElement('div');
    meta.style.cssText = 'font-size:11px;color:var(--muted);margin-top:2px;';
    const metaParts: string[] = [`${ui.name} v${ui.manifest.version}`];
    if (ui.manifest.author) metaParts.push(ui.manifest.author);
    meta.textContent = metaParts.join(' — ');
    card.appendChild(meta);

    // Description
    if (ui.manifest.description) {
      const desc = document.createElement('div');
      desc.style.cssText = 'font-size:11px;color:var(--muted);margin-top:4px;';
      desc.textContent = ui.manifest.description;
      card.appendChild(desc);
    }

    // Action buttons
    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;gap:6px;margin-top:8px;';

    if (!ui.active) {
      const switchBtn = document.createElement('button');
      switchBtn.setAttribute('data-action', 'settingsPageApi.switchUi');
      switchBtn.setAttribute('data-action-arg', ui.name);
      switchBtn.setAttribute('data-i18n', 'settings.ui_switch');
      switchBtn.textContent = '切り替え';
      switchBtn.style.cssText = 'padding:4px 12px;border:1px solid rgba(128,128,128,0.3);border-radius:4px;background:none;color:var(--text);cursor:pointer;font-size:12px;';
      switchBtn.onclick = () => switchUi(ui.name);
      actions.appendChild(switchBtn);
    }

    if (ui.name !== 'default') {
      const delBtn = document.createElement('button');
      delBtn.setAttribute('data-action', 'settingsPageApi.uninstallUi');
      delBtn.setAttribute('data-action-arg', ui.name);
      delBtn.textContent = 'Uninstall';
      delBtn.style.cssText = 'padding:4px 12px;border:1px solid rgba(220,53,69,0.3);border-radius:4px;background:none;color:#dc3545;cursor:pointer;font-size:12px;';
      delBtn.onclick = () => uninstallUi(ui.name);
      actions.appendChild(delBtn);
    }

    if (actions.children.length > 0) {
      card.appendChild(actions);
    }

    container.appendChild(card);
  }
}

/* ---- Switch UI ---- */

async function switchUi(name: string): Promise<void> {
  try {
    const resp = await fetch('/api/ui/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    const json = await resp.json();
    if (json.ok || json.data?.restart_required) {
      loadUiList();
      // Offer auto-restart if available
      if (_restartAvailable) {
        const msg = _t('settings.ui_switch_restart_confirm', 'UI switched to "{name}". Restart now to apply?').replace('{name}', name);
        if (confirm(msg)) {
          await restartWithConfig({ ui: name }, _t('settings.ui_switching', 'Switching UI theme'));
          return;
        }
      }
      _toast(_t('settings.ui_switch_restart_required', 'UI switched. Restart required to apply.'));
    } else {
      _toast(json.error || 'Switch failed');
    }
  } catch {
    _toast('Failed to switch UI');
  }
}

/* ---- Install UI ---- */

export async function installUi(): Promise<void> {
  const input = document.getElementById('uiInstallUrl') as HTMLInputElement | null;
  const status = document.getElementById('uiInstallStatus');
  if (!input || !status) return;

  const url = input.value.trim();
  if (!url) {
    _toast('URL is required');
    return;
  }

  status.style.display = 'block';
  status.style.color = 'var(--muted)';
  status.textContent = 'Installing...';

  try {
    const resp = await fetch('/api/ui/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const json = await resp.json();
    if (json.ok || json.data?.name) {
      status.style.color = '#27ae60';
      status.textContent = `Installed "${json.data?.name || 'UI'}" successfully.`;
      input.value = '';
      loadUiList();
    } else {
      status.style.color = '#dc3545';
      status.textContent = json.error || 'Install failed';
    }
  } catch {
    status.style.color = '#dc3545';
    status.textContent = 'Install request failed';
  }
}

/* ---- Uninstall UI ---- */

async function uninstallUi(name: string): Promise<void> {
  if (!confirm(`Uninstall UI "${name}"?`)) return;

  try {
    const resp = await fetch(`/api/ui/${encodeURIComponent(name)}/uninstall`, {
      method: 'DELETE',
    });
    const json = await resp.json();
    if (json.ok || json.data?.uninstalled) {
      _toast(`UI "${name}" uninstalled.`);
      loadUiList();
    } else {
      _toast(json.error || 'Uninstall failed');
    }
  } catch {
    _toast('Failed to uninstall UI');
  }
}

/* ---- Init ---- */

export function initUiTab(): void {
  if (!_initialized) {
    loadUiList();
  }
}

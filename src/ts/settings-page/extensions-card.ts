/**
 * Settings page — Extension card rendering.
 * createElement-based DOM construction (no innerHTML) to avoid XSS.
 */

import { getAppApi } from '../shared/browser-apis';

export interface ExtensionDetail {
  name: string;
  enabled: boolean;
  version?: string;
  description?: string;
  author?: string;
  source?: string;       // "builtin" | "git" | "local"
  has_config?: boolean;
  config_schema?: unknown;
}

export interface MarketplaceEntry {
  name: string;
  description?: string;
  author?: string;
  version?: string;
  url?: string;
  installed?: boolean;
}

export interface CardCallbacks {
  onToggle: (name: string, enabled: boolean) => void;
  onConfig: (name: string) => void;
  onUpdate: (name: string) => void;
  onUninstall: (name: string) => void;
}

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function _el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  style?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  if (style) el.style.cssText = style;
  if (text != null) el.textContent = text;
  return el;
}

function _btn(
  label: string,
  style: string,
  onClick: () => void,
): HTMLButtonElement {
  const btn = _el('button', style, label);
  btn.type = 'button';
  btn.onclick = onClick;
  return btn;
}

function _sourceBadge(source: string): HTMLSpanElement {
  const colors: Record<string, string> = {
    builtin: 'rgba(128,128,128,0.6)',
    git: '#27ae60',
    local: '#3498db',
  };
  const color = colors[source] || 'var(--muted)';
  return _el(
    'span',
    `display:inline-block;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:600;background:${color};color:#fff;margin-left:6px;`,
    source,
  );
}

function _versionBadge(version: string): HTMLSpanElement {
  return _el(
    'span',
    'display:inline-block;padding:1px 7px;border-radius:4px;font-size:10px;font-weight:500;background:rgba(128,128,128,0.15);color:var(--muted);margin-left:6px;',
    `v${version}`,
  );
}

const _btnBase =
  'padding:5px 12px;border-radius:6px;cursor:pointer;font-size:12px;background:transparent;';

export function renderExtensionCard(
  ext: ExtensionDetail,
  callbacks: CardCallbacks,
): HTMLElement {
  const card = _el(
    'div',
    'display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:8px;border:1px solid var(--border);margin-bottom:8px;background:var(--card);',
  );

  // Icon
  card.appendChild(_el('span', 'font-size:20px;flex-shrink:0;', '\uD83E\uDDE9'));

  // Info
  const info = _el('div', 'flex:1;min-width:0;');
  const titleRow = _el('div', 'display:flex;align-items:center;flex-wrap:wrap;');
  titleRow.appendChild(_el('span', 'font-weight:600;font-size:13px;color:var(--text);', ext.name));
  if (ext.version) titleRow.appendChild(_versionBadge(ext.version));
  if (ext.source) titleRow.appendChild(_sourceBadge(ext.source));
  info.appendChild(titleRow);

  if (ext.description) {
    info.appendChild(
      _el('div', 'font-size:11px;color:var(--muted);margin-top:2px;', ext.description),
    );
  }

  // Status
  const statusColor = ext.enabled ? '#2ecc71' : '#d32f2f';
  const statusText = ext.enabled
    ? _t('settings.ext_enabled', 'Enabled')
    : _t('settings.ext_disabled', 'Disabled');
  info.appendChild(
    _el(
      'span',
      `font-size:11px;color:${statusColor};margin-top:2px;display:block;`,
      statusText,
    ),
  );

  card.appendChild(info);

  // Actions
  const actions = _el('div', 'display:flex;gap:6px;flex-shrink:0;flex-wrap:wrap;');

  // Toggle
  const toggleLabel = ext.enabled
    ? _t('settings.ext_disable', 'Disable')
    : _t('settings.ext_enable', 'Enable');
  actions.appendChild(
    _btn(
      toggleLabel,
      `${_btnBase}border:1px solid rgba(128,128,128,0.35);color:var(--text);`,
      () => callbacks.onToggle(ext.name, !ext.enabled),
    ),
  );

  // Config (if schema exists)
  if (ext.has_config) {
    actions.appendChild(
      _btn(
        _t('settings.ext_config', 'Config'),
        `${_btnBase}border:1px solid var(--accent);color:var(--accent);`,
        () => callbacks.onConfig(ext.name),
      ),
    );
  }

  // Update (git only)
  if (ext.source === 'git') {
    actions.appendChild(
      _btn(
        _t('settings.ext_update', 'Update'),
        `${_btnBase}border:1px solid #3498db;color:#3498db;`,
        () => callbacks.onUpdate(ext.name),
      ),
    );
  }

  // Uninstall (non-builtin only)
  if (ext.source !== 'builtin') {
    actions.appendChild(
      _btn(
        _t('settings.ext_uninstall', 'Uninstall'),
        `${_btnBase}border:1px solid rgba(220,53,69,0.5);color:#dc3545;`,
        () => callbacks.onUninstall(ext.name),
      ),
    );
  }

  card.appendChild(actions);
  return card;
}

export function renderMarketplaceCard(
  entry: MarketplaceEntry,
  onInstall: (url: string) => void,
): HTMLElement {
  const card = _el(
    'div',
    'display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:8px;border:1px solid var(--border);margin-bottom:8px;background:var(--card);',
  );

  card.appendChild(_el('span', 'font-size:20px;flex-shrink:0;', '\uD83D\uDCE6'));

  const info = _el('div', 'flex:1;min-width:0;');
  const titleRow = _el('div', 'display:flex;align-items:center;flex-wrap:wrap;');
  titleRow.appendChild(_el('span', 'font-weight:600;font-size:13px;color:var(--text);', entry.name));
  if (entry.version) titleRow.appendChild(_versionBadge(entry.version));
  info.appendChild(titleRow);

  if (entry.description) {
    info.appendChild(
      _el('div', 'font-size:11px;color:var(--muted);margin-top:2px;', entry.description),
    );
  }
  if (entry.author) {
    info.appendChild(
      _el('div', 'font-size:11px;color:var(--muted);', entry.author),
    );
  }
  card.appendChild(info);

  // Actions
  const actions = _el('div', 'display:flex;gap:6px;flex-shrink:0;');
  if (entry.installed) {
    actions.appendChild(
      _el(
        'span',
        'font-size:12px;color:#166534;padding:5px 12px;',
        _t('settings.ext_installed', 'Installed'),
      ),
    );
  } else if (entry.url) {
    actions.appendChild(
      _btn(
        _t('settings.ext_install', 'Install'),
        `${_btnBase}border:1px solid #27ae60;color:#27ae60;`,
        () => onInstall(entry.url!),
      ),
    );
  }

  card.appendChild(actions);
  return card;
}

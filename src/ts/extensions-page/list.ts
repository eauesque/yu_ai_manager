/**
 * Extension list — loads installed extensions and renders the main list.
 * Grouped by category with collapsible sections.
 */

import { getAppApi } from '../shared/browser-apis';
import { type HealthInfo, healthReasonText, renderHealthBadge } from '../shared/extension-health';
import { extensionApiFetch, extensionEsc } from './api';

function renderHealthReasonRow(health: HealthInfo | null | undefined): string {
  if (!health || health.available) return '';
  const reason = healthReasonText(health);
  if (!reason) return '';
  return `<div style="font-size:11px;color:#9a3412;margin-bottom:4px;padding:4px 8px;background:rgba(230,126,34,0.10);border-radius:4px;">⚠️ ${extensionEsc(reason)}</div>`;
}

function getExtensionsPageApi(): Record<string, unknown> | null {
  return typeof window.extensionsPageApi === 'object' ? window.extensionsPageApi : null;
}

/** i18n helper: use window.tr if available, otherwise return fallback. */
function _t(key: string, fallback: string = ''): string {
  return getAppApi().tr(key, fallback);
}

interface ExtensionInfo {
  name: string;
  version: string;
  description?: string;
  enabled: boolean;
  status?: string;
  status_message?: string;
  type: string;
  category?: string;
  hooks?: string[];
  priority: number;
  source?: string;
  directory?: string;
  trust_level?: string;
  health?: HealthInfo | null;
}

interface ExtensionsApiResponse {
  extensions?: ExtensionInfo[];
  category_order?: string[];
}

interface StatusDisplay {
  icon: string;
  color: string;
  label: string;
}

const TYPE_ICONS: Record<string, string> = {
  importer: '\uD83D\uDCE5',
  transformer: '\uD83D\uDD04',
  exporter: '\uD83D\uDCE4',
  ui_widget: '\uD83D\uDDBC\uFE0F',
  general: '\uD83E\uDDE9',
};

const CATEGORY_LABELS: Record<string, { icon: string; label: string }> = {
  metadata: { icon: '\uD83D\uDCE5', label: 'Metadata Extractors' },
  ai:       { icon: '\uD83E\uDDE0', label: 'AI / Hardware Acceleration' },
  bridge:   { icon: '\uD83D\uDD17', label: 'Generation Bridges' },
  prompt:   { icon: '\uD83D\uDCDD', label: 'Prompt Tools' },
  library:  { icon: '\uD83D\uDCDA', label: 'Library & Viewer' },
  system:   { icon: '\u2699\uFE0F', label: 'System' },
};

const DEFAULT_CATEGORY_ORDER = ['metadata', 'ai', 'bridge', 'prompt', 'library', 'system'];

const TRUST_BADGES: Record<string, { label: string; color: string; bg: string }> = {
  trusted:   { label: 'L0', color: '#166534', bg: 'rgba(46,204,113,0.12)' },
  verified:  { label: 'L1', color: 'var(--trust-verified-fg,#1e40af)', bg: 'rgba(52,152,219,0.15)' },
  untrusted: { label: 'L2', color: 'var(--trust-untrusted-fg,#b91c1c)', bg: 'rgba(231,76,60,0.15)' },
};

let _delegationBound = false;

function _defer(task: () => void): void {
  const win = window as Window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => void };
  if (typeof win.requestIdleCallback === 'function') {
    win.requestIdleCallback(task, { timeout: 1200 });
    return;
  }
  setTimeout(task, 0);
}

function renderExtensionCard(ext: ExtensionInfo): string {
  const st = ext.status || (ext.enabled ? 'loaded' : 'disabled');

  const statusMap: Record<string, StatusDisplay> = {
    loaded: { icon: '\u2705', color: 'var(--status-ok,#166534)', label: _t('ext.status_ok') || 'OK' },
    disabled: { icon: '\u23F8\uFE0F', color: 'var(--muted,#aab2c0)', label: _t('ext.status_disabled') || 'Disabled' },
    rejected: { icon: '\u274C', color: '#d32f2f', label: 'reject' },
    pending_approval: { icon: '\uD83D\uDD12', color: '#f39c12', label: 'Pending' },
    error: { icon: '\u26A0\uFE0F', color: '#e67e22', label: _t('ext.status_error') || 'Error' },
  };
  const s: StatusDisplay = statusMap[st] || statusMap.loaded;
  const typeLabel = TYPE_ICONS[ext.type] || '\uD83E\uDDE9';
  const isGit = ext.source === 'git' || (ext.directory != null && ext.directory.includes('.git'));
  const isBuiltin = ext.name.startsWith('builtin-');
  const tl = ext.trust_level || 'trusted';
  const trustBadge = TRUST_BADGES[tl] || TRUST_BADGES.trusted;

  const borderColor = st === 'rejected' || st === 'error'
    ? 'rgba(231,76,60,0.3)' : 'rgba(255,255,255,0.06)';

  const hooksHtml = (ext.hooks ?? []).length > 0
    ? (ext.hooks ?? []).map((h) =>
      `<code style="background:rgba(100,100,100,0.25);padding:1px 5px;border-radius:3px;font-size:10px;color:var(--text,#333);">${h}</code>`
    ).join(' ')
    : '<span style="color:var(--muted,#888);">none</span>';

  const toggleTitle = ext.enabled
    ? (_t('ext.disable') || 'Disable')
    : (_t('ext.enable') || 'Enable');
  const toggleIcon = ext.enabled ? '\u23F9' : '\u25B6\uFE0F';

  return `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;margin-bottom:8px;border-radius:8px;background:rgba(0,0,0,0.15);border:1px solid ${borderColor};">
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
          <span style="font-size:18px;">${typeLabel}</span>
          <strong style="font-size:15px;">${extensionEsc(ext.name)}</strong>
          <span style="font-size:11px;color:var(--muted,#aab2c0);">v${extensionEsc(ext.version)}</span>
          <span style="font-size:11px;padding:1px 7px;border-radius:9px;background:${ext.enabled ? 'rgba(46,204,113,0.15)' : 'rgba(100,100,100,0.15)'};color:${ext.enabled ? 'var(--status-ok,#166534)' : 'var(--muted,#aab2c0)'};" title="${extensionEsc(s.label)}">${s.icon} ${extensionEsc(s.label)}</span>
          ${renderHealthBadge(ext.health)}
          ${isBuiltin ? '<span style="font-size:9px;background:rgba(102,126,234,0.2);color:var(--text-secondary,#444);padding:1px 6px;border-radius:8px;">built-in</span>' : ''}
          <span style="font-size:9px;background:${trustBadge.bg};color:${trustBadge.color};padding:1px 6px;border-radius:8px;" title="Trust Level: ${tl}">${trustBadge.label}</span>
        </div>
        ${ext.description ? `<div style="font-size:12px;color:var(--muted,#aab2c0);margin-bottom:4px;">${extensionEsc(ext.description)}</div>` : ''}
        ${ext.status_message ? `<div style="font-size:11px;color:#d32f2f;margin-bottom:4px;padding:4px 8px;background:rgba(231,76,60,0.1);border-radius:4px;">\uD83D\uDCAC ${extensionEsc(ext.status_message)}</div>` : ''}
        ${renderHealthReasonRow(ext.health)}
        <div style="font-size:11px;color:var(--muted,#aab2c0);">
          hooks: ${hooksHtml}
          &nbsp;|&nbsp; priority: ${ext.priority}
          &nbsp;|&nbsp; type: ${ext.type}
        </div>
      </div>
      <div style="display:flex;gap:6px;align-items:center;flex-shrink:0;margin-left:16px;">
        <button class="btn btn-secondary" style="padding:5px 12px;font-size:16px;" data-ext-action="toggle" data-ext-name="${extensionEsc(ext.name)}" title="${toggleTitle}">
          ${toggleIcon}
        </button>
        ${!isBuiltin ? `<button class="btn btn-secondary" style="padding:5px 12px;font-size:12px;" data-ext-action="permissions" data-ext-name="${extensionEsc(ext.name)}" title="Permissions">\uD83D\uDD10</button>` : ''}
        ${isGit ? `<button class="btn btn-secondary" style="padding:5px 12px;font-size:12px;" data-ext-action="update" data-ext-name="${extensionEsc(ext.name)}">\uD83D\uDD04</button>` : ''}
        ${!isBuiltin ? `<button class="btn btn-secondary" style="padding:5px 12px;font-size:12px;color:#d32f2f;" data-ext-action="uninstall" data-ext-name="${extensionEsc(ext.name)}">\uD83D\uDDD1\uFE0F</button>` : ''}
      </div>
    </div>`;
}

/**
 * Load all installed extensions and render into #extensionsList.
 */
export async function loadExtensions(): Promise<void> {
  const container = document.getElementById('extensionsList');
  if (!container) return;

  try {
    const res = await extensionApiFetch('/api/extensions');
    const data: ExtensionsApiResponse = await res.json();

    if (!data.extensions || data.extensions.length === 0) {
      container.innerHTML = `
        <div style="padding:24px;text-align:center;color:var(--muted,#aab2c0);font-size:13px;">
          <div style="font-size:40px;margin-bottom:12px;opacity:0.5;">\uD83E\uDDE9</div>
          ${_t('ext.no_extensions') || 'No extensions installed'}<br>
          <span style="font-size:12px;">${_t('ext.install_hint') || 'Enter a Git URL below to install'}</span>
        </div>`;
      return;
    }

    const categoryOrder = data.category_order || DEFAULT_CATEGORY_ORDER;

    // Group extensions by category
    const grouped = new Map<string, ExtensionInfo[]>();
    for (const ext of data.extensions) {
      const cat = ext.category || '';
      if (!grouped.has(cat)) grouped.set(cat, []);
      grouped.get(cat)!.push(ext);
    }

    const sections: Array<{ key: string; icon: string; label: string; exts: ExtensionInfo[] }> = [];

    // Render known categories in order
    for (const cat of categoryOrder) {
      const exts = grouped.get(cat);
      if (!exts || exts.length === 0) continue;
      grouped.delete(cat);
      const info = CATEGORY_LABELS[cat] || { icon: '\uD83E\uDDE9', label: cat };
      sections.push({ key: cat, icon: info.icon, label: info.label, exts });
    }

    // Render uncategorized extensions (custom extensions without category)
    for (const [cat, exts] of grouped) {
      if (exts.length === 0) continue;
      const label = cat || (_t('ext.uncategorized') || 'Other');
      sections.push({ key: cat || 'other', icon: '\uD83E\uDDE9', label, exts });
    }

    container.innerHTML = '';

    const renderChunk = (startIndex: number): void => {
      const endIndex = Math.min(startIndex + 2, sections.length);
      const fragment = document.createDocumentFragment();
      for (let i = startIndex; i < endIndex; i++) {
        const section = sections[i];
        const wrapper = document.createElement('div');
        wrapper.innerHTML = renderCategorySection(section.key, section.icon, section.label, section.exts);
        while (wrapper.firstChild) fragment.appendChild(wrapper.firstChild);
      }
      container.appendChild(fragment);
      if (endIndex < sections.length) {
        _defer(() => renderChunk(endIndex));
      }
    };
    renderChunk(0);

    // Bind extension action buttons via event delegation (avoid inline onclick XSS)
    if (!_delegationBound) {
      _delegationBound = true;
      container.addEventListener('click', (e) => {
        const btn = (e.target as HTMLElement).closest<HTMLButtonElement>('[data-ext-action]');
        if (!btn) return;
        const action = btn.dataset.extAction;
        const name = btn.dataset.extName;
        if (!name) return;
        const api = getExtensionsPageApi();
        if (action === 'toggle' && typeof api?.toggleExtension === 'function') api.toggleExtension(name);
        else if (action === 'permissions' && typeof api?.showPermissionsModal === 'function') api.showPermissionsModal(name);
        else if (action === 'update' && typeof api?.updateExtension === 'function') api.updateExtension(name);
        else if (action === 'uninstall' && typeof api?.uninstallExtension === 'function') api.uninstallExtension(name);
      });
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    container.innerHTML = `<div style="color:#d32f2f;font-size:13px;">${_t('ext.list_failed') || 'Failed to load extensions'}: ${extensionEsc(message)}</div>`;
  }
}

function renderCategorySection(catKey: string, icon: string, label: string, exts: ExtensionInfo[]): string {
  const sectionId = `ext-cat-${catKey}`;
  return `
    <details open class="ext-category-group" style="margin-bottom:16px;">
      <summary style="cursor:pointer;user-select:none;display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:6px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);margin-bottom:8px;font-size:14px;font-weight:600;color:var(--text,#e7eaf0);">
        <span style="font-size:16px;">${icon}</span>
        ${extensionEsc(label)}
        <span style="font-size:11px;font-weight:400;color:var(--muted,#aab2c0);margin-left:auto;">${exts.length}</span>
      </summary>
      <div id="${sectionId}" style="padding-left:4px;">
        ${exts.map(renderExtensionCard).join('')}
      </div>
    </details>`;
}

/**
 * Initialize extensions list — call on DOMContentLoaded or immediately.
 */
export function initExtensionsList(): void {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { loadExtensions(); });
  } else {
    loadExtensions();
  }
}

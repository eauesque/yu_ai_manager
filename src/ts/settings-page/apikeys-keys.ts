/**
 * apikeys-keys.ts -- API key CRUD operations and key list rendering.
 */

import { getAppApi } from '../shared/browser-apis';
import { apiFetch, escapeHtml } from '../main/api-utils';
import { customPrompt } from '../shared/dialog';
import { copyToClipboard } from '../shared/clipboard';

/* -- Types -- */

export interface ApiKeyEntry {
  id: string;
  key_prefix: string;
  label: string;
  scopes?: string[];
  created_at: number | null;
  last_used_at: number | null;
}

interface CreateKeyResult {
  id: string;
  key: string;
  key_prefix: string;
  label: string;
  scopes?: string[];
  created_at: number;
}

/* -- State (shared with apikeys-mcp.ts via getters) -- */

let _keys: ApiKeyEntry[] = [];
let _createdRawKey = '';

export function getKeys(): ApiKeyEntry[] { return _keys; }
export function getCreatedRawKey(): string { return _createdRawKey; }

/* -- Helpers -- */

export function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function fmtDate(ts: number | null): string {
  if (!ts) return '-';
  const d = new Date(ts * 1000);
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

const SCOPE_I18N_MAP: Record<string, string> = {
  'read': 'settings.scope_read',
  'rate': 'settings.scope_rate',
  'tag.write': 'settings.scope_tag_write',
  'collection.write': 'settings.scope_collection_write',
  'annotate': 'settings.scope_annotate',
  'scan': 'settings.scope_scan',
  'admin': 'settings.scope_admin',
};

function scopeLabel(s: string): string {
  const key = SCOPE_I18N_MAP[s];
  if (key) {
    const translated = _t(key, '');
    if (translated && translated !== key) return translated;
  }
  return s;
}

function scopeBadges(scopes?: string[]): string {
  if (!scopes || scopes.length === 0) {
    return `<span class="ak-badge ak-badge-full">${escapeHtml(_t('settings.apikeys_full_access', 'full access'))}</span>`;
  }
  return scopes.map(s => `<span class="ak-badge" title="${escapeHtml(s)}">${escapeHtml(scopeLabel(s))}</span>`).join(' ');
}

let _toastTimer: ReturnType<typeof setTimeout> | null = null;

export function showToast(msg: string, isError?: boolean): void {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const w = window as any;
  if (typeof w.showToast === 'function') {
    w.showToast(msg, isError);
    return;
  }
  // Inline fallback for pages without main/index.ts
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.style.background = isError ? 'rgba(180,40,40,0.86)' : 'rgba(0,0,0,0.78)';
  el.classList.remove('show');
  void el.offsetWidth;
  el.classList.add('show');
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), isError ? 4500 : 2500);
}

/* -- Render Key List -- */

function renderKeyList(container: HTMLElement): void {
  if (_keys.length === 0) {
    container.innerHTML = '<div style="padding:12px 0;color:var(--muted);font-size:13px;">' + escapeHtml(_t('settings.apikeys_empty', 'No API keys created yet.')) + '</div>';
    return;
  }
  const rows = _keys.map(k => `
    <div class="ak-row">
      <div class="ak-row-main">
        <div class="ak-row-label">${escapeHtml(k.label)}</div>
        <div class="ak-row-meta">
          <code class="ak-prefix">${escapeHtml(k.key_prefix)}...</code>
          ${scopeBadges(k.scopes)}
        </div>
      </div>
      <div class="ak-row-dates">
        <span class="ak-date-label">${escapeHtml(_t('settings.apikeys_created', 'Created:'))}</span> ${fmtDate(k.created_at)}
        <span class="ak-date-sep">|</span>
        <span class="ak-date-label">${escapeHtml(_t('settings.apikeys_last_used', 'Last used:'))}</span> ${fmtDate(k.last_used_at)}
      </div>
      <button class="ak-edit-btn" data-action="settingsPageApi.editApiKeyLabel" data-action-arg="${escapeHtml(k.id)}" title="${escapeHtml(_t('settings.apikeys_edit_label', 'Edit label'))}">✏️</button>
      <button class="ak-delete-btn" data-action="settingsPageApi.deleteApiKey" data-action-arg="${escapeHtml(k.id)}" title="${escapeHtml(_t('settings.apikeys_revoke', 'Revoke this key'))}">&#x2715;</button>
    </div>
  `).join('');
  container.innerHTML = rows;
}

/* -- Load & Render Keys -- */

// Callback set by the MCP module to update its UI after key list changes
let _onKeysLoaded: (() => void) | null = null;
export function setOnKeysLoaded(fn: () => void): void { _onKeysLoaded = fn; }

export async function editApiKeyLabel(keyId: string): Promise<void> {
  const key = _keys.find(k => k.id === keyId);
  if (!key) return;
  const current = key.label || '';
  const newLabel = await customPrompt(_t('settings.apikeys_edit_label_prompt', '新しいラベルを入力してください:'), current);
  if (newLabel === null || newLabel === current) return;
  try {
    const res = await apiFetch(`/api/apikeys/${encodeURIComponent(keyId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label: newLabel.trim() }),
    });
    const data = await res.json();
    if (data.ok) {
      showToast(_t('settings.apikeys_label_updated', 'ラベルを更新しました'));
      await loadApiKeys();
    } else {
      showToast(data.error || 'Failed to update label', true);
    }
  } catch (e) {
    showToast('Failed to update label', true);
  }
}

export async function loadApiKeys(): Promise<void> {
  const container = document.getElementById('apikeysList');
  if (!container) return;
  try {
    const res = await apiFetch('/api/apikeys');
    const data = await res.json();
    _keys = data.keys || [];
    renderKeyList(container);
    _onKeysLoaded?.();
  } catch (e) {
    container.textContent = 'Failed to load API keys';
    console.error('[apikeys] load error:', e);
  }
}

/* -- Create Key -- */

export async function createApiKey(): Promise<void> {
  const labelEl = document.getElementById('ak-label') as HTMLInputElement | null;
  const label = labelEl?.value.trim() || '';

  // Collect checked scopes
  const scopeEls = document.querySelectorAll('#ak-scopes input[type="checkbox"]:checked');
  const scopes: string[] = [];
  scopeEls.forEach(el => scopes.push((el as HTMLInputElement).value));

  const body: Record<string, unknown> = { label };
  if (scopes.length > 0) body.scopes = scopes;

  try {
    const res = await apiFetch('/api/apikeys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data: CreateKeyResult = await res.json();
    _createdRawKey = data.key;

    // Show one-time key
    const panel = document.getElementById('ak-created');
    const keyEl = document.getElementById('ak-created-key');
    if (panel && keyEl) {
      keyEl.textContent = data.key;
      panel.style.display = 'block';
    }

    // Reset form
    if (labelEl) labelEl.value = '';
    document.querySelectorAll('#ak-scopes input[type="checkbox"]').forEach(el => {
      (el as HTMLInputElement).checked = false;
    });

    // Reload list
    await loadApiKeys();
    showToast(_t('settings.apikeys_toast_created', 'API key created'));
  } catch (e) {
    console.error('[apikeys] create error:', e);
    showToast(_t('settings.apikeys_toast_create_failed', 'Failed to create API key'), true);
  }
}

/* -- Copy Created Key -- */

export function copyCreatedKey(): void {
  if (!_createdRawKey) return;
  void copyToClipboard(_createdRawKey).then(() => {
    showToast(_t('settings.apikeys_toast_copied', 'API key copied'));
  });
}

/* -- Delete Key -- */

export async function deleteApiKey(keyId: string): Promise<void> {
  if (!confirm('Revoke this API key? This cannot be undone.')) return;
  try {
    await apiFetch(`/api/apikeys/${encodeURIComponent(keyId)}`, { method: 'DELETE' });
    await loadApiKeys();
    showToast(_t('settings.apikeys_toast_revoked', 'API key revoked'));
  } catch (e) {
    console.error('[apikeys] delete error:', e);
    showToast(_t('settings.apikeys_toast_revoke_failed', 'Failed to revoke API key'), true);
  }
}

/**
 * gateway-keys.ts -- Gateway API key CRUD for the settings page.
 */

import { getAppApi } from '../shared/browser-apis';
import { apiFetch } from '../main/api-utils';
import { copyToClipboard } from '../shared/clipboard';

/* -- Types -- */

interface GatewayKeyEntry {
  id: string;
  scopes: string[];
  allowed_models: string[] | null;
}

interface CreateGatewayKeyResult {
  id: string;
  scopes: string[];
  secret: string;
}

/* -- State -- */

let _gatewayKeys: GatewayKeyEntry[] = [];
let _createdSecret = '';
let _tabInitialized = false;

/* -- Helpers -- */

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function slugify(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

function showToast(msg: string, isError?: boolean): void {
  const w = window as any;
  if (typeof w.showToast === 'function') w.showToast(msg, isError);
}

/* -- Secret management -- */

function _clearSecret(): void {
  _createdSecret = '';
  const el = document.getElementById('gk-created-secret');
  const box = document.getElementById('gk-created');
  if (el) el.textContent = '';
  if (box) (box as HTMLElement).style.display = 'none';
}

/* -- Render key list using DOM API (no innerHTML for user data) -- */

export async function loadGatewayKeys(): Promise<void> {
  const container = document.getElementById('gatewayKeysList');
  if (!container) return;
  try {
    const resp = await apiFetch('/api/gateway/keys');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json() as { keys: GatewayKeyEntry[] };
    _gatewayKeys = data.keys || [];
    _renderKeyList(container);
  } catch {
    container.textContent = _t('gateway_keys.toast_error', 'エラーが発生しました');
  }
}

function _renderKeyList(container: HTMLElement): void {
  container.textContent = '';
  if (_gatewayKeys.length === 0) {
    const span = document.createElement('span');
    span.style.color = 'var(--muted)';
    span.textContent = '—';
    container.appendChild(span);
    return;
  }

  const wildcardKeys = _gatewayKeys.filter(k => k.scopes.includes('*'));

  const table = document.createElement('table');
  table.style.cssText = 'width:100%;border-collapse:collapse;font-size:13px;';

  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  headerRow.style.borderBottom = '1px solid var(--border)';
  ['ID', _t('gateway_keys.scopes_label', 'スコープ'), ''].forEach(text => {
    const th = document.createElement('th');
    th.style.cssText = 'text-align:left;padding:4px 8px;font-size:11px;color:var(--muted);';
    th.textContent = text;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  _gatewayKeys.forEach(k => {
    const tr = document.createElement('tr');

    const tdId = document.createElement('td');
    tdId.style.cssText = 'padding:6px 8px;font-family:monospace;font-size:12px;';
    tdId.textContent = k.id;
    tr.appendChild(tdId);

    const tdScopes = document.createElement('td');
    tdScopes.style.padding = '6px 8px';
    k.scopes.forEach(s => {
      const badge = document.createElement('span');
      badge.className = 'ak-badge';
      badge.title = s;
      badge.textContent = s;
      if (s === '*') badge.style.cssText = 'background:var(--error,#e74c3c);color:#fff;';
      tdScopes.appendChild(badge);
      tdScopes.appendChild(document.createTextNode(' '));
    });
    tr.appendChild(tdScopes);

    const tdDel = document.createElement('td');
    tdDel.style.padding = '6px 8px';
    const isLastWildcard = k.scopes.includes('*') && wildcardKeys.length === 1;
    const btn = document.createElement('button');
    btn.className = 'btn-danger-small';
    btn.dataset['action'] = 'settingsPageApi.deleteGatewayKey';
    btn.dataset['actionArg'] = k.id;
    btn.dataset['isLastWildcard'] = String(isLastWildcard);
    btn.style.cssText = 'padding:3px 8px;font-size:11px;';
    btn.textContent = _t('common.delete', '削除');
    tdDel.appendChild(btn);
    tr.appendChild(tdDel);

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.appendChild(table);
}

/* -- Validation -- */

function _validateCreateForm(): boolean {
  const label = (document.getElementById('gk-label') as HTMLInputElement)?.value ?? '';
  const slug = slugify(label);
  const idError = document.getElementById('gk-id-error') as HTMLElement | null;
  const idExistsError = document.getElementById('gk-id-exists-error') as HTMLElement | null;
  const createBtn = document.getElementById('gk-create-btn') as HTMLButtonElement | null;

  let valid = true;
  if (idError) idError.style.display = slug ? 'none' : 'inline';
  if (!slug) valid = false;

  const isDuplicate = !!slug && _gatewayKeys.some(k => k.id === slug);
  if (idExistsError) idExistsError.style.display = isDuplicate ? 'inline' : 'none';
  if (isDuplicate) valid = false;

  const scopes = _getSelectedScopes();
  if (scopes.length === 0) valid = false;

  if (scopes.includes('*')) {
    const confirmed = (document.getElementById('gk-wildcard-confirm') as HTMLInputElement)?.checked;
    if (!confirmed) valid = false;
  }

  if (createBtn) createBtn.disabled = !valid;
  return valid;
}

function _getSelectedScopes(): string[] {
  const badges = document.querySelectorAll<HTMLButtonElement>('#gk-scopes .gk-scope-badge[aria-pressed="true"]');
  return Array.from(badges).map(b => b.dataset['scope'] ?? '').filter(Boolean);
}

function _updateIdPreview(): void {
  const label = (document.getElementById('gk-label') as HTMLInputElement)?.value ?? '';
  const slug = slugify(label);
  const idValue = document.getElementById('gk-id-value');
  if (idValue) idValue.textContent = slug || '—';
  _validateCreateForm();
}

/* -- Wildcard UX -- */

function _onWildcardSelected(): void {
  document.querySelectorAll<HTMLButtonElement>('#gk-scopes .gk-scope-badge:not(.gk-scope-wildcard)').forEach(b => {
    b.disabled = true;
    b.setAttribute('aria-pressed', 'false');
    b.classList.remove('active');
  });
  const warning = document.getElementById('gk-wildcard-warning') as HTMLElement | null;
  if (warning) warning.style.display = 'block';
}

function _onWildcardDeselected(): void {
  document.querySelectorAll<HTMLButtonElement>('#gk-scopes .gk-scope-badge:not(.gk-scope-wildcard)').forEach(b => {
    b.disabled = false;
  });
  const warning = document.getElementById('gk-wildcard-warning') as HTMLElement | null;
  if (warning) warning.style.display = 'none';
  const confirmEl = document.getElementById('gk-wildcard-confirm') as HTMLInputElement | null;
  if (confirmEl) confirmEl.checked = false;
}

/* -- Create / Delete -- */

export async function createGatewayKey(): Promise<void> {
  if (!_validateCreateForm()) return;
  _clearSecret();

  const label = (document.getElementById('gk-label') as HTMLInputElement)?.value ?? '';
  const keyId = slugify(label);
  const scopes = _getSelectedScopes();

  try {
    const resp = await apiFetch('/api/gateway/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: keyId, scopes, allowed_models: null }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      showToast(data?.error?.message ?? _t('gateway_keys.toast_error', 'エラーが発生しました'), true);
      return;
    }
    const result = data as CreateGatewayKeyResult;
    _createdSecret = result.secret;

    const secretEl = document.getElementById('gk-created-secret');
    const secretBox = document.getElementById('gk-created') as HTMLElement | null;
    if (secretEl) secretEl.textContent = _createdSecret;
    if (secretBox) secretBox.style.display = 'block';

    const labelInput = document.getElementById('gk-label') as HTMLInputElement | null;
    if (labelInput) labelInput.value = '';
    document.querySelectorAll<HTMLButtonElement>('#gk-scopes .gk-scope-badge[aria-pressed="true"]').forEach(b => {
      b.setAttribute('aria-pressed', 'false');
      b.classList.remove('active');
    });
    _onWildcardDeselected();
    _updateIdPreview();

    showToast(_t('gateway_keys.toast_created', 'APIキーを作成しました'));
    await loadGatewayKeys();
  } catch {
    showToast(_t('gateway_keys.toast_error', 'エラーが発生しました'), true);
  }
}

export async function copyGatewaySecret(): Promise<void> {
  if (_createdSecret) await copyToClipboard(_createdSecret);
}

export async function deleteGatewayKey(keyId: string): Promise<void> {
  const key = _gatewayKeys.find(k => k.id === keyId);
  const isLastWildcard = !!key?.scopes.includes('*') &&
    _gatewayKeys.filter(k => k.scopes.includes('*')).length === 1;

  let confirmMsg = _t('gateway_keys.delete_confirm_with_id', "キー '{id}' を削除しますか？").replace('{id}', keyId);
  if (isLastWildcard) {
    confirmMsg += '\n\n' + _t('gateway_keys.last_wildcard_warning',
      'これは * スコープを持つ最後のキーです。削除すると Bearer 経路での管理が不可能になります。');
  }
  if (!(await window.customConfirm(confirmMsg))) return;

  try {
    const resp = await apiFetch(`/api/gateway/keys/${encodeURIComponent(keyId)}`, { method: 'DELETE' });
    const data = await resp.json();
    if (!resp.ok) {
      showToast(data?.error?.message ?? _t('gateway_keys.toast_error', 'エラーが発生しました'), true);
      return;
    }
    showToast(_t('gateway_keys.toast_deleted', 'APIキーを削除しました'));
    await loadGatewayKeys();
  } catch {
    showToast(_t('gateway_keys.toast_error', 'エラーが発生しました'), true);
  }
}

/* -- Initialization -- */

export function initGatewayKeysTab(): void {
  if (_tabInitialized) return;
  _tabInitialized = true;

  document.getElementById('gk-scopes')?.addEventListener('click', (e) => {
    const badge = (e.target as HTMLElement).closest<HTMLButtonElement>('.gk-scope-badge');
    if (!badge || badge.disabled) return;
    const isWildcard = badge.classList.contains('gk-scope-wildcard');
    const wasPressed = badge.getAttribute('aria-pressed') === 'true';
    badge.setAttribute('aria-pressed', wasPressed ? 'false' : 'true');
    badge.classList.toggle('active', !wasPressed);
    if (isWildcard && !wasPressed) _onWildcardSelected();
    if (isWildcard && wasPressed) _onWildcardDeselected();
    _validateCreateForm();
  });

  document.getElementById('gk-label')?.addEventListener('input', _updateIdPreview);
  document.getElementById('gk-wildcard-confirm')?.addEventListener('change', () => _validateCreateForm());

  document.addEventListener('settings:cat-shown', (e: Event) => {
    const detail = (e as CustomEvent).detail;
    if (detail.catId === 'cat-auth') _clearSecret();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') _clearSecret();
  });
}

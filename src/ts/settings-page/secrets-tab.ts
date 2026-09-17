/**
 * secrets-tab.ts -- Secret key management UI (barrel module).
 * Orchestrates backend status loading, secret settings overview,
 * export/import, and keychain migration.
 *
 * 1Password and Bitwarden specific logic is split into:
 *   - secrets-tab-op.ts   (1Password)
 *   - secrets-tab-bw.ts   (Bitwarden)
 * Shared utilities live in secrets-tab-utils.ts.
 */

import { apiFetch } from '../main/api-utils';
import { getAppApi, getNavApi } from '../shared/browser-apis';
import { customPrompt } from '../shared/dialog';
import { _t, _esc, _sourceBadge, fetchSecretSettingsAndSchema } from './secrets-tab-utils';
import { loadOpStatus, showLinkOpDialog, unlinkOpSecret, showPushToOpWizard, _setRefreshOverview as _setOpRefresh, _setRefreshOverviewWizard as _setOpWizardRefresh } from './secrets-tab-op';
import { loadBwStatus, unlinkBwSecret, showPushToBwWizard, _setRefreshOverview as _setBwRefresh, _setRefreshOverviewWizard as _setBwWizardRefresh } from './secrets-tab-bw';

// Re-export public API so existing imports from './secrets-tab' continue to work
export { showLinkOpDialog, unlinkOpSecret, showPushToOpWizard } from './secrets-tab-op';
export { unlinkBwSecret, showPushToBwWizard } from './secrets-tab-bw';

/* ── Wire up cross-module refresh callback ───────────── */

_setOpRefresh(() => loadSecretSettingsOverview());
_setOpWizardRefresh(() => loadSecretSettingsOverview());
_setBwRefresh(() => loadSecretSettingsOverview());
_setBwWizardRefresh(() => loadSecretSettingsOverview());
const { tr } = getAppApi();
const { showToast } = getNavApi();

/* ── Load backend status ─────────────────────────────── */

export async function loadSecretsStatus(): Promise<void> {
  const el = document.getElementById('secretsStatusArea');
  if (!el) return;
  try {
    const res = await apiFetch('/api/settings/secrets/status');
    const d = await res.json();
    const data = d.data ?? d;
    const active = data.active_backend ?? 'file';
    const backends = data.backends ?? {};

    let html = `<div class="stat-row"><span>Active Backend:</span>
      <span class="s2t-badge s2t-badge-active" style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600;background:rgba(59,130,246,.15);color:#3b82f6">${_esc(active)}</span></div>`;

    const backendDescriptions: Record<string, string> = {
      passphrase: 'YU_SECRET_PASSPHRASE env \u2192 PBKDF2-SHA256 (600K iterations)',
      keychain: 'OS Keychain (Windows Credential Manager / macOS Keychain / Linux Secret Service)',
      file: 'data/secret.key',
    };

    for (const [name, info] of Object.entries(backends) as [string, Record<string, unknown>][]) {
      const avail = info.available ? '\u2705' : '\u274C';
      const isActive = info.active ? ' <span style="color:#22c55e;font-weight:600">(active)</span>' : '';
      let detail = '';
      if (name === 'keychain' && info.backend_name) detail = ` \u2014 ${_esc(String(info.backend_name))}`;
      if (name === 'file' && info.path) detail = ` \u2014 ${_esc(String(info.path))}`;
      const desc = backendDescriptions[name] || '';
      html += `<div class="stat-row" style="margin-top:4px"><span>${avail} <strong>${_esc(name)}</strong>${detail}${isActive}</span></div>`;
      if (desc) {
        html += `<div style="margin-left:24px;font-size:11px;color:var(--muted,#888)">${_esc(desc)}</div>`;
      }
    }

    // Keychain migration button
    if (active !== 'keychain' && backends.keychain?.available) {
      html += `<div style="margin-top:12px"><button type="button" class="btn btn-secondary secrets-action-btn" data-secrets-action="migrate" id="secretsMigrateBtn">Migrate to OS Keychain</button></div>`;
    }

    el.innerHTML = html;
    _bindSecretsOverviewActions(el);
  } catch {
    el.innerHTML = `<span style="color:var(--muted,#888)">Failed to load secrets status</span>`;
  }

  // Load 1Password / Bitwarden status in parallel
  loadOpStatus();
  loadBwStatus();
  loadSecretSettingsOverview();
}

/* ── Secret settings overview ────────────────────────── */

async function loadSecretSettingsOverview(): Promise<void> {
  const el = document.getElementById('secretSettingsOverview');
  if (!el) return;
  try {
    const { settings, schema } = await fetchSecretSettingsAndSchema();

    // Filter only settings with secret=true
    const secretSettings = settings.filter((s) => s.secret);
    if (secretSettings.length === 0) {
      el.innerHTML = '<span style="color:var(--muted,#888)">No secret settings configured</span>';
      return;
    }

    // Build a map of schema op_eligible info
    const schemaMap = new Map(schema.map((s) => [s.key, s]));

    let html = '<table style="width:100%;border-collapse:collapse;font-size:13px">';
    html += '<thead><tr style="border-bottom:1px solid var(--border,#333);text-align:left">';
    html += '<th style="padding:6px 8px">Setting</th>';
    html += '<th style="padding:6px 8px">Value</th>';
    html += '<th style="padding:6px 8px">Source</th>';
    html += '<th style="padding:6px 8px">External Store</th>';
    html += '</tr></thead><tbody>';

    for (const s of secretSettings) {
      const schemaDef = schemaMap.get(s.key);
      const opEligible = schemaDef?.op_eligible ?? false;
      const descKey = 'settings_schema.' + s.key.replace(/\./g, '_');
      const desc = tr(descKey, '') || schemaDef?.description || s.key;

      html += `<tr style="border-bottom:1px solid rgba(128,128,128,.15)">`;
      html += `<td style="padding:6px 8px"><code style="font-size:12px">${_esc(s.key)}</code><br><span style="font-size:11px;color:var(--muted,#888)">${_esc(desc)}</span></td>`;
      html += `<td style="padding:6px 8px;font-family:monospace;font-size:12px">${_esc(String(s.value ?? '(not set)'))}</td>`;
      html += `<td style="padding:6px 8px">${_sourceBadge(s.source)}</td>`;

      // External Store column (1Password / Bitwarden)
      if (!opEligible) {
        html += `<td style="padding:6px 8px;color:var(--muted,#888);font-size:11px">\u2014</td>`;
      } else if (s.source === '1password') {
        html += `<td style="padding:6px 8px"><button type="button" class="btn btn-secondary secrets-action-btn" data-secrets-action="unlink-op" data-secret-key="${_esc(s.key)}" style="font-size:11px;padding:6px 10px">Unlink (1Password)</button></td>`;
      } else if (s.source === 'bitwarden') {
        html += `<td style="padding:6px 8px"><button type="button" class="btn btn-secondary secrets-action-btn" data-secrets-action="unlink-bw" data-secret-key="${_esc(s.key)}" style="font-size:11px;padding:6px 10px">Unlink (Bitwarden)</button></td>`;
      } else {
        html += `<td style="padding:6px 8px"><button type="button" class="btn btn-secondary secrets-action-btn" data-secrets-action="link-op" data-secret-key="${_esc(s.key)}" style="font-size:11px;padding:6px 10px">Link (1P)</button></td>`;
      }

      html += '</tr>';
    }

    html += '</tbody></table>';
    el.innerHTML = html;
    _bindSecretsOverviewActions(el);
  } catch {
    el.innerHTML = `<span style="color:var(--muted,#888)">Failed to load secret settings</span>`;
  }
}

function _bindSecretsOverviewActions(container: HTMLElement): void {
  container.querySelectorAll<HTMLButtonElement>('.secrets-action-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.secretsAction;
      const key = btn.dataset.secretKey || '';
      if (action === 'migrate') {
        void migrateToKeychain();
      } else if (action === 'unlink-op' && key) {
        void unlinkOpSecret(key);
      } else if (action === 'unlink-bw' && key) {
        void unlinkBwSecret(key);
      } else if (action === 'link-op' && key) {
        showLinkOpDialog(key);
      }
    });
  });
}

/* ── Export ───────────────────────────────────────────── */

export async function exportSecrets(): Promise<void> {
  const pwEl = document.getElementById('secretsExportPassword') as HTMLInputElement | null;
  const resultEl = document.getElementById('secretsExportResult');
  if (!pwEl || !resultEl) return;

  const password = pwEl.value.trim();
  if (password.length < 8) {
    resultEl.innerHTML = `<span style="color:#ef4444">${_t('settings.secrets_password_min', 'Password must be at least 8 characters')}</span>`;
    return;
  }

  resultEl.innerHTML = `<span style="color:var(--muted,#888)">${_t('settings.secrets_exporting', 'Exporting...')}</span>`;

  try {
    const res = await apiFetch('/api/settings/secrets/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    const d = await res.json();
    const data = d.data ?? d;

    if (data.success && data.export_data) {
      const json = JSON.stringify(data.export_data, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `yu-secrets-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      resultEl.innerHTML = `<span style="color:#22c55e">${_t('settings.secrets_export_ok', 'Export file downloaded')}</span>`;
      pwEl.value = '';
    } else {
      resultEl.innerHTML = `<span style="color:#ef4444">${_esc(data.error || 'Export failed')}</span>`;
    }
  } catch (err) {
    resultEl.innerHTML = `<span style="color:#ef4444">${_esc(err instanceof Error ? err.message : String(err))}</span>`;
  }
}

/* ── Import ──────────────────────────────────────────── */

export async function importSecrets(): Promise<void> {
  const fileEl = document.getElementById('secretsImportFile') as HTMLInputElement | null;
  const pwEl = document.getElementById('secretsImportPassword') as HTMLInputElement | null;
  const resultEl = document.getElementById('secretsImportResult');
  if (!fileEl || !pwEl || !resultEl) return;

  const password = pwEl.value.trim();
  if (password.length < 8) {
    resultEl.innerHTML = `<span style="color:#ef4444">${_t('settings.secrets_password_min', 'Password must be at least 8 characters')}</span>`;
    return;
  }

  const file = fileEl.files?.[0];
  if (!file) {
    resultEl.innerHTML = `<span style="color:#ef4444">${_t('settings.secrets_select_file', 'Select an export file')}</span>`;
    return;
  }

  resultEl.innerHTML = `<span style="color:var(--muted,#888)">${_t('settings.secrets_importing', 'Importing...')}</span>`;

  try {
    const text = await file.text();
    const exportData = JSON.parse(text);

    const res = await apiFetch('/api/settings/secrets/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ export_data: exportData, password }),
    });
    const d = await res.json();
    const data = d.data ?? d;

    if (data.success) {
      resultEl.innerHTML = `<span style="color:#22c55e">${_esc(data.message || 'Import successful')}</span>`;
      pwEl.value = '';
      fileEl.value = '';
      loadSecretsStatus();
    } else {
      resultEl.innerHTML = `<span style="color:#ef4444">${_esc(data.error || 'Import failed')}</span>`;
    }
  } catch (err) {
    resultEl.innerHTML = `<span style="color:#ef4444">${_esc(err instanceof Error ? err.message : String(err))}</span>`;
  }
}

/* ── Migrate to keychain ─────────────────────────────── */

export async function migrateToKeychain(): Promise<void> {
  const btn = document.getElementById('secretsMigrateBtn') as HTMLButtonElement | null;
  if (btn) btn.disabled = true;

  try {
    const res = await apiFetch('/api/settings/secrets/migrate-keychain', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const d = await res.json();
    const data = d.data ?? d;

    if (data.success) {
      showToast(data.message || 'Migrated to keychain');
      loadSecretsStatus();
    } else {
      showToast(data.error || 'Migration failed', true);
    }
  } catch {
    showToast('Migration failed', true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function initSecretsRotate(): void {
  const btn = document.getElementById('secretsRotateBtn');
  const resultEl = document.getElementById('secretsRotateResult');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    const confirmMsg = typeof window.tr === 'function'
      ? window.tr('settings.secrets_rotate_confirm')
      : 'Type ROTATE to confirm. This is irreversible.';
    const input = await customPrompt(confirmMsg);
    if (input !== 'ROTATE') return;

    btn.setAttribute('disabled', '');
    if (resultEl) { resultEl.textContent = 'Rotating…'; resultEl.style.color = '#6b7280'; }

    void fetch('/api/settings/secrets/rotate', { method: 'POST' })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        if (resultEl) { resultEl.textContent = 'Done — key rotated'; resultEl.style.color = '#10b981'; }
      })
      .catch((err: Error) => {
        if (resultEl) { resultEl.textContent = err.message; resultEl.style.color = '#dc2626'; }
      })
      .finally(() => btn.removeAttribute('disabled'));
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSecretsRotate);
} else {
  initSecretsRotate();
}

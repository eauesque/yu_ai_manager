/**
 * secrets-tab-op-status.ts -- 1Password CLI status display, setup guide,
 * and link/unlink operations.
 */

import { apiFetch } from '../main/api-utils';
import { getNavApi } from '../shared/browser-apis';
import { _t, _esc } from './secrets-tab-utils';

const { showToast } = getNavApi();

// Lazy-bound reference; set by the main barrel file to avoid circular deps.
let _refreshOverview: (() => void) | null = null;
export function _setRefreshOverview(fn: () => void): void {
  _refreshOverview = fn;
}

/* -- Auth method label -- */

function _opAuthMethodLabel(method: string): string {
  const labels: Record<string, string> = {
    service_account: 'Service Account Token',
    biometric: 'Desktop App (Biometric Unlock)',
    manual: 'Manual Sign-in',
  };
  return labels[method] || method;
}

/* -- Setup guide -- */

function _opSetupGuide(plat: string, hasSaToken: boolean, hasBiometric: boolean): string {
  const lines: string[] = [];

  // Service Account Token -- common to all OS, for server/headless environments
  lines.push('<details style="margin-top:8px;font-size:12px"><summary style="cursor:pointer;color:var(--link,#3b82f6);font-weight:600">Service Account Token (Linux / headless server)</summary>');
  lines.push('<div style="margin-top:4px;padding:8px 12px;background:rgba(128,128,128,.08);border-radius:6px">');
  lines.push('<p style="margin:0 0 4px">Create a <a href="https://developer.1password.com/docs/service-accounts/" target="_blank" rel="noopener" style="color:var(--link,#3b82f6);display:inline-block;padding:6px 0">Service Account</a> in 1Password web UI, then set the token as an environment variable:</p>');
  lines.push('<code style="display:block;padding:6px 8px;background:rgba(0,0,0,.2);border-radius:4px;margin:4px 0;font-size:11px;word-break:break-all">export OP_SERVICE_ACCOUNT_TOKEN="ops_xxxxx..."</code>');
  lines.push('<p style="margin:4px 0 0;font-size:11px;color:var(--muted,#888)">Add to systemd unit file, .env, or shell profile so the web server process inherits it.</p>');
  if (hasSaToken) {
    lines.push('<p style="margin:4px 0 0;color:#22c55e;font-weight:600">OP_SERVICE_ACCOUNT_TOKEN is set</p>');
  }
  lines.push('</div></details>');

  // Biometric / Desktop App -- macOS, Windows
  if (plat === 'Darwin' || plat === 'Windows') {
    const appName = plat === 'Darwin' ? 'macOS' : 'Windows';
    lines.push(`<details style="margin-top:6px;font-size:12px"><summary style="cursor:pointer;color:var(--link,#3b82f6);font-weight:600">Desktop App Integration (${appName})</summary>`);
    lines.push('<div style="margin-top:4px;padding:8px 12px;background:rgba(128,128,128,.08);border-radius:6px">');
    lines.push('<ol style="margin:0;padding-left:20px;font-size:12px">');
    lines.push('<li>Open 1Password desktop app</li>');
    lines.push('<li>Settings → Developer → <strong>"Integrate with 1Password CLI"</strong></li>');
    lines.push('<li>Restart the web server</li>');
    lines.push('</ol>');
    lines.push('<p style="margin:4px 0 0;font-size:11px;color:var(--muted,#888)">While 1Password app is unlocked, the CLI inherits the session automatically.</p>');
    if (hasBiometric) {
      lines.push('<p style="margin:4px 0 0;color:#22c55e;font-weight:600">Desktop app integration detected</p>');
    }
    lines.push('</div></details>');
  }

  return lines.join('');
}

/* -- Load 1Password CLI status -- */

export async function loadOpStatus(): Promise<void> {
  const el = document.getElementById('opStatusArea');
  if (!el) return;
  try {
    const res = await apiFetch('/api/settings/op-status');
    const d = await res.json();
    const data = d.data ?? d;

    const plat = data.platform || '';
    const authMethod = data.auth_method || 'none';
    const hasSaToken = data.has_service_account_token ?? false;
    const hasBiometric = data.has_biometric ?? false;

    let html = '<div style="display:flex;flex-direction:column;gap:4px">';

    if (!data.available) {
      html += `<div class="stat-row"><span>Status:</span><span><code>op</code> CLI not found in PATH</span></div>`;
      html += `<div style="font-size:11px;color:var(--muted,#888);margin-top:2px">Install: <a href="https://developer.1password.com/docs/cli/get-started/" target="_blank" rel="noopener" style="color:var(--link,#3b82f6);display:inline-block;padding:6px 0">1Password CLI Get Started</a></div>`;
    } else if (!data.signed_in) {
      html += `<div class="stat-row"><span>Status:</span><span>Installed but not authenticated</span></div>`;
      html += `<div style="font-size:12px;color:var(--muted,#888);margin-top:4px">Choose an authentication method below. <code>op signin</code> alone does not work because sessions are per-shell and the web server runs in a separate process.</div>`;
    } else {
      html += `<div class="stat-row"><span>Status:</span><span>Authenticated</span></div>`;
      html += `<div class="stat-row"><span>Method:</span><span>${_esc(_opAuthMethodLabel(authMethod))}</span></div>`;
      if (data.account) {
        html += `<div class="stat-row"><span>Account:</span><span>${_esc(data.account)}</span></div>`;
      }
    }

    // Always show setup guide in collapsible
    html += _opSetupGuide(plat, hasSaToken, hasBiometric);

    // If authenticated: bulk migration button
    if (data.available && data.signed_in) {
      html += `<div style="margin-top:12px">
        <button class="btn btn-primary" id="opPushWizardBtn" style="font-size:12px;padding:8px 14px">1Password へ一括移行</button>
      </div>
      <div id="opPushWizardArea" style="margin-top:8px"></div>`;
    }

    html += '</div>';
    el.innerHTML = html;

    // Bulk migration button event listener
    const pushBtn = document.getElementById('opPushWizardBtn');
    if (pushBtn) {
      // Import showPushToOpWizard lazily to avoid circular dependency
      const { showPushToOpWizard } = await import('./secrets-tab-op-wizard');
      pushBtn.addEventListener('click', () => showPushToOpWizard());
    }
  } catch {
    el.innerHTML = `<span style="color:var(--muted,#888)">Failed to load 1Password status</span>`;
  }
}

/* -- Link / Unlink 1Password URI -- */

export function showLinkOpDialog(key: string): void {
  const fieldHint = key.split('.').pop() || key;
  const raw = prompt(
    _t('secrets.op_uri_prompt', 'Enter 1Password URI for "{key}":\n\nFormat: op://VaultName/ItemName/FieldName\nExample: op://Personal/YuManager/{hint}\n\nYou can copy the secret reference from the 1Password app via ... > Copy Secret Reference')
      .replace('{key}', key)
      .replace('{hint}', fieldHint),
  );
  if (!raw || !raw.trim()) return;
  // Remove surrounding quotes that may be included when pasting
  const uri = raw.trim().replace(/^["']+|["']+$/g, '');
  if (!uri.startsWith('op://')) {
    showToast(_t('secrets.op_uri_invalid', 'URI must start with op://'), true);
    return;
  }
  linkOpSecret(key, uri);
}

async function linkOpSecret(key: string, opUri: string): Promise<void> {
  try {
    const res = await apiFetch(`/api/settings/${encodeURIComponent(key)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: '', op_uri: opUri }),
    });
    const d = await res.json();
    if (d.data?.updated || d.updated) {
      showToast(`Linked ${key} to 1Password`);
      _refreshOverview?.();
    } else {
      showToast(d.error || 'Failed to link', true);
    }
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Failed to link', true);
  }
}

export async function unlinkOpSecret(key: string): Promise<void> {
  if (!confirm(`Remove 1Password link for "${key}"?\nThe setting will fall back to local encrypted storage.`)) return;
  try {
    const res = await apiFetch(`/api/settings/op-mapping/${encodeURIComponent(key)}`, {
      method: 'DELETE',
    });
    const d = await res.json();
    if (d.data?.unlinked || d.unlinked) {
      showToast(`Unlinked ${key} from 1Password`);
      _refreshOverview?.();
    } else {
      showToast(d.error || 'Failed to unlink', true);
    }
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Failed to unlink', true);
  }
}

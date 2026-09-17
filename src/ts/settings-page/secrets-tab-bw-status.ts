/**
 * secrets-tab-bw-status.ts -- Bitwarden CLI status display, setup guide,
 * and unlink operations.
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

/* -- Setup guide -- */

function _bwSetupGuide(status: string, hasSession: boolean): string {
  const lines: string[] = [];

  lines.push('<details style="margin-top:8px;font-size:12px"><summary style="cursor:pointer;color:var(--link,#3b82f6);font-weight:600">Setup Guide</summary>');
  lines.push('<div style="margin-top:4px;padding:8px 12px;background:rgba(128,128,128,.08);border-radius:6px">');

  if (status === 'unauthenticated') {
    lines.push('<p style="margin:0 0 4px">1. Log in to Bitwarden CLI:</p>');
    lines.push('<code style="display:block;padding:6px 8px;background:rgba(0,0,0,.2);border-radius:4px;margin:4px 0;font-size:11px">bw login</code>');
    lines.push('<p style="margin:4px 0 0">2. Unlock and set session:</p>');
  } else {
    lines.push('<p style="margin:0 0 4px">Unlock vault and set session key:</p>');
  }

  lines.push('<code style="display:block;padding:6px 8px;background:rgba(0,0,0,.2);border-radius:4px;margin:4px 0;font-size:11px;word-break:break-all">export BW_SESSION=$(bw unlock --raw)</code>');
  lines.push('<p style="margin:4px 0 0;font-size:11px;color:var(--muted,#888)">Set this environment variable before starting the web server. Add to systemd unit, .env, or shell profile.</p>');

  if (hasSession) {
    lines.push('<p style="margin:4px 0 0;color:#22c55e;font-weight:600">BW_SESSION is set</p>');
  }

  // API key auth (for CI/CD)
  lines.push('<details style="margin-top:6px;font-size:12px"><summary style="cursor:pointer;color:var(--link,#3b82f6)">API Key Authentication (CI/CD)</summary>');
  lines.push('<div style="margin-top:4px;padding:6px 8px;background:rgba(0,0,0,.1);border-radius:4px;font-size:11px">');
  lines.push('<code>bw login --apikey</code> then set <code>BW_CLIENTID</code> and <code>BW_CLIENTSECRET</code> environment variables.');
  lines.push('</div></details>');

  lines.push('</div></details>');
  return lines.join('');
}

/* -- Load Bitwarden CLI status -- */

export async function loadBwStatus(): Promise<void> {
  const el = document.getElementById('bwStatusArea');
  if (!el) return;
  try {
    const res = await apiFetch('/api/settings/bw-status');
    const d = await res.json();
    const data = d.data ?? d;

    let html = '<div style="display:flex;flex-direction:column;gap:4px">';

    if (!data.available) {
      html += `<div class="stat-row"><span>Status:</span><span><code>bw</code> CLI not found in PATH</span></div>`;
      html += `<div style="font-size:11px;color:var(--muted,#888);margin-top:2px">Install: <a href="https://bitwarden.com/help/cli/" target="_blank" rel="noopener" style="color:var(--link,#3b82f6);display:inline-block;padding:6px 0">Bitwarden CLI</a></div>`;
    } else if (!data.signed_in) {
      const statusLabel = data.status === 'locked' ? 'Locked (logged in, vault locked)' : 'Not authenticated';
      html += `<div class="stat-row"><span>Status:</span><span>${statusLabel}</span></div>`;
      // Setup guide
      html += _bwSetupGuide(data.status, data.has_session);
    } else {
      html += `<div class="stat-row"><span>Status:</span><span>Unlocked</span></div>`;
      if (data.user_email) {
        html += `<div class="stat-row"><span>Account:</span><span>${_esc(data.user_email)}</span></div>`;
      }
      if (data.server_url) {
        html += `<div class="stat-row"><span>Server:</span><span style="font-size:11px">${_esc(data.server_url)}</span></div>`;
      }
    }

    // If authenticated: bulk migration button
    if (data.available && data.signed_in) {
      html += `<div style="margin-top:12px">
        <button class="btn btn-primary" id="bwPushWizardBtn" style="font-size:12px;padding:8px 14px">Bitwarden へ一括移行</button>
      </div>
      <div id="bwPushWizardArea" style="margin-top:8px"></div>`;
    }

    html += '</div>';
    el.innerHTML = html;

    // Bulk migration button event listener
    const pushBtn = document.getElementById('bwPushWizardBtn');
    if (pushBtn) {
      const { showPushToBwWizard } = await import('./secrets-tab-bw-wizard');
      pushBtn.addEventListener('click', () => showPushToBwWizard());
    }
  } catch {
    el.innerHTML = `<span style="color:var(--muted,#888)">Failed to load Bitwarden status</span>`;
  }
}

/* -- Unlink Bitwarden secret -- */

export async function unlinkBwSecret(key: string): Promise<void> {
  if (!confirm(`Remove Bitwarden link for "${key}"?\nThe setting will fall back to local encrypted storage.`)) return;
  try {
    const res = await apiFetch(`/api/settings/bw-mapping/${encodeURIComponent(key)}`, {
      method: 'DELETE',
    });
    const d = await res.json();
    if (d.data?.unlinked || d.unlinked) {
      showToast(`Unlinked ${key} from Bitwarden`);
      _refreshOverview?.();
    } else {
      showToast(d.error || 'Failed to unlink', true);
    }
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Failed to unlink', true);
  }
}

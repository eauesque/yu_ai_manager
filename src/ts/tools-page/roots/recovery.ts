/**
 * roots/recovery.ts -- One-time scan_roots recovery banner.
 *
 * Surfaces `GET /api/scan-roots/recovery-check`'s candidates (folders the
 * stale-read/reorder-overwrite bug fixed in v4.681.6 could have silently
 * dropped from config.json, reconstructed from files still in the DB) and
 * lets the user apply or dismiss them with one click. See
 * core/schema_core/schema_migrate_steps_88.py for the migration that plants
 * the marker this checks, and core/scan_roots_api/ops_recovery.py for the
 * backend side.
 */

import { getAppApi } from '../../shared/browser-apis';
import { apiFetch } from '../api';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

// Candidate paths come from files already indexed in the DB (local disk
// paths, not remote user input), but a crafted filename could still smuggle
// HTML into a path string -- escape before interpolating into innerHTML.
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

interface RecoveryCandidate {
  path: string;
  count: number;
}

/**
 * Checks for and, if warranted, renders the recovery banner into `container`.
 * `reload` is called after apply/dismiss to refresh the roots list --
 * passed in rather than imported from './list' to avoid a circular import.
 */
export async function checkScanRootsRecovery(
  container: HTMLElement,
  reload: () => void | Promise<void>,
): Promise<void> {
  let data: { pending?: boolean; candidates?: RecoveryCandidate[] };
  try {
    const res = await apiFetch('/api/scan-roots/recovery-check');
    data = await res.json();
  } catch {
    return; // Best-effort nicety, not core functionality.
  }
  if (!data.pending || !data.candidates || data.candidates.length === 0) return;
  renderRecoveryBanner(container, data.candidates, reload);
}

function renderRecoveryBanner(
  container: HTMLElement,
  candidates: RecoveryCandidate[],
  reload: () => void | Promise<void>,
): void {
  document.getElementById('scanRootsRecoveryBanner')?.remove();

  const list = candidates
    .map(
      (c) =>
        `<li>${escapeHtml(c.path)} <span style="color:#888;">(${c.count.toLocaleString()})</span></li>`,
    )
    .join('');

  const banner = document.createElement('div');
  banner.id = 'scanRootsRecoveryBanner';
  banner.style.cssText =
    'background:rgba(102,126,234,0.1);border:1px solid #667eea;border-radius:8px;' +
    'padding:12px;margin-bottom:10px;';
  banner.innerHTML = `
    <div style="font-weight:600;margin-bottom:6px;">
      ${_t('tools.recovery_title', 'Previously registered folders were detected')}
    </div>
    <div style="font-size:12px;color:var(--muted);margin-bottom:8px;">
      ${_t(
        'tools.recovery_desc',
        'These folders appear to have been registered before, based on files still in the database. Restore them?',
      )}
    </div>
    <ul style="font-size:12px;margin:0 0 10px 18px;padding:0;max-height:160px;overflow-y:auto;">${list}</ul>
    <button id="scanRootsRecoveryApply" type="button"
      style="margin-right:8px;padding:4px 12px;border-radius:4px;border:none;background:#667eea;color:#fff;cursor:pointer;">
      ${_t('tools.recovery_apply', 'Restore')}
    </button>
    <button id="scanRootsRecoveryDismiss" type="button"
      style="padding:4px 12px;border-radius:4px;border:1px solid rgba(128,128,128,0.3);background:transparent;color:var(--text);cursor:pointer;">
      ${_t('tools.recovery_dismiss', 'Dismiss')}
    </button>
  `;
  container.prepend(banner);

  document.getElementById('scanRootsRecoveryApply')?.addEventListener('click', async () => {
    try {
      await apiFetch('/api/scan-roots/recovery-apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
    } catch (e) {
      console.error('Scan roots recovery apply failed:', e);
    }
    banner.remove();
    await reload();
  });

  document.getElementById('scanRootsRecoveryDismiss')?.addEventListener('click', async () => {
    try {
      await apiFetch('/api/scan-roots/recovery-dismiss', { method: 'POST' });
    } catch (e) {
      console.error('Scan roots recovery dismiss failed:', e);
    }
    banner.remove();
  });
}

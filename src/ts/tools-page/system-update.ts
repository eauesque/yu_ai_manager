// System update controller: orchestrates API calls, rendering, and SSE progress.

import { getAppApi } from '../shared/browser-apis';
import { sseSubscribe, sseUnsubscribe } from '../sse';
import {
  fetchSystemUpdateCheck,
  fetchUnifiedUpdateCheck,
  fetchUpdateStatus,
  getApiErrorMessage,
  requestApplySystemUpdate,
  requestApplyUnifiedUpdates,
  requestSingleExtensionUpdate,
  unwrapApiPayload,
} from './system-update-api';
import {
  appendProgressMessage,
  appendRestartingMessage,
  renderUnifiedError,
  renderUnifiedSummary,
  renderUnifiedTable,
  STATUS_ICONS,
  STEP_LABELS,
  upsertProgressRow,
} from './system-update-render';
import type {
  ExtensionUpdateResult,
  SystemUpdateCheckResult,
  UnifiedCheckResult,
  UpdateProgressPayload,
} from './system-update-types';

// i18n helper
function _tr(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback) || fallback;
}

let _lastUnifiedResult: UnifiedCheckResult | null = null;
let _systemProgressHandler: ((d: unknown) => void) | null = null;
let _unifiedProgressHandler: ((d: unknown) => void) | null = null;

function _replaceProgressSubscription(
  kind: 'system' | 'unified',
  handler: (d: unknown) => void,
): void {
  const current = kind === 'system' ? _systemProgressHandler : _unifiedProgressHandler;
  if (current) {
    sseUnsubscribe('update.progress', current);
  }
  sseSubscribe('update.progress', handler);
  if (kind === 'system') {
    _systemProgressHandler = handler;
  } else {
    _unifiedProgressHandler = handler;
  }
}

/** Check for available updates via the API. */
export async function checkForUpdate(): Promise<void> {
  const resultEl = document.getElementById('updateCheckResult');
  const applyBtn = document.getElementById('applyUpdateBtn');
  const dockerHint = document.getElementById('dockerUpdateHint');
  if (!resultEl) return;

  resultEl.style.display = '';
  resultEl.style.background = 'var(--bg-card)';
  resultEl.style.border = '1px solid var(--border)';
  resultEl.textContent = _tr('tools.checking_update', 'Checking...');

  try {
    const data: SystemUpdateCheckResult = await fetchSystemUpdateCheck();

    if (data.update_available) {
      resultEl.style.background = 'rgba(46,204,113,0.1)';
      resultEl.style.border = '1px solid rgba(46,204,113,0.3)';
      const label = _tr('tools.update_available', 'Update available');
      resultEl.textContent = `${label}: v${data.latest}`;

      if (data.install_type === 'docker') {
        if (dockerHint) {
          dockerHint.style.display = '';
          const cmdEl = document.getElementById('dockerPullCmd');
          if (cmdEl) {
            cmdEl.textContent =
              data.docker_command || 'docker pull eauesque/yu_ai_manager:latest';
          }
        }
      } else if (data.install_type === 'git') {
        if (applyBtn) applyBtn.style.display = '';
      }
    } else if (data.error) {
      resultEl.style.background = 'rgba(231,76,60,0.1)';
      resultEl.style.border = '1px solid rgba(231,76,60,0.3)';
      resultEl.textContent = data.error;
    } else {
      resultEl.textContent = `${_tr('tools.up_to_date', 'You are up to date')} (v${data.current})`;
    }
  } catch (e) {
    resultEl.style.background = 'rgba(231,76,60,0.1)';
    resultEl.textContent =
      'Failed to check: ' + (e instanceof Error ? e.message : String(e));
  }
}

/** Apply available update with SSE progress tracking. */
export async function applySystemUpdate(): Promise<void> {
  if (!confirm(_tr('tools.update_confirm', 'Apply update? The server will restart.'))) return;

  const progressEl = document.getElementById('updateProgress');
  const stepsEl = document.getElementById('updateSteps');
  const applyBtn = document.getElementById('applyUpdateBtn') as HTMLButtonElement | null;
  if (!progressEl || !stepsEl) return;

  progressEl.style.display = '';
  if (applyBtn) applyBtn.disabled = true;
  stepsEl.replaceChildren();

  _replaceProgressSubscription('system', (d: unknown) => {
    const payload = d as UpdateProgressPayload;
    if (payload.unified) return; // Handled by unified handler
    const step = payload.step || '';
    const status = payload.status || '';
    const detail = payload.detail || '';
    const label = STEP_LABELS[step] || step;
    const icon = STATUS_ICONS[status] || '';
    upsertProgressRow(stepsEl, step, `${icon} ${label}${detail ? ': ' + detail : ''}`);

    if (step === 'complete' && status === 'done') {
      appendRestartingMessage(stepsEl);
    }
  });

  try {
    const result = await requestApplySystemUpdate();
    if (!result.ok) {
      appendProgressMessage(stepsEl, getApiErrorMessage(result.payload, 'Update failed'));
      if (applyBtn) applyBtn.disabled = false;
    }
  } catch (e) {
    appendProgressMessage(stepsEl, 'Request failed: ' + (e instanceof Error ? e.message : String(e)));
    if (applyBtn) applyBtn.disabled = false;
  }
}

/** Load current version and install type on page load. */
export async function loadUpdateStatus(): Promise<void> {
  try {
    const data = await fetchUpdateStatus();

    const verEl = document.getElementById('updateCurrentVer');
    const badgeEl = document.getElementById('updateInstallBadge');

    if (verEl) verEl.textContent = 'v' + (data.version || '?');
    if (badgeEl) {
      const labels: Record<string, string> = {
        git: 'Git Clone',
        tauri: 'Desktop',
        docker: 'Docker',
        portable: 'Portable',
      };
      const installType = data.install_type || '';
      badgeEl.textContent = labels[installType] || installType || 'Unknown';
    }
  } catch {
    // Silently ignore -- status is non-critical
  }
}

/** Check update status for system + all extensions. */
export async function checkUnifiedUpdates(): Promise<void> {
  const tableEl = document.getElementById('unifiedUpdateTable');
  const bodyEl = document.getElementById('unifiedUpdateBody');
  const summaryEl = document.getElementById('unifiedSummaryBadge');
  const applyAllBtn = document.getElementById('unifiedApplyAllBtn');
  if (!tableEl || !bodyEl) return;

  // Show loading state
  if (summaryEl) summaryEl.textContent = _tr('tools.checking_update', 'Checking...');
  bodyEl.innerHTML = '';
  tableEl.style.display = '';

  try {
    const result = await fetchUnifiedUpdateCheck();
    _lastUnifiedResult = result;

    if (summaryEl) {
      renderUnifiedSummary(summaryEl, result);
    }

    renderUnifiedTable(bodyEl, result, {
      onApplySystemUpdate: () => {
        void applySystemUpdate();
      },
      onUpdateExtension: (name: string) => {
        void updateSingleExtension(name);
      },
    });

    const hasUpdates = result.system.update_available || result.summary.update_available > 0;
    if (applyAllBtn) {
      applyAllBtn.style.display = hasUpdates ? '' : 'none';
    }

  } catch (e) {
    renderUnifiedError(bodyEl, summaryEl, e instanceof Error ? e.message : String(e));
  }
}

/** Update a single extension via the extensions API. */
export async function updateSingleExtension(name: string): Promise<void> {
  if (!confirm(`Update extension "${name}"?`)) return;

  const progressEl = document.getElementById('unifiedProgress');
  const stepsEl = document.getElementById('unifiedSteps');
  if (!progressEl || !stepsEl) return;

  progressEl.style.display = '';
  const row = upsertProgressRow(stepsEl, `single-${name}`, `... Updating ${name}...`);

  try {
    const result = await requestSingleExtensionUpdate(name);
    if (result.ok) {
      const data = unwrapApiPayload(result.payload as ExtensionUpdateResult);
      row.textContent = `[OK] ${name}: ${data.message || 'Updated'}`;
    } else {
      row.textContent = `[!] ${name}: ${getApiErrorMessage(result.payload, 'Failed')}`;
      row.style.color = '#d32f2f';
    }
  } catch (e) {
    row.textContent = `[!] ${name}: ${e instanceof Error ? e.message : String(e)}`;
    row.style.color = '#d32f2f';
  }

  // Refresh table after single update
  setTimeout(() => checkUnifiedUpdates(), 500);
}

/** Apply all available updates (system + extensions) via unified endpoint. */
export async function applyUnifiedUpdates(): Promise<void> {
  const hasSystemUpdate = _lastUnifiedResult?.system?.update_available || false;
  const extUpdates = (_lastUnifiedResult?.extensions || []).filter(e => e.status === 'update_available');

  const parts: string[] = [];
  if (hasSystemUpdate) parts.push('System');
  if (extUpdates.length > 0) parts.push(`${extUpdates.length} extension(s)`);
  const msg = _tr('tools.unified_confirm_all', `Update all? (${parts.join(' + ')})\nThe server may restart.`);
  if (!confirm(msg)) return;

  const progressEl = document.getElementById('unifiedProgress');
  const stepsEl = document.getElementById('unifiedSteps');
  const applyAllBtn = document.getElementById('unifiedApplyAllBtn') as HTMLButtonElement | null;
  if (!progressEl || !stepsEl) return;

  progressEl.style.display = '';
  if (applyAllBtn) applyAllBtn.disabled = true;
  stepsEl.replaceChildren();

  _replaceProgressSubscription('unified', (d: unknown) => {
    const payload = d as UpdateProgressPayload;
    if (!payload.unified) return; // Only handle unified events
    const step = payload.step || '';
    const status = payload.status || '';
    const detail = payload.detail || '';

    // Pretty label: extension updates get their name
    let label = STEP_LABELS[step] || step;
    if (step.startsWith('ext_update_')) {
      label = step.replace('ext_update_', '');
    }
    const icon = STATUS_ICONS[status] || '';
    upsertProgressRow(stepsEl, step, `${icon} ${label}${detail ? ': ' + detail : ''}`);

    if (step === 'complete' && status === 'done') {
      appendRestartingMessage(stepsEl);
    }
  });

  try {
    const body: Record<string, unknown> = {
      update_system: hasSystemUpdate,
      update_extensions: extUpdates.length > 0,
    };
    if (extUpdates.length > 0) {
      body.extension_names = extUpdates.map(e => e.name);
    }

    const result = await requestApplyUnifiedUpdates(body);
    if (!result.ok) {
      appendProgressMessage(stepsEl, getApiErrorMessage(result.payload, 'Unified update failed'));
      if (applyAllBtn) applyAllBtn.disabled = false;
    }
  } catch (e) {
    appendProgressMessage(stepsEl, 'Request failed: ' + (e instanceof Error ? e.message : String(e)));
    if (applyAllBtn) applyAllBtn.disabled = false;
  }
}

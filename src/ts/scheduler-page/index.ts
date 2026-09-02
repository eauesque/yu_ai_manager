/**
 * Scheduler page: fetch and display scheduled jobs and execution history.
 * Supports add/delete jobs, pause/resume, trigger, and SSE auto-refresh.
 *
 * API helpers are in scheduler-api.ts, rendering in scheduler-render.ts.
 */

import { sseSubscribe } from '../sse';

import {
  tr,
  showToast,
  parseCronField,
  CRON_FIELDS,
  fetchStatus,
  fetchHistory,
  triggerJob,
  pauseJob,
  resumeJob,
  deleteJob,
  addJob,
} from './scheduler-api';

import {
  renderStatus,
  renderJobs,
  renderHistory,
} from './scheduler-render';

// Re-export for backward compatibility
export {
  tr,
  showToast,
  escapeHtml,
  formatTime,
  formatTimestamp,
  parseCronField,
  JOB_DESCS,
  CRON_FIELDS,
  apiFetch,
  fetchStatus,
  fetchHistory,
  triggerJob,
  pauseJob,
  resumeJob,
  deleteJob,
  addJob,
} from './scheduler-api';
export type { CronFieldDef } from './scheduler-api';
export { renderStatus, renderJobs, renderHistory } from './scheduler-render';

/* ------------------------------------------------------------------ */
/*  Data loading                                                       */
/* ------------------------------------------------------------------ */

// Cache of the latest fetched data so the i18n:changed listener can re-render
// without issuing another network round-trip.
let _lastStatusData: unknown = null;
let _lastHistoryData: unknown = null;

async function loadAll(): Promise<void> {
  try {
    const [statusData, historyData] = await Promise.all([fetchStatus(), fetchHistory()]);
    _lastStatusData = statusData;
    _lastHistoryData = historyData;
    renderStatus(statusData);
    renderJobs(statusData);
    renderHistory(historyData);
  } catch (e) {
    console.error('[scheduler] load failed:', e);
  }
}

/**
 * Re-render from cached data when the i18n dictionary finishes loading
 * or the user switches languages. Without this, the initial render can
 * race the async dict load and produce English fallback text that never
 * updates (e.g. "Running (6 jobs)" instead of "稼働中 (6 ジョブ一覧)").
 */
function renderFromCache(): void {
  if (_lastStatusData) {
    renderStatus(_lastStatusData);
    renderJobs(_lastStatusData);
  }
  if (_lastHistoryData) {
    renderHistory(_lastHistoryData);
  }
}

/* ------------------------------------------------------------------ */
/*  Event handlers                                                     */
/* ------------------------------------------------------------------ */

function handleTableClick(e: Event): void {
  const btn = (e.target as HTMLElement).closest<HTMLButtonElement>('[data-action]');
  if (!btn) return;

  const action = btn.dataset.action;
  const jobId = btn.dataset.job;
  if (!action || !jobId) return;

  // Delete requires confirmation
  if (action === 'delete') {
    const msg = tr('scheduler.delete_confirm', `Delete job "${jobId}"?`).replace('{id}', jobId);
    if (!confirm(msg)) return;
  }

  btn.disabled = true;

  let promise: Promise<any>;
  let successMsg: string;

  switch (action) {
    case 'trigger':
      promise = triggerJob(jobId);
      successMsg = tr('scheduler.triggered', 'Job queued for immediate execution');
      break;
    case 'pause':
      promise = pauseJob(jobId);
      successMsg = tr('scheduler.paused_msg', 'Job paused');
      break;
    case 'resume':
      promise = resumeJob(jobId);
      successMsg = tr('scheduler.resumed_msg', 'Job resumed');
      break;
    case 'delete':
      promise = deleteJob(jobId);
      successMsg = tr('scheduler.deleted_msg', 'Job deleted');
      break;
    default:
      btn.disabled = false;
      return;
  }

  promise
    .then((resp) => {
      if (resp?.error || resp?.ok === false) {
        showToast(resp.error || tr('scheduler.action_failed', 'Action failed'));
      } else {
        showToast(successMsg);
      }
      return loadAll();
    })
    .catch(() => {
      showToast(tr('scheduler.action_failed', 'Action failed'));
    })
    .finally(() => {
      btn.disabled = false;
    });
}

/* ------------------------------------------------------------------ */
/*  Add Job Dialog                                                     */
/* ------------------------------------------------------------------ */

function setupAddDialog(): void {
  const dialog = document.getElementById('schedAddDialog') as HTMLDialogElement | null;
  const form = document.getElementById('schedAddForm') as HTMLFormElement | null;
  const openBtn = document.getElementById('schedAddBtn');
  const cancelBtn = document.getElementById('schedCancelBtn');
  const triggerSelect = document.getElementById('schedNewTrigger') as HTMLSelectElement | null;
  const cronFields = document.getElementById('schedCronFields');
  const intervalFields = document.getElementById('schedIntervalFields');

  if (!dialog || !form) return;

  // Open dialog
  openBtn?.addEventListener('click', () => {
    dialog.showModal();
  });

  // Cancel
  cancelBtn?.addEventListener('click', () => {
    dialog.close();
  });

  // Close on backdrop click
  dialog.addEventListener('click', (e) => {
    if (e.target === dialog) dialog.close();
  });

  // Toggle cron/interval fields
  triggerSelect?.addEventListener('change', () => {
    const isCron = triggerSelect.value === 'cron';
    if (cronFields) cronFields.style.display = isCron ? '' : 'none';
    if (intervalFields) intervalFields.style.display = isCron ? 'none' : '';
  });

  // Submit
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const jobId = (document.getElementById('schedNewJobId') as HTMLInputElement)?.value.trim();
    const funcName = (document.getElementById('schedNewFunc') as HTMLSelectElement)?.value;
    const triggerType = triggerSelect?.value ?? 'cron';

    if (!jobId || !funcName) return;

    const triggerArgs: Record<string, unknown> = {};

    if (triggerType === 'cron') {
      for (const field of CRON_FIELDS) {
        const raw = (document.getElementById(field.id) as HTMLInputElement)?.value ?? '';
        const parsed = parseCronField(raw);
        if (parsed !== undefined) triggerArgs[field.key] = parsed;
      }
    } else {
      const hours = (document.getElementById('schedNewIntervalHours') as HTMLInputElement)?.value;
      const minutes = (document.getElementById('schedNewIntervalMinutes') as HTMLInputElement)?.value;
      if (hours) triggerArgs.hours = parseInt(hours, 10);
      if (minutes) triggerArgs.minutes = parseInt(minutes, 10);
    }

    try {
      const resp = await addJob({
        job_id: jobId,
        func_name: funcName,
        trigger: triggerType,
        trigger_args: triggerArgs,
      });

      if (resp?.error || resp?.ok === false) {
        showToast(resp.error || tr('scheduler.action_failed', 'Action failed'));
      } else {
        showToast(tr('scheduler.added_msg', 'Job added'));
        dialog.close();
        form.reset();
        await loadAll();
      }
    } catch {
      showToast(tr('scheduler.action_failed', 'Action failed'));
    }
  });
}

/* ------------------------------------------------------------------ */
/*  Init                                                               */
/* ------------------------------------------------------------------ */

function init(): void {
  loadAll();

  // Refresh button
  document.getElementById('schedRefreshBtn')?.addEventListener('click', () => loadAll());

  // Table action buttons (delegation)
  document.getElementById('schedJobsTable')?.addEventListener('click', handleTableClick);

  // Add job dialog
  setupAddDialog();

  // SSE: auto-refresh on job execution events
  sseSubscribe('scheduler.job_executed', () => loadAll());
  sseSubscribe('scheduler.job_error', () => loadAll());

  // Re-render when the i18n dictionary becomes available or the user
  // switches languages. See core-shared.ts::applyTranslations which
  // dispatches this event. Also listen for tr-runtime-lite ready signal
  // because the scheduler page uses the lite runtime, which fires its own
  // event instead of i18n:changed.
  document.addEventListener('i18n:changed', renderFromCache);
  document.addEventListener('tr-runtime:ready', renderFromCache);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

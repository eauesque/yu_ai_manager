/**
 * scheduler-render.ts — DOM rendering functions for the scheduler page.
 *
 * Extracted from index.ts to keep file sizes manageable.
 */

import {
  tr,
  escapeHtml,
  formatTime,
  formatTimestamp,
  JOB_DESCS,
} from './scheduler-api';

/* ------------------------------------------------------------------ */
/*  Trigger string formatter                                           */
/* ------------------------------------------------------------------ */

function formatTrigger(raw: string): string {
  if (!raw) return raw;
  // interval[H:MM:SS] or interval[D day, H:MM:SS]
  const intervalMatch = raw.match(/^interval\[(?:(\d+) day(?:s)?,\s*)?(\d+):(\d+):(\d+)\]$/);
  if (intervalMatch) {
    const days = parseInt(intervalMatch[1] || '0', 10);
    const hours = parseInt(intervalMatch[2], 10);
    const mins = parseInt(intervalMatch[3], 10);
    const secs = parseInt(intervalMatch[4], 10);
    const parts: string[] = [];
    if (days) parts.push(`${days}日`);
    if (hours) parts.push(`${hours}時間`);
    if (mins) parts.push(`${mins}分`);
    if (secs && !parts.length) parts.push(`${secs}秒`);
    return `${parts.join('')}ごと`;
  }
  // cron[...] - extract key fields
  const cronMatch = raw.match(/^cron\[(.+)\]$/);
  if (cronMatch) {
    const fields = cronMatch[1];
    const hour = fields.match(/hour='([^']+)'/)?.[1];
    const minute = fields.match(/minute='([^']+)'/)?.[1];
    const dow = fields.match(/day_of_week='([^']+)'/)?.[1];
    if (hour !== undefined && minute !== undefined) {
      const h = hour === '*' ? '毎時' : `${hour}時`;
      const m = minute === '0' ? '0分' : `${minute}分`;
      const d = dow ? ` (${dow})` : '';
      return `${h}${h === '毎時' ? '' : ''}${m}${d}`;
    }
    return fields.length < 60 ? fields : raw;
  }
  // date trigger
  if (raw.startsWith('date[')) return raw.replace(/^date\[/, '').replace(/\]$/, '');
  return raw;
}

/* ------------------------------------------------------------------ */
/*  Rendering                                                          */
/* ------------------------------------------------------------------ */

export function renderStatus(data: any): void {
  const dot = document.getElementById('schedDot');
  const text = document.getElementById('schedStatusText');
  if (!dot || !text) return;

  const status = data?.data?.status ?? data?.status ?? {};
  const running = status.running ?? false;

  dot.className = 'sched-dot ' + (running ? 'running' : 'stopped');
  // Strip data-i18n so the shared i18n runtime (src/ts/i18n/core-shared.ts)
  // does not overwrite our dynamic text back to "Loading..." on its async
  // post-load sweep. The element is now JS-owned.
  text.removeAttribute('data-i18n');
  // The count suffix intentionally drops the unit word: the same i18n key
  // scheduler.jobs is reused as a section heading ("ジョブ一覧") and reusing
  // it here would read awkwardly ("稼働中 (6 ジョブ一覧)"). A bare "(N)" is
  // unambiguous across all locales.
  text.textContent = running
    ? tr('scheduler.running', 'Running') + ` (${status.job_count ?? 0})`
    : tr('scheduler.stopped', 'Stopped');
}

export function renderJobs(data: any): void {
  const tbody = document.getElementById('schedJobsBody');
  if (!tbody) return;

  const status = data?.data?.status ?? data?.status ?? {};
  const jobs: any[] = status.jobs ?? [];

  if (jobs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="sched-empty">${escapeHtml(tr('scheduler.no_jobs', 'No jobs registered'))}</td></tr>`;
    return;
  }

  tbody.innerHTML = jobs.map((j: any) => {
    const id = escapeHtml(j.id ?? '');
    const descKey = JOB_DESCS[j.id] ?? '';
    const desc = descKey ? tr(descKey, '') : '';
    const triggerRaw = j.trigger ?? '';
    const trigger = escapeHtml(formatTrigger(triggerRaw));
    const triggerTitle = triggerRaw !== formatTrigger(triggerRaw) ? ` title="${escapeHtml(triggerRaw)}"` : '';
    const nextRun = formatTime(j.next_run_time);
    const paused = j.paused ?? false;
    const statusBadge = paused
      ? `<span class="sched-badge paused">${escapeHtml(tr('scheduler.paused', 'Paused'))}</span>`
      : `<span class="sched-badge active">${escapeHtml(tr('scheduler.active', 'Active'))}</span>`;

    const pauseResumeBtn = paused
      ? `<button type="button" class="sched-btn" data-action="resume" data-job="${id}">${escapeHtml(tr('scheduler.resume', 'Resume'))}</button>`
      : `<button type="button" class="sched-btn" data-action="pause" data-job="${id}">${escapeHtml(tr('scheduler.pause', 'Pause'))}</button>`;

    // Skip one-shot trigger jobs in display
    if (j.id?.startsWith('_trigger_')) return '';

    // Last execution result
    let lastResult = '';
    if (j.last_success === true) {
      lastResult = `<span class="sched-badge success" title="${escapeHtml(j.last_summary ?? '')}">✓</span>`;
    } else if (j.last_success === false) {
      lastResult = `<span class="sched-badge failed" title="${escapeHtml(j.last_summary ?? '')}">✗</span>`;
    } else {
      lastResult = '<span style="color:var(--muted);font-size:11px;">—</span>';
    }

    return `<tr>
      <td><strong>${id}</strong>${desc ? `<span class="sched-job-desc">${escapeHtml(desc)}</span>` : ''}</td>
      <td><span${triggerTitle}>${trigger}</span></td>
      <td>${escapeHtml(nextRun)}</td>
      <td>${statusBadge}</td>
      <td>${lastResult}</td>
      <td><div class="sched-actions">
        <button type="button" class="sched-btn primary" data-action="trigger" data-job="${id}">${escapeHtml(tr('scheduler.trigger_now', 'Run Now'))}</button>
        ${pauseResumeBtn}
        <button type="button" class="sched-btn danger" data-action="delete" data-job="${id}" title="${escapeHtml(tr('scheduler.delete', 'Delete'))}">&times;</button>
      </div></td>
    </tr>`;
  }).join('');
}

export function renderHistory(data: any): void {
  const tbody = document.getElementById('schedHistoryBody');
  if (!tbody) return;

  const history: any[] = data?.data?.history ?? data?.history ?? [];

  if (history.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" class="sched-empty">${escapeHtml(tr('scheduler.no_history', 'No execution history'))}</td></tr>`;
    return;
  }

  tbody.innerHTML = history.slice(0, 50).map((h: any) => {
    const id = escapeHtml(h.job_id ?? '');
    const time = formatTimestamp(h.timestamp);
    const success = h.success ?? false;
    const statusBadge = success
      ? `<span class="sched-badge success">${escapeHtml(tr('scheduler.success', 'Success'))}</span>`
      : `<span class="sched-badge failed">${escapeHtml(tr('scheduler.failed', 'Failed'))}</span>`;
    const result = success
      ? escapeHtml(h.result_summary ?? '-')
      : escapeHtml(h.error ?? '-');

    return `<tr>
      <td><strong>${id}</strong></td>
      <td>${escapeHtml(time)}</td>
      <td>${statusBadge}</td>
      <td>${escapeHtml(result)}</td>
    </tr>`;
  }).join('');
}

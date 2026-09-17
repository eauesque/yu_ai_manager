/**
 * job-progress-ui.ts — DOM construction and UI update logic for
 * the global background job progress bar.
 *
 * Extracted from job-progress.ts to keep file sizes manageable.
 */

import { getProgressStack } from '../shared/progress-stack';
import { showToast } from '../shared/toast';
import { formatElapsedHms } from '../shared/date-format';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

export const COMPLETE_HIDE_DELAY_MS = 5_000;

/** Client-side tick for the elapsed-time readout (server polls every 2s). */
export const ELAPSED_TICK_MS = 1_000;

/** Job icon mapping */
export const JOB_ICONS: Record<string, string> = {
  scan: '\u27F3',
  'scan-all': '\u27F3',
  hash: '#',
  analysis: '\uD83D\uDD0D',
  'wd-tagger': '\uD83C\uDFF7',
  'semantic-index': '\uD83E\uDDE0',
  'yolo-detect': '\uD83D\uDCE6',
  'hash-backfill': '#',
  'chatlog-reprocess': '\uD83D\uDCAC',
  fpb: '\u2744',
};

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface JobInfo {
  job_id: string;
  label: string;
  running: boolean;
  phase: string;
  current: number;
  total: number;
  percent: number;
  message: string;
  detail: string;
  error: string | null;
  elapsed_seconds: number;
}

export interface JobsStatus {
  has_active: boolean;
  active: JobInfo[];
  recent: JobInfo[];
}

/* ------------------------------------------------------------------ */
/*  Module state (shared with job-progress.ts via setter/getter)       */
/* ------------------------------------------------------------------ */

let _barEl: HTMLElement | null = null;
const _barEls = new Map<string, HTMLElement>();
const _hideTimers = new Map<string, ReturnType<typeof setTimeout>>();
const _terminalToastJobIds = new Set<string>();
let _dynamicBar = false;
let _currentJobId: string | null = null;
const _dismissedJobIds = new Set<string>();
let _queueSize = 0;

/**
 * Per-job anchor for the elapsed readout: the last server-reported
 * `elapsed_seconds` plus the local clock reading at which it arrived.
 * The ticker extrapolates from this, and every poll re-anchors it, so
 * client drift cannot accumulate beyond one poll interval.
 */
const _elapsedAnchors = new Map<string, { seconds: number; at: number }>();
const _runningJobIds = new Set<string>();
let _elapsedTimer: ReturnType<typeof setInterval> | null = null;

/** Callbacks set by the main module to control polling */
let _stopPollFn: (() => void) | null = null;

export function setStopPollFn(fn: () => void): void {
  _stopPollFn = fn;
}

export function getCurrentJobId(): string | null {
  return _currentJobId;
}

export function setDismissedJobId(id: string | null): void {
  _dismissedJobIds.clear();
  if (id) _dismissedJobIds.add(id);
}

/* ------------------------------------------------------------------ */
/*  DOM helpers                                                        */
/* ------------------------------------------------------------------ */

function _safeDomId(id: string): string {
  return id.replace(/[^a-zA-Z0-9_-]/g, '-');
}

export function getOrCreateBar(jobId = 'global'): HTMLElement {
  const cached = _barEls.get(jobId);
  if (cached && cached.isConnected) {
    _barEl = cached;
    return cached;
  }

  // Reuse cached element if still in DOM
  if (jobId === 'global' && _barEl && _barEl.isConnected) return _barEl;

  // Check if an element already exists (e.g. from a previous call)
  const existingId = jobId === 'global'
    ? 'globalJobProgressBar'
    : `globalJobProgressBar-${_safeDomId(jobId)}`;
  const existing = document.getElementById(existingId);
  if (existing) {
    _barEl = existing;
    _barEls.set(jobId, existing);
    return existing;
  }

  const wrapper = document.createElement('div');
  wrapper.id = existingId;
  wrapper.className = 'scan-progress-bar';
  wrapper.dataset.jobId = jobId;
  wrapper.setAttribute('role', 'status');
  wrapper.setAttribute('aria-live', 'polite');
  wrapper.innerHTML =
    '<div class="scan-progress-content">' +
    '<div class="scan-progress-icon">\u27F3</div>' +
    '<div class="scan-progress-info">' +
    '<div class="scan-progress-text"></div>' +
    '<div class="scan-progress-details"></div>' +
    '</div>' +
    '<div class="scan-progress-track">' +
    '<div class="scan-progress-fill" style="width:0%"></div>' +
    '</div>' +
    '<div class="scan-progress-percent">0%</div>' +
    '<span class="scan-progress-elapsed" style="font-size:11px;opacity:0.75;font-variant-numeric:tabular-nums;"></span>' +
    '<span class="scan-queue-badge" style="display:none"></span>' +
    '<button class="scan-progress-close" type="button" aria-label="Dismiss">\u2715</button>' +
    '</div>';

  // Insert into the shared progress bar stack
  getProgressStack().appendChild(wrapper);

  // Wire dismiss button
  const dismiss = wrapper.querySelector('.scan-progress-close') as HTMLElement | null;
  if (dismiss) {
    dismiss.addEventListener('click', () => {
      _dismissedJobIds.add(jobId);
      wrapper.classList.remove('active');
      if (_stopPollFn) _stopPollFn();
    });
  }

  _barEl = wrapper;
  _barEls.set(jobId, wrapper);
  _dynamicBar = true;
  return wrapper;
}

export function showBar(bar: HTMLElement): void {
  if (!bar.classList.contains('active')) {
    bar.classList.add('active');
  }
}

/* ------------------------------------------------------------------ */
/*  Elapsed-time readout                                               */
/* ------------------------------------------------------------------ */

/** Paint one job's elapsed readout from its anchor, extrapolated to now. */
function _paintElapsed(jobId: string): void {
  const bar = _barEls.get(jobId);
  const anchor = _elapsedAnchors.get(jobId);
  if (!bar) return;
  const el = bar.querySelector('.scan-progress-elapsed') as HTMLElement | null;
  if (!el) return;
  if (!anchor) {
    el.textContent = '';
    return;
  }
  const extra = _runningJobIds.has(jobId) ? (Date.now() - anchor.at) / 1000 : 0;
  el.textContent = formatElapsedHms(anchor.seconds + extra);
}

function _stopElapsedTicker(): void {
  if (_elapsedTimer !== null) {
    clearInterval(_elapsedTimer);
    _elapsedTimer = null;
  }
}

/**
 * Run a 1s ticker while any job is running. Without it the readout only
 * moves when the 2s poll lands, which reads as a stuttering clock.
 */
function _ensureElapsedTicker(): void {
  if (_runningJobIds.size === 0) {
    _stopElapsedTicker();
    return;
  }
  if (_elapsedTimer !== null) return;
  _elapsedTimer = setInterval(() => {
    if (_runningJobIds.size === 0) {
      _stopElapsedTicker();
      return;
    }
    for (const jobId of _runningJobIds) _paintElapsed(jobId);
  }, ELAPSED_TICK_MS);
}

export function hideBar(bar: HTMLElement): void {
  bar.classList.remove('active');
}

export function updateBarUI(job: JobInfo): void {
  // If user dismissed this specific job, don't re-show it
  if (_dismissedJobIds.has(job.job_id) && job.running) return;
  // Non-running update -- clear dismiss so terminal state can be shown
  if (job.running) _terminalToastJobIds.delete(job.job_id);
  if (!job.running) _dismissedJobIds.delete(job.job_id);

  _currentJobId = job.job_id;
  const bar = getOrCreateBar(job.job_id);

  const existingTimer = _hideTimers.get(job.job_id);
  if (existingTimer) {
    clearTimeout(existingTimer);
    _hideTimers.delete(job.job_id);
  }

  const icon = bar.querySelector('.scan-progress-icon') as HTMLElement | null;
  const text = bar.querySelector('.scan-progress-text') as HTMLElement | null;
  const details = bar.querySelector('.scan-progress-details') as HTMLElement | null;
  const fill = bar.querySelector('.scan-progress-fill') as HTMLElement | null;
  const percent = bar.querySelector('.scan-progress-percent') as HTMLElement | null;

  if (icon) icon.textContent = JOB_ICONS[job.job_id] || '\u27F3';

  if (text) {
    const label = job.label || job.job_id;
    if (job.phase === 'complete') {
      text.textContent = `${label} \u2014 ${window.tr('job.status_complete', 'Complete')}`;
    } else if (job.phase === 'error') {
      text.textContent = `${label} \u2014 ${window.tr('job.status_error', 'Error')}`;
    } else if (job.phase === 'cancelled') {
      text.textContent = `${label} \u2014 ${window.tr('job.status_cancelled', 'Cancelled')}`;
    } else if (job.phase === 'counting' || job.phase === 'initializing') {
      text.textContent = `${label} \u2014 ${window.tr('job.status_preparing', 'Preparing...')}`;
    } else if (job.phase === 'cleanup') {
      text.textContent = `${label} \u2014 ${window.tr('job.status_postprocessing', 'Post-processing...')}`;
    } else {
      text.textContent = `${label}`;
    }
  }

  if (details) {
    if (job.total > 0) {
      details.textContent = `${job.current.toLocaleString()} / ${job.total.toLocaleString()}`;
      if (job.detail) details.textContent += ` \u2022 ${job.detail}`;
    } else if (job.detail) {
      details.textContent = job.detail;
    } else if (job.message) {
      details.textContent = job.message;
    } else {
      details.textContent = '';
    }
  }

  if (fill) fill.style.width = `${job.percent}%`;
  if (percent) percent.textContent = `${job.percent}%`;

  // Re-anchor the elapsed readout on every server-sourced update. SSE-derived
  // JobInfo carries no elapsed (0), so keep the previous anchor in that case
  // rather than resetting the clock to zero mid-run.
  if (job.running) _runningJobIds.add(job.job_id);
  else _runningJobIds.delete(job.job_id);
  if (job.elapsed_seconds > 0) {
    _elapsedAnchors.set(job.job_id, { seconds: job.elapsed_seconds, at: Date.now() });
  }
  _paintElapsed(job.job_id);
  _ensureElapsedTicker();

  // State classes
  bar.classList.remove('complete', 'error');
  if (job.phase === 'complete' || job.phase === 'cancelled') {
    bar.classList.add('complete');
    if (icon) icon.style.animation = 'none';
  } else if (job.phase === 'error') {
    bar.classList.add('error');
    if (icon) icon.style.animation = 'none';
  } else {
    if (icon) icon.style.animation = '';
  }

  showBar(bar);

  if (!job.running && !_terminalToastJobIds.has(job.job_id)) {
    const label = job.label || job.job_id;
    const status = job.phase === 'error'
      ? window.tr('job.status_error', 'Error')
      : job.phase === 'cancelled'
        ? window.tr('job.status_cancelled', 'Cancelled')
        : window.tr('job.status_complete', 'Complete');
    showToast(`${label} — ${status}`, job.phase === 'error');
    _terminalToastJobIds.add(job.job_id);
  }

  // Auto-hide completed/error/cancelled after delay
  if (!job.running) {
    _hideTimers.set(job.job_id, setTimeout(() => {
      hideBar(bar);
      _hideTimers.delete(job.job_id);
      _elapsedAnchors.delete(job.job_id);
      if (_stopPollFn) _stopPollFn();
    }, COMPLETE_HIDE_DELAY_MS));
  }
}

/* ------------------------------------------------------------------ */
/*  Queue badge                                                        */
/* ------------------------------------------------------------------ */

export function updateQueueBadge(count: number): void {
  _queueSize = count;
  const bar = _barEl;
  if (!bar) return;
  const badge = bar.querySelector('.scan-queue-badge') as HTMLElement | null;
  if (!badge) return;
  if (count > 0) {
    badge.textContent = `+${count}`;
    badge.title = window.tr('job.queue_badge', '{count} queued').replace('{count}', String(count));
    badge.style.display = '';
  } else {
    badge.style.display = 'none';
  }
}

/* ------------------------------------------------------------------ */
/*  SSE data unwrapper                                                 */
/* ------------------------------------------------------------------ */

/**
 * SSE events arrive as {type, timestamp, data: {...}, source}.
 * Extract the inner `data` payload.
 */
export function unwrapSseData(raw: unknown): Record<string, unknown> {
  const outer = raw as Record<string, unknown>;
  if (outer.data && typeof outer.data === 'object') {
    return outer.data as Record<string, unknown>;
  }
  return outer;
}

/** Map SSE event data to a synthetic JobInfo for display. */
export function sseToJobInfo(jobId: string, data: Record<string, unknown>): JobInfo {
  return {
    job_id: jobId,
    label: (data.label as string) || jobId,
    running: true,
    phase: (data.phase as string) || 'scanning',
    current: (data.current as number) || (data.processed as number) || 0,
    total: (data.total as number) || 0,
    percent: (data.percent as number) || 0,
    message: (data.message as string) || '',
    detail: (data.detail as string) || (data.current_file as string) || '',
    error: null,
    elapsed_seconds: 0,
  };
}

/** Return the cached bar element (or null). */
export function getBarElement(): HTMLElement | null {
  return _barEl;
}

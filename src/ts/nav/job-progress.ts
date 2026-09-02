/**
 * job-progress.ts — Global background job progress bar (all pages).
 *
 * On page load, checks /api/jobs/status for active jobs.
 * Subscribes to SSE events for real-time progress updates.
 * Polling runs as backup whenever SSE indicates a job is active.
 *
 * UI construction and rendering are in job-progress-ui.ts.
 */

import { getProgressStack } from '../shared/progress-stack';
import { getAppApi } from '../shared/browser-apis';
import { registerJobProgressEvents } from './job-progress-events';

import {
  updateBarUI,
  setStopPollFn,
  getCurrentJobId,
} from './job-progress-ui';

import type { JobInfo, JobsStatus } from './job-progress-ui';

// Re-export types and UI functions for backward compatibility
export type { JobInfo, JobsStatus } from './job-progress-ui';
export {
  JOB_ICONS,
  COMPLETE_HIDE_DELAY_MS,
  getOrCreateBar,
  showBar,
  hideBar,
  updateBarUI,
  updateQueueBadge,
  unwrapSseData,
  sseToJobInfo,
  getBarElement,
} from './job-progress-ui';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const POLL_INTERVAL_MS = 2_000;
/** How many consecutive "no active" polls before stopping */
const IDLE_POLLS_BEFORE_STOP = 3;
const INITIAL_STATUS_DELAY_MS = 2000;

/* ------------------------------------------------------------------ */
/*  State                                                              */
/* ------------------------------------------------------------------ */

let _pollTimer: ReturnType<typeof setInterval> | null = null;
/** Suppress poll while SSE is providing updates */
let _lastSseUpdate = 0;
/** Consecutive polls that found no active jobs */
let _idlePollCount = 0;
let _initialStatusQueued = false;
let _initialStatusChecked = false;
const _seenActiveJobIds = new Set<string>();

/* ------------------------------------------------------------------ */
/*  Polling (backup for SSE gaps)                                      */
/* ------------------------------------------------------------------ */

export function pollJobsStatusOnce(): Promise<void> {
  // Skip poll if SSE updated very recently
  if (Date.now() - _lastSseUpdate < POLL_INTERVAL_MS * 0.7) return Promise.resolve();

  const { apiFetch: fetcher } = getAppApi();

  return fetcher('/api/jobs/status')
    .then((r: Response) => r.json())
    .then((data: JobsStatus) => {
      if (data.has_active && data.active.length > 0) {
        _idlePollCount = 0;
        data.active.forEach((job) => {
          _seenActiveJobIds.add(job.job_id);
          updateBarUI(job);
        });
        return;
      }

      // No active jobs. If the bar is still showing a job that just moved
      // to `recent`, render its terminal state so updateBarUI's auto-hide
      // path runs. Without this, jobs without an SSE `*.complete` event
      // (e.g. wd_tagger) would stay frozen at the last running percent.
      const currentId = getCurrentJobId();
      const recent = Array.isArray(data.recent) ? data.recent : [];
      const done = recent.filter((j) => _seenActiveJobIds.has(j.job_id) || j.job_id === currentId);
      if (done.length > 0) {
        done.forEach(updateBarUI);
        _seenActiveJobIds.clear();
        _stopPoll();
        return;
      }
      // Don't stop immediately -- wait for consecutive idle polls
      _idlePollCount++;
      if (_idlePollCount >= IDLE_POLLS_BEFORE_STOP) {
        _stopPoll();
      }
    })
    .catch(() => { /* silent */ });
}

function _startPoll(): void {
  if (_pollTimer) return;
  _idlePollCount = 0;
  _pollTimer = setInterval(() => { void pollJobsStatusOnce(); }, POLL_INTERVAL_MS);
}

function _stopPoll(): void {
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
}

function _deferVisibleWork(fn: () => void, timeout = INITIAL_STATUS_DELAY_MS): void {
  const run = (): void => {
    if (document.hidden) return;
    fn();
  };

  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(run, { timeout });
    return;
  }

  setTimeout(run, timeout);
}

function _scheduleInitialStatusCheck(): void {
  if (_initialStatusQueued || _initialStatusChecked) return;
  _initialStatusQueued = true;

  const run = (): void => {
    _initialStatusQueued = false;
    if (document.hidden || _initialStatusChecked) return;
    _initialStatusChecked = true;

    const { apiFetch: fetcher } = getAppApi();
    fetcher('/api/jobs/status')
      .then((r: Response) => r.json())
      .then((data: JobsStatus) => {
        if (data.has_active && data.active.length > 0) {
          data.active.forEach((job) => {
            _seenActiveJobIds.add(job.job_id);
            updateBarUI(job);
          });
          _startPoll();
        }
      })
      .catch(() => { /* silent on initial check failure */ });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => _deferVisibleWork(run), { once: true });
    return;
  }

  _deferVisibleWork(run);
}

/* ------------------------------------------------------------------ */
/*  Initialization                                                     */
/* ------------------------------------------------------------------ */

export function initJobProgress(): void {
  // Register stop-poll callback so the UI module can stop polling on dismiss
  setStopPollFn(_stopPoll);

  // Ensure the shared progress stack exists on every page load.
  // Also adopt any orphaned progress bars (e.g. thumbProgressBar created
  // by background-preload before the stack existed).
  const stack = getProgressStack();
  document.querySelectorAll<HTMLElement>('.scan-progress-bar').forEach((bar) => {
    if (!stack.contains(bar)) {
      stack.appendChild(bar);
    }
  });

  registerJobProgressEvents(
    _startPoll,
    _stopPoll,
    () => _lastSseUpdate,
    (ts) => { _lastSseUpdate = ts; },
    () => { _idlePollCount = 0; },
  );

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      // Restart polling when tab becomes visible — recovers from SSE gap or
      // polling stopped while tab was hidden.
      if (!_pollTimer) {
        _idlePollCount = 0;
        _startPoll();
      }
      _scheduleInitialStatusCheck();
    }
  });

  // Delay the startup fetch until the page is visible and the main thread
  // has settled; SSE still covers real-time jobs immediately.
  _scheduleInitialStatusCheck();
}

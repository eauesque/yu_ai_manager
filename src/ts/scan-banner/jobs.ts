/**
 * scan-banner jobs orchestrator — polling lifecycle and initialization.
 * Converted from static/js/scan-banner/jobs.js
 */

import * as jobsCore from './jobs-core';
import { registerJobActions } from './jobs-actions';

const POLL_ACTIVE_MS = 5000;
const POLL_IDLE_MS = 30000;
const STARTUP_INTERRUPT_DELAY_MS = 3000;

let pollTimer: ReturnType<typeof setTimeout> | null = null;
let initialized = false;
let interruptedCheckQueued = false;
let interruptedCheckDone = false;

function _deferVisibleWork(fn: () => void, timeout = STARTUP_INTERRUPT_DELAY_MS): void {
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

function _scheduleInterruptedCheck(): void {
  if (interruptedCheckQueued || interruptedCheckDone) return;
  interruptedCheckQueued = true;

  const run = (): void => {
    interruptedCheckQueued = false;
    if (document.hidden) return;
    interruptedCheckDone = true;
    checkInterruptedScan();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => _deferVisibleWork(run), { once: true });
    return;
  }

  _deferVisibleWork(run);
}

export function pollJobStatus(): Promise<void> | undefined {
  return jobsCore.pollJobStatus();
}

export function checkInterruptedScan(): void {
  return jobsCore.checkInterruptedScan();
}

function scheduleNextPoll(): void {
  const interval = jobsCore.hasActiveJobs() ? POLL_ACTIVE_MS : POLL_IDLE_MS;
  pollTimer = setTimeout(async () => {
    await pollJobStatus();
    if (pollTimer !== null) scheduleNextPoll();
  }, interval);
}

export function startPolling(): void {
  if (pollTimer) return;
  pollJobStatus()?.catch(() => {});
  scheduleNextPoll();
}

export function stopPolling(): void {
  if (!pollTimer) return;
  clearTimeout(pollTimer);
  pollTimer = null;
}

export function init(): void {
  if (initialized) return;
  initialized = true;

  const api = {
    checkInterruptedScan: checkInterruptedScan,
    pollJobStatus: pollJobStatus,
    startPolling: startPolling,
    stopPolling: stopPolling,
    ui: function () { return jobsCore.ui; },
  };
  registerJobActions(api);

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) stopPolling();
    else _scheduleInterruptedCheck();
  });

  _scheduleInterruptedCheck();
}

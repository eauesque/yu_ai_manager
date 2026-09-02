/**
 * scan-banner jobs core — polling for interrupted scan detection.
 *
 * Active job progress display is handled by nav/job-progress.ts.
 * This module polls /api/jobs/status to:
 *   - Track hasActiveJobs state
 *   - Detect when all jobs finish to hide interrupted banner
 */

import * as ui from './ui';

export { ui };

let _hasActiveJobs = false;
export function hasActiveJobs(): boolean { return _hasActiveJobs; }

export async function pollJobStatus(): Promise<void> {
  try {
    const res = await fetch('/api/jobs/status');
    if (!res.ok) return;
    const data = await res.json();
    const activeJobs = (data.active || []) as { job_id: string; running?: boolean }[];

    const wasActive = _hasActiveJobs;
    _hasActiveJobs = activeJobs.length > 0;

    // A scan started: clear interrupted toast (scan_state.json was wiped on start)
    if (_hasActiveJobs && ui.isInterruptedShown()) {
      ui.hideBanner();
    }

    // Jobs just finished: re-check whether interrupted state is still valid
    if (wasActive && !_hasActiveJobs) {
      checkInterruptedScan();
    }
  } catch (_e) {
    // ignore network errors
  }
}

export function checkInterruptedScan(): void {
  fetch('/api/scan/interrupted')
    .then(function (r) {
      return r.json();
    })
    .then(function (data) {
      if (!data.interrupted) {
        // Scan completed or state was cleared — hide any lingering toast
        ui.hideBanner();
        return;
      }
      ui.showInterrupted(data);
    })
    .catch(function () {});
}

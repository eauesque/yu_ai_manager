/**
 * scan-banner jobs actions — cancel, resume, dismiss handlers.
 * Converted from static/js/scan-banner/jobs-actions.js
 */

import { getAppApi } from '../shared/browser-apis';
import { installWindowApi } from '../shared/window-api';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

export interface JobsApi {
  pollJobStatus?: () => Promise<void> | void;
  startPolling?: () => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ui?: () => any;
}

export function registerJobActions(api: JobsApi): void {
  if (!api) return;

  const cancelScan = async function () {
    try {
      const res = await fetch('/api/scan/cancel', { method: 'POST', headers: XHR_HEADERS });
      if (res.ok) api.pollJobStatus?.();
    } catch (e) {
      console.error('Failed to cancel scan:', e);
    }
  };

  const resumeScan = function () {
    fetch('/api/scan/resume', { method: 'POST', headers: XHR_HEADERS })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data.status === 'resumed') {
          api.ui?.()?.showResumeMessage?.();
          api.startPolling?.();
        } else {
          alert(data.error || getAppApi().tr('scan.banner.resume_failed', 'Failed to resume'));
        }
      });
  };

  const dismissScan = function () {
    fetch('/api/scan/dismiss', { method: 'POST', headers: XHR_HEADERS }).then(function () {
      api.ui?.()?.hideBanner?.();
    });
  };

  installWindowApi('scanBannerApi', {
    cancelScan,
    resumeScan,
    dismissScan,
  });
}

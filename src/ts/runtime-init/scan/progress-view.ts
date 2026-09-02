/**
 * Scan progress UI view — updates DOM elements with scan status.
 */

import { getAppApi, getNavApi, getSearchResultsApi } from '../../shared/browser-apis';

export interface ScanStatus {
  phase: string;
  current: number;
  total: number;
  percent: number;
  current_file?: string;
  error?: string;
}

export function updateScanProgress(status: ScanStatus): void {
  const { tr } = getAppApi();
  const text = document.getElementById('scanProgressText');
  const details = document.getElementById('scanProgressDetails');
  const fill = document.getElementById('scanProgressFill') as HTMLElement | null;
  const percent = document.getElementById('scanProgressPercent');

  if (!text || !details || !fill || !percent) return;

  let phaseText = '';
  switch (status.phase) {
    case 'counting':
      phaseText = tr('scan.phase.counting');
      break;
    case 'scanning':
      phaseText = tr('scan.phase.scanning');
      break;
    case 'initializing':
      phaseText = tr('scan.phase.initializing');
      break;
    default:
      phaseText = status.phase;
  }
  text.textContent = phaseText;

  details.textContent = tr('scan.details.progress', { current: status.current.toLocaleString(), total: status.total.toLocaleString() });
  if (status.current_file) details.textContent += ` \u2022 ${status.current_file}`;

  fill.style.width = `${status.percent}%`;
  percent.textContent = `${status.percent}%`;
}

export function onScanComplete(status: ScanStatus): void {
  const { tr } = getAppApi();
  const { showToast } = getNavApi();
  const { runSearch } = getSearchResultsApi();
  const bar = document.getElementById('scanProgressBar');
  const text = document.getElementById('scanProgressText');
  const details = document.getElementById('scanProgressDetails');
  if (!bar || !text || !details) return;

  bar.classList.add('complete');
  text.textContent = tr('scan.complete_label');
  details.textContent = tr('scan.details.processed', { total: status.total.toLocaleString() });
  showToast(tr('scan.complete_toast', { count: status.total }));

  setTimeout(() => {
    if (bar.classList.contains('complete')) {
      bar.classList.remove('active');
      if (confirm(tr('scan.complete_confirm_refresh'))) runSearch();
    }
  }, 5000);
}

export function onScanError(status: ScanStatus): void {
  const { tr } = getAppApi();
  const { showToast } = getNavApi();
  const bar = document.getElementById('scanProgressBar');
  const text = document.getElementById('scanProgressText');
  const details = document.getElementById('scanProgressDetails');
  if (!bar || !text || !details) return;

  bar.classList.add('error');
  text.textContent = tr('scan.failed_label');
  details.textContent = status.error || tr('scan.unknown_error');
  showToast(tr('scan.failed_toast', { error: status.error || 'Unknown error' }), true);
}

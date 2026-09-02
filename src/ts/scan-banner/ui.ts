/**
 * scan-banner UI — interrupted scan toast + legacy API stubs.
 *
 * Active job progress display is handled by nav/job-progress.ts (bottom bar).
 * This module now only handles:
 *   - Interrupted scan resume/dismiss toast
 *   - Legacy API surface (renderJobs → no-op, hideBanner, scheduleHide)
 */

interface InterruptedData {
  total: number;
  current: number;
  root: string;
  interrupted_at?: number;
}

interface JobData {
  job_id: string;
  percent?: number;
  message?: string;
  label?: string;
  phase?: string;
  running?: boolean;
  elapsed_seconds?: number;
}

let _interruptedShown = false;
let _interruptedToast: HTMLElement | null = null;

export function isInterruptedShown(): boolean {
  return _interruptedShown;
}

function _tr(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback) || fallback;
}

function _esc(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

/* ── Interrupted scan toast ── */

export function showInterrupted(data: InterruptedData): void {
  // Remove existing toast if any
  hideInterruptedToast();

  const pct = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0;
  let timeStr = '';
  if (data.interrupted_at) {
    const d = new Date(data.interrupted_at * 1000);
    timeStr = d.toLocaleString();
  }

  const toast = document.createElement('div');
  toast.id = 'interruptedScanToast';
  toast.style.cssText = [
    'position:fixed',
    'bottom:80px',
    'right:20px',
    'z-index:870',
    'background:linear-gradient(135deg, #e65100 0%, #bf360c 100%)',
    'color:#fff',
    'padding:14px 18px',
    'border-radius:10px',
    'box-shadow:0 4px 20px rgba(0,0,0,0.4)',
    'font-size:13px',
    'max-width:400px',
    'animation:toast-slide-in 0.3s ease',
  ].join(';');

  toast.innerHTML =
    '<div style="font-weight:600;margin-bottom:6px;">' +
    '\u26A0\uFE0F ' + _tr('scan.banner.interrupted', 'Previous scan was interrupted') +
    '</div>' +
    '<div style="font-size:12px;opacity:0.9;margin-bottom:10px;">' +
    _esc(data.root) + '<br>' +
    data.current + ' / ' + data.total + ' (' + pct + '%)' +
    (timeStr ? ' \u2014 ' + timeStr : '') +
    '</div>' +
    '<div style="display:flex;gap:8px;">' +
    '<button id="interruptedResumeBtn" style="flex:1;padding:6px 12px;border-radius:6px;border:none;background:#4CAF50;color:#fff;cursor:pointer;font-size:12px;font-weight:600;">' +
    '\u25B6 ' + _tr('scan.banner.resume', 'Resume') +
    '</button>' +
    '<button id="interruptedDismissBtn" style="flex:1;padding:6px 12px;border-radius:6px;border:none;background:rgba(255,255,255,0.2);color:#fff;cursor:pointer;font-size:12px;">' +
    '\u2715 ' + _tr('scan.banner.dismiss', 'Dismiss') +
    '</button>' +
    '</div>';

  document.body.appendChild(toast);
  _interruptedToast = toast;
  _interruptedShown = true;

  // Wire buttons
  const resumeBtn = toast.querySelector('#interruptedResumeBtn');
  if (resumeBtn) {
    resumeBtn.addEventListener('click', () => {
      getScanBannerApi().resumeScan();
      hideInterruptedToast();
    });
  }
  const dismissBtn = toast.querySelector('#interruptedDismissBtn');
  if (dismissBtn) {
    dismissBtn.addEventListener('click', () => {
      getScanBannerApi().dismissScan();
      hideInterruptedToast();
    });
  }
}

function hideInterruptedToast(): void {
  if (_interruptedToast) {
    _interruptedToast.remove();
    _interruptedToast = null;
  }
  _interruptedShown = false;
}

/* ── Legacy stubs — progress is now handled by nav/job-progress.ts ── */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function renderJobs(_visibleJobs: JobData[]): void {
  // No-op: active job progress is displayed by the bottom progress bar
}

export function hideBanner(): void {
  hideInterruptedToast();
}

export function scheduleHide(_ms: number): void {
  // No-op: auto-hide is handled by nav/job-progress.ts
}

export function createBanner(): HTMLElement {
  // Return a dummy element for backwards compat
  return document.createElement('div');
}

export function showResumeMessage(): void {
  _interruptedShown = false;
  hideInterruptedToast();
  getNavApi().showToast(_tr('scan.banner.resuming', 'Resuming scan...'));
}
import { getAppApi, getNavApi, getScanBannerApi } from '../shared/browser-apis';

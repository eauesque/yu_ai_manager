/**
 * tools/copy.ts — Clipboard copy with visual feedback badge.
 * Converted from runtime-tools-copy.js
 */

import { getAppApi, getDetailModalApi, getNavApi } from '../../shared/browser-apis';

export async function copyWithFeedback(
  text: string,
  triggerEl: HTMLElement | null | undefined,
  label?: string,
): Promise<boolean> {
  if (!text) return false;
  // Resolve APIs at call time (not module load time) to avoid init-order issues
  const { tr } = getAppApi();
  const { copyToClipboard } = getDetailModalApi();
  const { showToast } = getNavApi();
  const success = await copyToClipboard(text);
  const msg = success
    ? (tr('toast.copy_with_label', { label: label || '' }) || 'Copied')
    : (tr('toast.copy_failed', 'Copy failed') || 'Copy failed');
  showToast(msg, !success);

  if (triggerEl) {
    const old = triggerEl.querySelector('.copy-badge');
    if (old) old.remove();

    const badge = document.createElement('span');
    badge.className = 'copy-badge';
    badge.textContent = success ? '\u2713' : '\u00d7';
    badge.style.cssText = `
      position:absolute;top:-6px;right:-6px;
      font-size:11px;font-weight:bold;line-height:1;
      color:${success ? '#2ecc71' : '#e74c3c'};
      background:${success ? 'rgba(46,204,113,0.15)' : 'rgba(231,76,60,0.15)'};
      border-radius:50%;width:16px;height:16px;
      display:flex;align-items:center;justify-content:center;
      pointer-events:none;
    `;
    triggerEl.style.position = 'relative';
    triggerEl.appendChild(badge);
    setTimeout(() => badge.remove(), 1800);
  }

  return success;
}

export function notifyCopy(
  btn: HTMLElement | null | undefined,
  ok: boolean,
): void {
  if (!btn) return;

  const oldBadge = btn.querySelector('.copy-badge');
  if (oldBadge) oldBadge.remove();

  const badge = document.createElement('span');
  badge.className = 'copy-badge';
  badge.textContent = ok ? '\u2713' : '\u00d7';
  badge.style.cssText = `
    position:absolute;top:-6px;right:-6px;
    font-size:11px;font-weight:bold;line-height:1;
    color:${ok ? '#2ecc71' : '#e74c3c'};
    background:${ok ? 'rgba(46,204,113,0.15)' : 'rgba(231,76,60,0.15)'};
    border-radius:50%;width:16px;height:16px;
    display:flex;align-items:center;justify-content:center;
    pointer-events:none;
  `;
  btn.style.position = 'relative';
  btn.appendChild(badge);
  setTimeout(() => badge.remove(), 1800);

  getNavApi().showToast(ok ? (getAppApi().tr('toast.copy_done', 'Copied') || 'Copied') : (getAppApi().tr('toast.copy_failed', 'Copy failed') || 'Copy failed'), !ok);
}

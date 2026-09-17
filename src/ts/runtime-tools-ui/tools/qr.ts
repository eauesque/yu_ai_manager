/**
 * tools/qr.ts — QR share panel: show, generate, copy, download.
 * Converted from runtime-tools-qr.js
 */

import { getAppApi } from '../../shared/browser-apis';
import { buildQrPayload, renderQr } from './qr-core';
import { copyWithFeedback } from './copy';

const { apiFetch, escapeHtml, tr, reportError } = getAppApi();

function _isLocalhost(): boolean {
  const h = window.location.hostname;
  return h === 'localhost' || h === '127.0.0.1' || h === '::1';
}

export async function showQRShare(fileId: number): Promise<void> {
  const panel = document.getElementById(`qrPanel-${fileId}`);
  if (!panel) return;

  const isVisible = getComputedStyle(panel).display !== 'none';
  if (isVisible) {
    panel.style.display = 'none';
    return;
  }

  panel.style.display = 'block';
  panel.innerHTML = `<div style="color:#888;font-size:12px;">${escapeHtml(tr('common.loading'))}</div>`;

  try {
    const res = await apiFetch(`/api/share/${fileId}`);
    const shareData = await res.json();

    if (shareData.error) {
      panel.innerHTML = `<div style="color:#e74c3c;font-size:12px;">${escapeHtml(tr('common.error_prefix'))} ${escapeHtml(shareData.error)}</div>`;
      return;
    }

    panel.dataset.shareJson = JSON.stringify(shareData);
    panel.dataset.fileId = String(fileId);
    const isLocal = _isLocalhost();

    panel.innerHTML = `
      <div style="margin:8px 0;">
        <label style="font-size:12px;color:#aaa;">${escapeHtml(tr('qr.content_label'))}</label>
        <select id="qrMode-${fileId}"
                style="font-size:12px;padding:3px 6px;border-radius:4px;border:1px solid #555;background:var(--card,#2a2a2a);color:var(--text,#eee);margin-left:4px;">
          <option value="positive">${escapeHtml(tr('qr.mode.positive'))}</option>
          <option value="negative">${escapeHtml(tr('qr.mode.negative'))}</option>
          <option value="meta">${escapeHtml(tr('qr.mode.meta'))}</option>
          ${isLocal
            ? `<option value="url" disabled>${escapeHtml(tr('qr.mode.url_local_disabled'))}</option>`
            : `<option value="url">${escapeHtml(tr('qr.mode.url'))}</option>`}
        </select>
      </div>
      <div style="background:white;display:inline-block;padding:12px;border-radius:8px;margin:4px 0;">
        <div id="qrCanvas-${fileId}"></div>
      </div>
      <div id="qrInfo-${fileId}" style="font-size:11px;color:#888;margin:4px 0;"></div>
      <div style="display:flex;gap:6px;justify-content:center;flex-wrap:wrap;">
        <button type="button" class="btn-small" data-action="copy-qr-content" style="padding:4px 10px;font-size:11px;">\uD83D\uDCCB ${escapeHtml(tr('qr.copy_text'))}</button>
        <button type="button" class="btn-small" data-action="download-qr" style="padding:4px 10px;font-size:11px;">\uD83D\uDCBE ${escapeHtml(tr('qr.save_image'))}</button>
      </div>
      <div id="qrCopyStatus-${fileId}" style="font-size:11px;color:#2ecc71;margin-top:4px;"></div>
    `;

    const modeSelect = document.getElementById(`qrMode-${fileId}`) as HTMLSelectElement | null;
    modeSelect?.addEventListener('change', () => generateQR(fileId));
    panel.querySelector<HTMLElement>('[data-action="copy-qr-content"]')
      ?.addEventListener('click', (event) => copyQRContent(fileId, event.currentTarget as HTMLElement | null));
    panel.querySelector<HTMLElement>('[data-action="download-qr"]')
      ?.addEventListener('click', () => downloadQR(fileId));

    generateQR(fileId);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    panel.innerHTML = `<div style="color:#e74c3c;font-size:12px;">${escapeHtml(tr('common.error_prefix'))} ${escapeHtml(message)}</div>`;
    reportError('qr/showQRShare', err, { fileId });
  }
}

export function generateQR(fileId: number): void {
  const panel = document.getElementById(`qrPanel-${fileId}`);
  const modeEl = document.getElementById(`qrMode-${fileId}`) as HTMLSelectElement | null;
  const mode = modeEl?.value || 'positive';
  const shareData = JSON.parse(panel?.dataset?.shareJson || '{}');
  const info = document.getElementById(`qrInfo-${fileId}`);

  const built = buildQrPayload(mode, shareData);
  if (!built.ok) {
    const canvas = document.getElementById(`qrCanvas-${fileId}`);
    if (canvas) canvas.innerHTML = `<div style="color:#e74c3c;font-size:12px;padding:20px;">${escapeHtml(tr('qr.text_too_long'))}</div>`;
    if (info) {
      info.textContent = built.infoText;
      if (built.diagText) {
        const diag = document.createElement('div');
        diag.style.cssText = 'font-size:10px;color:#e67e22;margin-top:2px;font-family:monospace;';
        diag.textContent = built.diagText;
        info.after(diag);
      }
    }
    if (panel) panel.dataset.qrContent = built.qrText;
    // Only record to session mailbox when diagText is present (unexpected payload state),
    // not for the normal user-facing "text too long" path.
    if (built.diagText) {
      reportError('qr/generateQR', new Error(built.infoText), {
        fileId,
        mode,
        diagText: built.diagText,
        bytes: built.qrText ? new TextEncoder().encode(built.qrText).length : 0,
      });
    }
    return;
  }

  // When a compact fallback is active, the copy button copies the ORIGINAL text
  // (full prompt), not the compact QR payload.
  if (panel) panel.dataset.qrContent = built.copyText ?? built.qrText;
  if (info) {
    info.textContent = built.infoText;
    if (built.fallbackNote) {
      const note = document.createElement('div');
      note.style.cssText = 'font-size:10px;color:#e67e22;margin-top:2px;';
      note.textContent = built.fallbackNote;
      info.after(note);
    }
  }

  const container = document.getElementById(`qrCanvas-${fileId}`);
  if (!container) return;
  renderQr(container, built.qrText);
}

export function copyQRContent(fileId: number, triggerEl?: HTMLElement | null): void {
  const panel = document.getElementById(`qrPanel-${fileId}`);
  const text = panel?.dataset?.qrContent || '';
  if (!text) return;
  void copyWithFeedback(text, triggerEl || null, '');
}

export function downloadQR(fileId: number): void {
  const canvas = document.querySelector(`#qrCanvas-${fileId} canvas`) as HTMLCanvasElement | null;
  if (!canvas) return;
  const url = canvas.toDataURL('image/png');
  const a = document.createElement('a');
  a.href = url;
  a.download = `tagdb-share-${fileId}.png`;
  a.click();
}

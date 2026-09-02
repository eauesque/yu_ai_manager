/**
 * Share QR — reads QR codes from image files and decodes share data.
 * Converted from static/js/share/share-qr.js
 */

import { getAppApi } from '../shared/browser-apis';
import { renderShareData, escHtml } from './page';
import { copyToClipboard } from '../shared/clipboard';
import jsQR from 'jsqr';

/** i18n helper: use window.tr if available, otherwise return fallback. */
function _t(key: string, fallback: string = ''): string {
  return getAppApi().tr(key, fallback);
}

/**
 * Decode a QR code from a file input and process the result.
 * If the QR contains share data URL, renders it directly.
 * Otherwise shows the raw content with a copy button.
 */
export async function decodeQRFile(input: HTMLInputElement): Promise<void> {
  const status = document.getElementById('qrDecodeStatus');
  const resultDiv = document.getElementById('qrDecodeResult');
  const file = input.files?.[0];
  if (!file || !status || !resultDiv) return;

  status.textContent = _t('share.qr_reading', 'Reading...');
  resultDiv.style.display = 'none';

  try {
    const img = new Image();
    img.src = URL.createObjectURL(file);
    await new Promise<void>((resolve) => {
      img.onload = () => resolve();
    });

    const canvas = document.createElement('canvas');
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      status.textContent = _t('common.error_prefix', 'Error:') + ' Canvas context unavailable';
      return;
    }

    ctx.drawImage(img, 0, 0);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    URL.revokeObjectURL(img.src);

    const code = jsQR(imageData.data, imageData.width, imageData.height);
    if (!code) {
      status.textContent = _t('share.qr_not_found', 'QR code not found');
      return;
    }

    const text = code.data;
    status.textContent = _t('share.qr_success', 'Read successfully')
      + ' (' + text.length + ' chars)';

    // Try to decode as a share URL
    if (text.startsWith('http') && text.includes('data=')) {
      try {
        const url = new URL(text);
        const encoded = url.searchParams.get('data');
        if (encoded) {
          const json = decodeURIComponent(escape(atob(encoded)));
          const data = JSON.parse(json);
          renderShareData(data);
          status.textContent = _t('share.qr_restored', 'Share data restored');
          return;
        }
      } catch {
        // Fall through to generic preview.
      }
    }

    // Generic content preview
    let displayHtml = '';

    try {
      const parsed = JSON.parse(text);
      displayHtml = `<pre style="background:var(--card,#1e1e1e);padding:12px;border-radius:6px;overflow-x:auto;font-size:12px;color:var(--text,#eee);white-space:pre-wrap;">${escHtml(JSON.stringify(parsed, null, 2))}</pre>`;
    } catch {
      displayHtml = `<div style="background:var(--card,#1e1e1e);padding:12px;border-radius:6px;font-size:13px;color:var(--text,#eee);white-space:pre-wrap;">${escHtml(text)}</div>`;
    }

    const copyLabel = _t('toast.copy_done', 'Copied');
    const copyBtn = _t('share.copy_btn', 'Copy');
    displayHtml += `<button type="button" data-share-qr-copy="1"
                 style="margin-top:8px;padding:6px 12px;font-size:12px;cursor:pointer;border-radius:4px;border:1px solid #555;background:var(--card);color:var(--text);">\uD83D\uDCCB ${copyBtn}</button>`;

    resultDiv.innerHTML = displayHtml;
    resultDiv.style.display = '';
    resultDiv.querySelector<HTMLElement>('[data-share-qr-copy="1"]')?.addEventListener('click', () => {
      void copyToClipboard(text).then(() => {
        const btn = resultDiv.querySelector<HTMLElement>('[data-share-qr-copy="1"]');
        if (btn) btn.textContent = '\u2705 ' + copyLabel;
      });
    });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    status.textContent = _t('common.error_prefix', 'Error:') + ' ' + message;
  }
}

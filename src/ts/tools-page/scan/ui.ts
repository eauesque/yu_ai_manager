/**
 * scan/ui.ts -- Scan progress UI helpers.
 * Converted from tools-scan-ui.js
 */

import { getAppApi } from '../../shared/browser-apis';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export function setScanProgressUi(
  titleText: string,
  subText: string,
): HTMLElement {
  const resultBox = document.getElementById('scanResult')!;
  resultBox.classList.add('show');
  resultBox.innerHTML = `
    <div style="padding:10px;">
      <div style="margin-bottom:8px;">${titleText}</div>
      <div style="background:rgba(0,0,0,0.3);border-radius:4px;height:24px;overflow:hidden;margin:8px 0;">
        <div id="scanProgressBar" style="height:100%;background:linear-gradient(90deg,#667eea,#764ba2);width:0%;transition:width 0.3s;border-radius:4px;"></div>
      </div>
      <div id="scanProgressText" style="font-size:12px;color:#888;">${subText}</div>
    </div>
  `;
  return resultBox;
}

export function setScanError(message: string): void {
  const resultBox = document.getElementById('scanResult');
  if (!resultBox) return;
  resultBox.classList.add('show');
  resultBox.innerHTML =
    '<p style="color:#e74c3c;">' +
    _t('tools.error', 'Error') +
    ': ' +
    message +
    '</p>';
}

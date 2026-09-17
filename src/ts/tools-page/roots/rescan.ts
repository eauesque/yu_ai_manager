/**
 * roots/rescan.ts -- Rescan dialog for individual folders.
 * Converted from tools-roots-rescan.js
 */

import { getAppApi } from '../../shared/browser-apis';
import { startScan } from '../scan/start';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export function closeRescanDialog(): void {
  const dialog = document.getElementById('rescanDialog');
  if (dialog) dialog.style.display = 'none';
}

export function showRescanDialog(path: string): void {
  let modal = document.getElementById('rescanDialog');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'rescanDialog';
    modal.style.cssText =
      'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.6);z-index:9999;display:flex;align-items:center;justify-content:center;';
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal!.style.display = 'none';
    });
    document.body.appendChild(modal);
  }

  modal.innerHTML = `
    <div style="background:#2a2a3a;border-radius:10px;padding:24px;max-width:450px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.5);">
      <h3 style="margin:0 0 12px;color:#fff;font-size:16px;">&#x1F504; ${_t('tools.rescan', 'Rescan')}</h3>
      <p style="margin:0 0 16px;color:#aaa;font-size:13px;word-break:break-all;">${path}</p>
      <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:16px;">
        <label style="display:flex;align-items:center;gap:8px;color:#ccc;font-size:13px;">
          <input type="checkbox" id="rescanRecursive" checked> ${_t('tools.include_subfolders', 'Include subfolders')}
        </label>
        <label style="display:flex;align-items:center;gap:8px;color:#ccc;font-size:13px;">
          <input type="checkbox" id="rescanZips"> ${_t('tools.search_zips', 'Search inside ZIP files')}
        </label>
        <label style="display:flex;align-items:center;gap:8px;color:#ccc;font-size:13px;">
          <input type="checkbox" id="rescanForce"> ${_t('tools.force_rescan', 'Force rescan (reanalyze all files)')}
        </label>
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end;">
        <button data-action="toolsPageApi.closeRescanDialog" class="btn btn-secondary" style="padding:8px 16px;">${_t('tools.cancel', 'Cancel')}</button>
        <button data-action="toolsPageApi.executeRescan" data-action-arg="${btoa(unescape(encodeURIComponent(path)))}" class="btn btn-primary" style="padding:8px 16px;">${_t('tools.start_scan', 'Start Scan')}</button>
      </div>
    </div>
  `;
  modal.style.display = 'flex';
}

export function executeRescan(pathB64: string): void {
  const path = decodeURIComponent(escape(atob(pathB64)));
  const recursive = (document.getElementById('rescanRecursive') as HTMLInputElement).checked;
  const scanZips = (document.getElementById('rescanZips') as HTMLInputElement).checked;
  const force = (document.getElementById('rescanForce') as HTMLInputElement).checked;

  const dialog = document.getElementById('rescanDialog');
  if (dialog) dialog.style.display = 'none';

  const scanPath = document.getElementById('scanPath') as HTMLInputElement | null;
  const scanRecursive = document.getElementById('scanRecursive') as HTMLInputElement | null;
  const scanZipsEl = document.getElementById('scanZips') as HTMLInputElement | null;
  const scanForce = document.getElementById('scanForce') as HTMLInputElement | null;

  if (scanPath) scanPath.value = path;
  if (scanRecursive) scanRecursive.checked = recursive;
  if (scanZipsEl) scanZipsEl.checked = scanZips;
  if (scanForce) scanForce.checked = force;
  startScan();
}

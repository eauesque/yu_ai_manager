/**
 * scan/start.ts -- Start a folder scan.
 * Converted from tools-scan-start.js
 */

import { getAppApi } from '../../shared/browser-apis';
import { apiFetch } from '../api';
import { loadDbInfo } from '../db-info';
import { loadScanRoots } from '../roots/list';
import { setScanProgressUi } from './ui';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

interface ScanStatus {
  percent?: number;
  message?: string;
  current: number;
  total: number;
  phase?: string;
  current_file?: string;
  running?: boolean;
}

export async function startScan(): Promise<void> {
  const path = (document.getElementById('scanPath') as HTMLInputElement).value.trim();
  if (!path) {
    alert(_t('tools.enter_folder_path', 'Please enter a folder path'));
    return;
  }

  const recursive = (document.getElementById('scanRecursive') as HTMLInputElement).checked;
  const scanZips = (document.getElementById('scanZips') as HTMLInputElement).checked;
  const forceRescan = (document.getElementById('scanForce') as HTMLInputElement).checked;

  const resultBox = setScanProgressUi(
    '\uD83D\uDD0D <strong>Checking database health...</strong>',
    _t('tools.preparing', 'Preparing...'),
  );

  try {
    const startRes = await apiFetch('/api/scan/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        root: path,
        recursive,
        force: forceRescan,
        scan_zips: scanZips,
      }),
    });
    const startData: { error?: string } = await startRes.json();

    if (startData.error) {
      resultBox.innerHTML =
        '<p style="color: #e74c3c;">' +
        _t('tools.error', 'Error') +
        ': ' +
        startData.error +
        '</p>';
      return;
    }

    // Progress bar is handled by nav/job-progress.ts (SSE + polling).
    // Here we only poll to detect completion and update the Tools page result box.
    const pollInterval = setInterval(async () => {
      try {
        const statusRes = await fetch('/api/scan/status');
        const status: ScanStatus = await statusRes.json();

        if (status.phase === 'complete') {
          clearInterval(pollInterval);
          resultBox.innerHTML = `
            <p style="color: #2ecc71;">${'\u2713 ' + _t('tools.scan_complete', 'Scan complete')}</p>
            <div class="stat-row">
              <span>${_t('tools.processed_files', 'Processed files:')}</span>
              <span>${status.current.toLocaleString()}</span>
            </div>
          `;
          loadDbInfo();
          loadScanRoots();
        } else if (status.phase === 'error') {
          clearInterval(pollInterval);
          resultBox.innerHTML =
            '<p style="color: #e74c3c;">' +
            _t('tools.error', 'Error') +
            ': ' +
            (status.current_file || 'Unknown error') +
            '</p>';
        }
      } catch {
        // ignore transient polling errors
      }
    }, 2000);

    setTimeout(() => clearInterval(pollInterval), 1800000);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    resultBox.innerHTML =
      '<p style="color: #e74c3c;">' +
      _t('tools.error', 'Error') +
      ': ' +
      msg +
      '</p>';
  }
}

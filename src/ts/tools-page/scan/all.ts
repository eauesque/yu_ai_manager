/**
 * scan/all.ts -- Scan all registered folders.
 * Converted from tools-scan-all.js
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
  current?: number;
  total?: number;
  phase?: string;
  running?: boolean;
}

export async function startScanAll(): Promise<void> {
  const force = (document.getElementById('scanForce') as HTMLInputElement).checked;

  const resultBox = setScanProgressUi(
    '\uD83D\uDD04 <strong>' +
      _t('tools.rescanning_all', 'Rescanning all folders...') +
      '</strong>',
    _t('tools.checking_roots', 'Checking registered folders...'),
  );
  const btn = document.getElementById('scanAllBtn') as HTMLButtonElement | null;
  if (btn) {
    btn.disabled = true;
    btn.textContent = '\uD83D\uDD04 ' + _t('tools.scanning', 'Scanning...');
  }

  try {
    const startRes = await apiFetch('/api/scan-all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force }),
    });
    const startData: { error?: string; status?: string; position?: number } =
      await startRes.json();

    if (startRes.status === 202) {
      const pos = startData.position || 1;
      resultBox.innerHTML =
        '<p style="color:#3498db;">' +
        _t('tools.queued', 'Queued') +
        `: ${pos}` +
        _t('tools.queued_suffix', ' 番目に追加されました') +
        '</p>';
      if (btn) {
        btn.disabled = false;
        btn.textContent =
          '\uD83D\uDD04 ' + _t('tools.rescan_all', 'Rescan All');
      }
      return;
    }

    if (startData.error) {
      resultBox.innerHTML =
        '<p style="color:#e74c3c;">' +
        _t('tools.error', 'Error') +
        ': ' +
        startData.error +
        '</p>';
      if (btn) {
        btn.disabled = false;
        btn.textContent =
          '\uD83D\uDD04 ' + _t('tools.rescan_all', 'Rescan All');
      }
      return;
    }

    const pollInterval = setInterval(async () => {
      try {
        const statusRes = await fetch('/api/scan/status');
        const status: ScanStatus = await statusRes.json();
        const bar = document.getElementById('scanProgressBar') as HTMLElement | null;
        const text = document.getElementById('scanProgressText') as HTMLElement | null;

        if (bar && status.percent !== undefined)
          bar.style.width = status.percent + '%';

        if (text) {
          if (
            status.phase === 'scanning' ||
            status.phase === 'processing'
          ) {
            text.textContent =
              (status.current || 0).toLocaleString() +
              ' / ' +
              (status.total || 0).toLocaleString() +
              ' ' +
              _t('tools.files', 'files') +
              ' (' +
              status.percent +
              '%)';
            if (status.message) text.textContent += ` \u2014 ${status.message}`;
          } else if (status.phase === 'complete' || !status.running) {
            clearInterval(pollInterval);
            if (bar) bar.style.width = '100%';
            resultBox.innerHTML = `
              <p style="color:#2ecc71;">${'\u2713 ' + _t('tools.scan_all_complete', 'All folder scans complete')}</p>
              <div class="stat-row">
                <span>${_t('tools.processed_files', 'Processed files:')}</span>
                <span>${(status.current || 0).toLocaleString()}</span>
              </div>
            `;
            loadDbInfo();
            loadScanRoots();
            if (btn) {
              btn.disabled = false;
              btn.textContent =
                '\uD83D\uDD04 ' + _t('tools.rescan_all', 'Rescan All');
            }
          } else if (status.message) {
            text.textContent = status.message;
          }
        }
      } catch {
        // ignore transient polling errors
      }
    }, 800);

    setTimeout(() => {
      clearInterval(pollInterval);
      if (btn) {
        btn.disabled = false;
        btn.textContent =
          '\uD83D\uDD04 ' + _t('tools.rescan_all', 'Rescan All');
      }
    }, 1800000);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    resultBox.innerHTML =
      '<p style="color:#e74c3c;">' +
      _t('tools.error', 'Error') +
      ': ' +
      msg +
      '</p>';
    if (btn) {
      btn.disabled = false;
      btn.textContent =
        '\uD83D\uDD04 ' + _t('tools.rescan_all', 'Rescan All');
    }
  }
}

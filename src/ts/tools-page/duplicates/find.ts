/**
 * duplicates/find.ts -- Find duplicates and compute hashes.
 * Converted from tools-duplicates-find.js
 */

import { getAppApi } from '../../shared/browser-apis';
import { setDuplicateData } from '../../shared/runtime-state/duplicate-data-state';
import { apiFetch } from '../api';
import * as render from './render';
import type { DuplicateData } from './render';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function _updateHashStats(
  hashStats: { total_files?: number; with_hash?: number; with_phash?: number } | undefined,
): void {
  if (!hashStats) return;
  const el = document.getElementById('hashStats');
  if (!el) return;
  el.innerHTML =
    '📊 ' +
    _t('tools.hash_stats_total', 'Total files') +
    ': ' +
    (hashStats.total_files?.toLocaleString()) +
    ' &mdash; ' +
    _t('tools.file_hash_computed', 'File hashes computed') +
    ': <b>' +
    (hashStats.with_hash?.toLocaleString()) +
    '</b> / ' +
    _t('tools.phash_computed', 'Perceptual hashes computed') +
    ': <b>' +
    (hashStats.with_phash?.toLocaleString()) +
    '</b>';
}

function _renderResult(
  resultBox: HTMLElement,
  data: DuplicateData & { hash_stats?: { total_files?: number; with_hash?: number; with_phash?: number } },
  method: string,
): void {
  _updateHashStats(data.hash_stats);

  if (data.groups.length === 0) {
    resultBox.innerHTML = render.renderNoDuplicates(method, data.hash_stats);
    const delBtn = document.getElementById('deleteDuplicatesBtn') as HTMLButtonElement | null;
    const delHardBtn = document.getElementById('deleteDuplicatesHardBtn') as HTMLButtonElement | null;
    if (delBtn) delBtn.disabled = true;
    if (delHardBtn) delHardBtn.disabled = true;
    return;
  }

  render.renderGroups(resultBox, data, method);
  const delBtn = document.getElementById('deleteDuplicatesBtn') as HTMLButtonElement | null;
  const delHardBtn = document.getElementById('deleteDuplicatesHardBtn') as HTMLButtonElement | null;
  if (delBtn) delBtn.disabled = false;
  if (delHardBtn) delHardBtn.disabled = false;
  setDuplicateData(data);
}

async function _findDuplicatesSync(
  resultBox: HTMLElement,
  method: string,
  crossDirOnly: boolean,
): Promise<void> {
  const response = await apiFetch(
    `/api/tools/find-duplicates?cross_directory=${crossDirOnly}&method=${method}`,
  );
  const data: DuplicateData & {
    hash_stats?: { total_files?: number; with_hash?: number; with_phash?: number };
  } = await response.json();
  _renderResult(resultBox, data, method);
}

async function _findDuplicatesPhash(
  resultBox: HTMLElement,
  crossDirOnly: boolean,
): Promise<void> {
  const startResp = await apiFetch('/api/tools/find-duplicates/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ method: 'phash', cross_directory: crossDirOnly, threshold: 5 }),
  });
  const startData: { data: { started?: boolean; already_running?: boolean } } =
    await startResp.json();
  if (!startData.data?.started && !startData.data?.already_running) {
    throw new Error(_t('tools.job_start_failed', 'Failed to start duplicate search job'));
  }

  await new Promise<void>((resolve, reject) => {
    const poll = setInterval(async () => {
      try {
        const statusResp = await apiFetch('/api/tools/find-duplicates/status');
        const statusData: {
          data: {
            phase: string;
            running: boolean;
            elapsed_seconds?: number;
            result?: DuplicateData & {
              hash_stats?: { total_files?: number; with_hash?: number; with_phash?: number };
            };
            error?: string;
          };
        } = await statusResp.json();
        const status = statusData.data;

        if (status.phase === 'complete' && status.result) {
          clearInterval(poll);
          _renderResult(resultBox, status.result, 'phash');
          resolve();
        } else if (status.phase === 'error') {
          clearInterval(poll);
          resultBox.innerHTML = render.renderError(
            status.error || _t('tools.error', 'Error'),
          );
          resolve();
        } else {
          resultBox.innerHTML = render.renderProgress(status.elapsed_seconds ?? 0);
        }
      } catch (err) {
        clearInterval(poll);
        reject(err);
      }
    }, 2000);
  });
}

export async function findDuplicates(): Promise<void> {
  const resultBox = document.getElementById('duplicatesResult');
  if (!resultBox) return;
  resultBox.innerHTML = render.renderLoading();
  resultBox.classList.add('show');

  const crossDirOnly = (document.getElementById('crossDirectoryOnly') as HTMLInputElement).checked;
  const method = (document.getElementById('duplicateMethod') as HTMLSelectElement).value;

  const findBtn = document.querySelector(
    '[data-action="toolsPageApi.findDuplicates"]',
  ) as HTMLButtonElement | null;
  if (findBtn) findBtn.disabled = true;

  try {
    if (method === 'phash') {
      await _findDuplicatesPhash(resultBox, crossDirOnly);
    } else {
      await _findDuplicatesSync(resultBox, method, crossDirOnly);
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    resultBox.innerHTML = render.renderError(msg);
  } finally {
    if (findBtn) findBtn.disabled = false;
  }
}

export async function computeHashes(): Promise<void> {
  const method = (document.getElementById('duplicateMethod') as HTMLSelectElement).value;
  const hashType =
    method === 'phash' ? 'phash' : method === 'hash' ? 'hash' : 'both';

  const hashLabel =
    hashType === 'both'
      ? _t('tools.file_and_perceptual', 'File + Perceptual')
      : hashType === 'phash'
        ? _t('tools.perceptual', 'Perceptual')
        : _t('tools.file', 'File');
  if (
    !confirm(
      _t(
        'tools.compute_hash_confirm',
        'Compute {type} hashes.\nThis may take a while if there are many files.',
      ).replace('{type}', hashLabel),
    )
  )
    return;

  const resultBox = document.getElementById('duplicatesResult');
  if (!resultBox) return;
  resultBox.classList.add('show');
  resultBox.innerHTML = render.renderHashProgress();

  try {
    await apiFetch('/api/tools/compute-hashes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: hashType, limit: 10000 }),
    });

    const poll = setInterval(async () => {
      try {
        const res = await fetch('/api/scan/status');
        const status: {
          percent?: number;
          message?: string;
          current?: number;
          total?: number;
          running?: boolean;
        } = await res.json();

        const bar = document.getElementById('hashProgressBar') as HTMLElement | null;
        const text = document.getElementById('hashProgressText') as HTMLElement | null;

        if (bar) bar.style.width = (status.percent || 0) + '%';
        if (text)
          text.textContent =
            status.message ||
            `${status.current}/${status.total} (${status.percent}%)`;

        if (!status.running && (status.percent || 0) >= 100) {
          clearInterval(poll);
          resultBox.innerHTML = render.renderHashDone(status.message || '');
          findDuplicates();
        }
      } catch {
        // Ignore transient polling errors.
      }
    }, 1000);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    resultBox.innerHTML = render.renderError(msg);
  }
}

/**
 * wd-tagger/core.ts -- Main entry point.
 * Stats, batch execution, XMP viewer.
 * Re-exports all public symbols from config.ts and model.ts.
 */

import { getAppApi, getNavApi } from '../../shared/browser-apis';
import { apiFetch } from '../api';
import { renderWtStats, renderWtResult } from './render';
import { wtLoadConfigData } from './config';
import { wtLoadModelStatus } from './model';

// Re-export everything from config and model so external imports stay unchanged
export { wtSaveConfig, wtToggleEngineUI } from './config';
export { wtLoadModelStatus, wtDownloadModel, wtTestVlm, wtLoadVlmModels } from './model';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

// ── Config (orchestrator) ────────────────────────────

/**
 * Load config, toggle engine UI, refresh model status and stats.
 * This wraps wtLoadConfigData() (config.ts) and calls model/stats loaders
 * to avoid circular dependencies between config.ts and model.ts/core.ts.
 */
export async function wtLoadConfig(): Promise<void> {
  await wtLoadConfigData();
  wtLoadModelStatus();
  wtLoadStats();
  _loadScanRootsForWt();
}


// ── Stats ─────────────────────────────────────────────

export async function wtLoadStats(): Promise<void> {
  const el = document.getElementById('wtStats');
  if (!el) return;
  try {
    const res = await fetch('/api/wd-tagger/stats');
    const data = await res.json();
    el.innerHTML = renderWtStats(data);
  } catch {
    el.textContent = '';
  }
}


// ── Scan roots for batch ──────────────────────────────

async function _loadScanRootsForWt(): Promise<void> {
  const sel = document.getElementById('wtBatchRoot') as HTMLSelectElement | null;
  if (!sel) return;
  try {
    const res = await apiFetch('/api/scan-roots');
    const data: { roots: Array<{ path: string; enabled?: boolean }> } = await res.json();
    while (sel.options.length > 1) sel.remove(1);
    for (const root of data.roots) {
      if (root.enabled === false) continue;
      const opt = document.createElement('option');
      opt.value = root.path;
      opt.textContent = root.path;
      sel.appendChild(opt);
    }
  } catch { /* ignore */ }
}

// ── Batch ─────────────────────────────────────────────

let _pollTimer: ReturnType<typeof setInterval> | null = null;

export async function wtRunBatch(): Promise<void> {
  try {
    const scanRoot = (document.getElementById('wtBatchRoot') as HTMLSelectElement | null)?.value || '';
    const limitVal = (document.getElementById('wtBatchLimit') as HTMLSelectElement | null)?.value || '0';
    const limit = parseInt(limitVal, 10) || 0;

    const res = await apiFetch('/api/wd-tagger/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ limit, scan_root: scanRoot }),
    });
    const data = await res.json();
    if (data.ok === false) {
      getNavApi().showToast(data.error || _t('tools.wt_batch_failed', 'Batch start failed'), true);
      return;
    }
    _showProgress(true);
    _setCancelVisible(true);
    _startPolling();
  } catch (err) {
    getNavApi().showToast(_t('tools.wt_batch_failed', 'Batch start failed'), true);
  }
}

function _showProgress(visible: boolean): void {
  const el = document.getElementById('wtProgress');
  if (el) el.style.display = visible ? '' : 'none';
}

function _updateProgress(pct: number, label: string): void {
  const bar = document.getElementById('wtProgressBar');
  if (bar) bar.style.width = pct + '%';
  const pctEl = document.getElementById('wtProgressPct');
  if (pctEl) pctEl.textContent = pct + '%';
  const labelEl = document.getElementById('wtProgressLabel');
  if (labelEl) labelEl.textContent = label;
}

function _startPolling(): void {
  if (_pollTimer) clearInterval(_pollTimer);
  _pollTimer = setInterval(async () => {
    try {
      const res = await fetch('/api/jobs/status');
      const data = await res.json();
      const jobs = data.active || [];
      const wtJob = jobs.find((j: { job_id: string }) => j.job_id === 'wd_tagger');
      if (wtJob) {
        _updateProgress(wtJob.percent || 0, wtJob.message || _t('tools.wt_processing', 'Processing...'));
      } else {
        // Check recent
        const recent = data.recent || [];
        const done = recent.find((j: { job_id: string }) => j.job_id === 'wd_tagger');
        if (done) {
          _updateProgress(100, done.message || _t('tools.wt_complete', 'Complete'));
          _stopPolling();
          const resultEl = document.getElementById('wtResult');
          if (resultEl) {
            resultEl.style.display = '';
            resultEl.innerHTML = renderWtResult(done);
          }
          wtLoadStats();
        } else {
          _stopPolling();
        }
      }
    } catch {
      _stopPolling();
    }
  }, 2000);
}

function _stopPolling(): void {
  if (_pollTimer) {
    clearInterval(_pollTimer);
    _pollTimer = null;
  }
  _setCancelVisible(false);
}

function _setCancelVisible(visible: boolean): void {
  const btn = document.getElementById('wtCancelBtn');
  if (btn) btn.style.display = visible ? '' : 'none';
}

export async function wtCancelBatch(): Promise<void> {
  try {
    const res = await apiFetch('/api/wd-tagger/batch/cancel', { method: 'POST' });
    const data = await res.json();
    if (data.ok !== false) {
      _updateProgress(0, _t('tools.wt_cancelling', 'Cancelling...'));
    }
  } catch { /* ignore */ }
}


// ── XMP viewer ────────────────────────────────────────

export async function wtViewXmp(fileId: number): Promise<void> {
  try {
    const res = await fetch(`/api/wd-tagger/xmp/${fileId}`);
    const data = await res.json();
    const xmp = data.xmp || data.data?.xmp;
    if (!xmp) return;

    // Show in a simple modal
    const modal = document.createElement('div');
    modal.className = 'wt-xmp-modal-overlay';
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

    const content = document.createElement('div');
    content.className = 'wt-xmp-modal';

    let html = '<h3 style="margin:0 0 12px;font-size:15px;">' + _escapeHtml(_t('tools.wt_xmp_title', 'XMP Metadata')) + '</h3>';

    if (xmp.dc_subject && xmp.dc_subject.length > 0) {
      html += '<div style="margin-bottom:10px;"><strong>' + _escapeHtml(_t('tools.wt_xmp_dc_subject', 'dc:subject tags:')) + '</strong><div class="wt-tag-list">';
      for (const tag of xmp.dc_subject) {
        html += `<span class="wt-tag wt-tag-general">${_escapeHtml(tag)}</span>`;
      }
      html += '</div></div>';
    }

    if (xmp.wdtag && Object.keys(xmp.wdtag).length > 0) {
      html += '<div style="margin-bottom:10px;"><strong>' + _escapeHtml(_t('tools.wt_xmp_wdtag_info', 'wdtag info:')) + '</strong><ul style="margin:4px 0;padding-left:20px;font-size:12px;">';
      for (const [k, v] of Object.entries(xmp.wdtag)) {
        html += `<li>${_escapeHtml(k)}: ${_escapeHtml(String(v))}</li>`;
      }
      html += '</ul></div>';
    }

    if (xmp.raw_xml) {
      html += '<details style="margin-top:10px;"><summary style="cursor:pointer;font-size:12px;">' + _escapeHtml(_t('tools.wt_xmp_raw_xml', 'Raw XML')) + '</summary>';
      html += `<pre style="max-height:300px;overflow:auto;font-size:11px;background:rgba(0,0,0,0.2);padding:8px;border-radius:6px;white-space:pre-wrap;">${_escapeHtml(xmp.raw_xml)}</pre>`;
      html += '</details>';
    }

    html += '<button class="btn btn-secondary wt-xmp-close" type="button" style="margin-top:12px;">' + _escapeHtml(_t('tools.wt_close', 'Close')) + '</button>';
    content.innerHTML = html;
    content.querySelector('.wt-xmp-close')?.addEventListener('click', () => modal.remove());
    modal.appendChild(content);
    document.body.appendChild(modal);
  } catch {
    getNavApi().showToast(_t('tools.wt_xmp_load_failed', 'Failed to load XMP data'), true);
  }
}

function _escapeHtml(text: string): string {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

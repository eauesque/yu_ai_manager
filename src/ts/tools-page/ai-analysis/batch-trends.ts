/**
 * ai-analysis/batch-trends.ts -- Batch analysis, prompt trends, trend history,
 * and fallback local-only toggle.
 */

import { apiFetch } from '../api';
import * as render from './render';
import { _t, _esc, getConfigLoaded, getIsLocalEngine } from './helpers';
import { getSelectedBatchServerIds } from './servers';
import type { TrendHistoryItem } from './types';

/* ------------------------------------------------------------------ */
/* Interfaces (batch/trends specific)                                  */
/* ------------------------------------------------------------------ */

interface JobEntry {
  job_id: string;
  running: boolean;
  phase?: string;
  percent?: number;
  message?: string;
  current?: number;
  total?: number;
}

interface JobsStatus {
  has_active: boolean;
  active: JobEntry[];
  recent: JobEntry[];
}

interface TrendsResponse {
  error?: string;
  result?: {
    style_tendency?: string;
    strengths?: string;
    weaknesses?: string;
    frequent_tags?: string[];
    recommendations?: string[];
    unexplored?: string[];
    raw?: string;
  };
}

/* ------------------------------------------------------------------ */
/* Batch analysis                                                      */
/* ------------------------------------------------------------------ */

/**
 * Start a batch analysis job and poll for completion.
 * @param loadAiConfig - callback to reload config after batch completes
 */
export async function analyzeCurrentBatch(loadAiConfig: () => Promise<void>): Promise<void> {
  const resultBox = document.getElementById('aiAnalysisResult');
  if (!resultBox) return;
  render.renderBatchProgress(resultBox);

  const limitVal = (document.getElementById('aiBatchLimit') as HTMLSelectElement | null)?.value;
  const limit = limitVal !== undefined ? parseInt(limitVal, 10) || 0 : (getIsLocalEngine() ? 0 : 10);
  const scanRoot = (document.getElementById('aiBatchRoot') as HTMLSelectElement | null)?.value || '';

  try {
    const batchPayload: Record<string, unknown> = { limit, scan_root: scanRoot };
    const selectedServers = getSelectedBatchServerIds();
    if (selectedServers.length > 0) {
      batchPayload.server_ids = selectedServers;
    }
    await apiFetch('/api/analysis/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(batchPayload),
    });

    const poll = setInterval(async () => {
      try {
        const res = await apiFetch('/api/jobs/status');
        const data: JobsStatus = await res.json();
        const job = data.active.find(j => j.job_id === 'ai_analysis')
          || data.recent.find(j => j.job_id === 'ai_analysis');

        if (!job) return;

        const bar = document.getElementById('aiProgressBar') as HTMLElement | null;
        const text = document.getElementById('aiProgressText') as HTMLElement | null;
        if (bar) bar.style.width = (job.percent || 0) + '%';
        if (text)
          text.textContent =
            job.message || `${job.current}/${job.total}`;

        if (!job.running) {
          clearInterval(poll);
          const color = job.phase === 'error' ? '#e74c3c' : '#2ecc71';
          resultBox.innerHTML = `<p style="color:${color};">\u2713 ${_esc(job.message || '')}</p>`;
          loadAiConfig();
        }
      } catch {
        // ignore transient polling errors
      }
    }, 2000);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    resultBox.innerHTML =
      '<p style="color:#e74c3c;">' +
      _t('tools.error', 'Error') +
      ': ' +
      _esc(msg) +
      '</p>';
  }
}

export async function cancelAiBatch(): Promise<void> {
  try {
    await apiFetch('/api/analysis/batch/cancel', { method: 'POST' });
    const text = document.getElementById('aiProgressText');
    if (text) text.textContent = _t('tools.cancelling', 'Cancelling...');
  } catch { /* ignore */ }
}

/* ------------------------------------------------------------------ */
/* Prompt trends                                                       */
/* ------------------------------------------------------------------ */

export async function analyzePromptTrends(): Promise<void> {
  const resultBox = document.getElementById('aiAnalysisResult');
  if (!resultBox) return;
  render.renderTrendsLoading(resultBox);

  try {
    const res = await apiFetch('/api/analysis/trends', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data: TrendsResponse = await res.json();

    if (data.error) {
      resultBox.innerHTML =
        '<p style="color:#e74c3c;">' +
        _t('tools.error', 'Error') +
        ': ' +
        _esc(data.error) +
        '</p>';
      return;
    }

    if (data.result) {
      render.renderTrendsResult(resultBox, data.result);
      loadTrendHistory();
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    resultBox.innerHTML =
      '<p style="color:#e74c3c;">' +
      _t('tools.error', 'Error') +
      ': ' +
      _esc(msg) +
      '</p>';
  }
}

/* ------------------------------------------------------------------ */
/* Trend history                                                       */
/* ------------------------------------------------------------------ */

export async function loadTrendHistory(): Promise<void> {
  const container = document.getElementById('trendHistoryContainer');
  if (!container) return;
  try {
    const res = await apiFetch('/api/analysis/trends/history?limit=20');
    const data: { items: TrendHistoryItem[] } = await res.json();
    render.renderTrendHistory(container, data.items);
  } catch {
    // silently ignore
  }
}

export async function deleteTrendHistoryEntry(id: number): Promise<void> {
  try {
    await apiFetch(`/api/analysis/trends/history/${id}`, { method: 'DELETE' });
    loadTrendHistory();
  } catch {
    // silently ignore
  }
}

/* ------------------------------------------------------------------ */
/* Fallback local-only toggle                                          */
/* ------------------------------------------------------------------ */

export async function onFallbackLocalOnlyChange(): Promise<void> {
  if (!getConfigLoaded()) return;
  const el = document.getElementById('aiFallbackLocalOnly') as HTMLInputElement | null;
  if (!el) return;
  try {
    await apiFetch('/api/analysis/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fallback_local_only: el.checked }),
    });
  } catch {
    // silently ignore
  }
}

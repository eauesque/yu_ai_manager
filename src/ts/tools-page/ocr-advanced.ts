/**
 * Tools page — OCR Advanced Features (PR-4).
 * NPU status: GET /api/ocr/npu
 * Benchmark: GET /api/ocr/benchmark/cases, POST /api/ocr/benchmark
 * Profiles: GET /api/ocr/profiles, POST /api/ocr/profiles/fetch
 */

import { runOcrJob } from '../shared/ocr-job';

interface BenchmarkResult {
  engine: string;
  avg_similarity: number;
  avg_char_accuracy: number;
  avg_elapsed_ms: number;
}

interface BenchmarkSummary {
  task_scores: BenchmarkResult[];
}

interface OcrProfile {
  model: string;
  scores: Record<string, number>;
}

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function tStr(key: string, fallback: string): string {
  return typeof window.tr === 'function' ? window.tr(key) : fallback;
}

async function loadNpuStatus(): Promise<void> {
  const badge = document.getElementById('ocrNpuBadge');
  const suggestion = document.getElementById('ocrNpuSuggestion');
  if (!badge) return;
  try {
    const res = await fetch('/api/ocr/npu');
    if (!res.ok) {
      badge.textContent = res.status === 501
        ? tStr('tools.ocr_npu_unsupported', 'NPU status unavailable (not implemented)')
        : tStr('tools.ocr_npu_unknown', 'NPU status unknown');
      return;
    }
    const json = await res.json();
    const npu = json.npu ?? json;
    if (npu.available) {
      badge.textContent = `✓ ${npu.device ?? tStr('tools.ocr_npu_available', 'NPU available')}`;
      badge.style.background = '#d1fae5';
      badge.style.color = '#065f46';
    } else {
      badge.textContent = tStr('tools.ocr_npu_unavailable', 'NPU not available');
      badge.style.background = '#fef3c7';
      badge.style.color = '#92400e';
    }
    if (suggestion && npu.suggestion) suggestion.textContent = npu.suggestion;
  } catch { /* ignore */ }
}

function renderBenchmarkResults(container: HTMLElement, summary: BenchmarkSummary): void {
  if (!summary.task_scores || summary.task_scores.length === 0) {
    container.innerHTML = `<div class="tools-empty">${tStr('tools.ocr_benchmark_empty', 'No results yet')}</div>`;
    return;
  }
  const rows = summary.task_scores
    .map(
      (r) =>
        `<tr>
          <td>${escHtml(r.engine)}</td>
          <td>${(r.avg_similarity * 100).toFixed(1)}%</td>
          <td>${(r.avg_char_accuracy * 100).toFixed(1)}%</td>
          <td>${r.avg_elapsed_ms.toFixed(0)} ms</td>
        </tr>`,
    )
    .join('');
  container.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:0.85rem">
    <thead><tr><th>Engine</th><th>Similarity</th><th>Char Acc.</th><th>ms/image</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

async function loadProfiles(): Promise<void> {
  const container = document.getElementById('ocrProfilesList');
  if (!container) return;
  try {
    const res = await fetch('/api/ocr/profiles');
    if (!res.ok) {
      container.textContent = res.status === 501
        ? tStr('tools.ocr_npu_unsupported', 'NPU status unavailable (not implemented)')
        : tStr('tools.ocr_npu_unknown', 'NPU status unknown');
      return;
    }
    const json = await res.json();
    const profiles: OcrProfile[] = Array.isArray(json) ? json : (json.profiles ?? []);
    if (profiles.length === 0) { container.textContent = '—'; return; }
    container.innerHTML = profiles
      .map(
        (p) =>
          `<div style="margin-bottom:4px">
            <span style="font-family:monospace">${escHtml(p.model)}</span>
            <span style="color:#6b7280;margin-left:8px;font-size:0.8rem">
              ${Object.entries(p.scores).map(([k, v]) => `${escHtml(k)}: ${v.toFixed(2)}`).join(', ')}
            </span>
          </div>`,
      )
      .join('');
  } catch { /* ignore */ }
}

export function initOcrAdvanced(): void {
  void loadNpuStatus();
  void loadProfiles();

  document.getElementById('ocrBenchmarkRunBtn')?.addEventListener('click', () => {
    const taskEl = document.getElementById('ocrBenchmarkTask') as HTMLSelectElement | null;
    const results = document.getElementById('ocrBenchmarkResults');
    if (!results) return;
    const task = taskEl?.value ?? 'ocr';
    const btn = document.getElementById('ocrBenchmarkRunBtn');
    btn?.setAttribute('disabled', '');
    results.innerHTML = '<div class="tools-spinner">Running…</div>';

    // The job result carries aggregates only — per-case expected/actual text
    // would otherwise be readable through the unauthenticated /api/jobs/status.
    // The full report is fetched from the admin-gated report endpoint.
    void runOcrJob(
      fetch,
      '/api/ocr/benchmark',
      { task, server_id: '', benchmark_dir: '' },
      {
        onProgress: (job) => {
          const pct = job.percent != null ? ` ${Math.round(job.percent)}%` : '';
          results.innerHTML = `<div class="tools-spinner">Running…${pct}</div>`;
        },
      },
    )
      .then((job) => {
        const reportId = job.result?.report_id;
        if (typeof reportId !== 'string' || !reportId) {
          throw new Error('the benchmark produced no report');
        }
        return fetch(`/api/ocr/benchmark/report/${encodeURIComponent(reportId)}`);
      })
      .then((r) => r.json() as Promise<BenchmarkSummary>)
      .then((data) => renderBenchmarkResults(results, data))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Benchmark failed';
        results.innerHTML = `<div class="tools-empty">${msg}</div>`;
      })
      .finally(() => btn?.removeAttribute('disabled'));
  });

  document.getElementById('ocrProfilesFetchBtn')?.addEventListener('click', () => {
    const urlEl = document.getElementById('ocrProfilesFetchUrl') as HTMLInputElement | null;
    const statusEl = document.getElementById('ocrProfilesFetchStatus');
    const url = urlEl?.value?.trim();
    if (!url) return;
    const btn = document.getElementById('ocrProfilesFetchBtn');
    btn?.setAttribute('disabled', '');
    if (statusEl) statusEl.textContent = 'Fetching…';

    void fetch('/api/ocr/profiles/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        if (statusEl) { statusEl.textContent = 'Done'; statusEl.style.color = '#10b981'; }
        return loadProfiles();
      })
      .catch((err: Error) => {
        if (statusEl) { statusEl.textContent = err.message; statusEl.style.color = '#dc2626'; }
      })
      .finally(() => btn?.removeAttribute('disabled'));
  });
}

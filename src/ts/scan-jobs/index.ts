/**
 * Scan Jobs page — shows active jobs and persistent scan history.
 */

import { formatElapsedHms } from '../shared/date-format';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

interface ActiveJob {
  job_id: string;
  label: string;
  running: boolean;
  phase: string;
  current: number;
  total: number;
  percent: number;
  message: string;
  detail: string;
  error: string | null;
  elapsed_seconds: number;
}

interface HistoryEntry {
  status: string;
  timestamp: number;
  job_id: string;
  label: string;
  count: number;
  added: number;
  updated: number;
  deleted: number;
  errors: number;
  elapsed_seconds: number;
  error_message?: string;
}

let _autoRefreshTimer: ReturnType<typeof setInterval> | null = null;

function fmtTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleString('ja-JP', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
}

function fmtElapsed(s: number): string {
  if (!s) return '-';
  return formatElapsedHms(s);
}

function statusBadge(status: string): HTMLElement {
  const span = document.createElement('span');
  span.className = 'sj-job-status-badge';
  if (status === 'running' || status === 'started') {
    span.classList.add('sj-badge-running');
    span.textContent = '実行中';
  } else if (status === 'complete') {
    span.classList.add('sj-badge-complete');
    span.textContent = '完了';
  } else if (status === 'error') {
    span.classList.add('sj-badge-error');
    span.textContent = 'エラー';
  } else {
    span.classList.add('sj-badge-started');
    span.textContent = status;
  }
  return span;
}

function renderActiveJobs(jobs: ActiveJob[]): void {
  const el = document.getElementById('sjActiveJobs');
  if (!el) return;
  el.textContent = '';

  if (jobs.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'sj-empty';
    empty.setAttribute('data-i18n', 'scan_jobs.no_active_jobs');
    empty.textContent = '実行中のジョブはありません';
    el.appendChild(empty);
    return;
  }

  for (const job of jobs) {
    const card = document.createElement('div');
    card.className = 'sj-job-card';

    const header = document.createElement('div');
    header.className = 'sj-job-card-header';

    const labelEl = document.createElement('span');
    labelEl.className = 'sj-job-label';
    labelEl.textContent = job.label || job.job_id;
    header.appendChild(labelEl);

    const phaseEl = document.createElement('span');
    phaseEl.className = 'sj-job-phase';
    phaseEl.textContent = job.phase || '';
    header.appendChild(phaseEl);

    header.appendChild(statusBadge(job.running ? 'running' : 'complete'));
    card.appendChild(header);

    if (job.running && job.total > 0) {
      const barWrap = document.createElement('div');
      barWrap.className = 'sj-progress-bar-wrap';
      const bar = document.createElement('div');
      bar.className = 'sj-progress-bar';
      bar.style.width = `${Math.min(100, job.percent)}%`;
      barWrap.appendChild(bar);
      card.appendChild(barWrap);
    }

    const meta = document.createElement('div');
    meta.className = 'sj-job-meta';
    if (job.total > 0) {
      const prog = document.createElement('span');
      prog.textContent = `${job.current.toLocaleString()} / ${job.total.toLocaleString()} (${job.percent}%)`;
      meta.appendChild(prog);
    }
    if (job.elapsed_seconds > 0) {
      const elapsed = document.createElement('span');
      elapsed.textContent = `⏱ ${fmtElapsed(job.elapsed_seconds)}`;
      meta.appendChild(elapsed);
    }
    card.appendChild(meta);

    if (job.message) {
      const detail = document.createElement('div');
      detail.className = 'sj-job-detail';
      detail.textContent = job.message;
      card.appendChild(detail);
    }

    el.appendChild(card);
  }
}

function renderHistory(entries: HistoryEntry[]): void {
  const tbody = document.getElementById('sjHistoryBody');
  if (!tbody) return;
  tbody.textContent = '';

  if (entries.length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 8;
    td.className = 'sj-empty';
    td.setAttribute('data-i18n', 'scan_jobs.no_history');
    td.textContent = '履歴がありません';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const e of entries) {
    const tr = document.createElement('tr');

    const cells: [string, string][] = [
      [fmtTime(e.timestamp), ''],
      [e.label || e.job_id || '-', ''],
      ['', ''],  // badge placeholder
      [e.added > 0 ? `+${e.added.toLocaleString()}` : '-', 'num'],
      [e.updated > 0 ? e.updated.toLocaleString() : '-', 'num'],
      [e.deleted > 0 ? e.deleted.toLocaleString() : '-', 'num'],
      [e.errors > 0 ? String(e.errors) : '-', 'num'],
      [fmtElapsed(e.elapsed_seconds), 'num'],
    ];

    cells.forEach(([text, cls], i) => {
      const td = document.createElement('td');
      if (cls) td.className = cls;
      if (i === 2) {
        // status badge cell
        td.appendChild(statusBadge(e.status));
        if (e.status === 'error' && e.error_message) {
          td.title = e.error_message;
        }
      } else {
        td.textContent = text;
      }
      tr.appendChild(td);
    });

    tbody.appendChild(tr);
  }
}

async function refresh(): Promise<void> {
  try {
    const [jobsRes, histRes] = await Promise.all([
      fetch('/api/jobs/status'),
      fetch('/api/scan/history?limit=50'),
    ]);
    if (jobsRes.ok) {
      const data = await jobsRes.json();
      const active: ActiveJob[] = (data.active || []).filter((j: ActiveJob) => j.running);
      renderActiveJobs(active);
    }
    if (histRes.ok) {
      const data = await histRes.json();
      renderHistory(data.entries || []);
    }
  } catch {
    // ignore fetch errors
  }
}

async function clearHistory(): Promise<void> {
  if (!confirm('スキャン履歴をすべて削除しますか？')) return;
  try {
    await fetch('/api/scan/history/clear', { method: 'POST', headers: XHR_HEADERS });
    await refresh();
  } catch {
    // ignore
  }
}

function initAutoRefresh(): void {
  const cb = document.getElementById('sjAutoRefresh') as HTMLInputElement | null;
  if (!cb) return;

  const start = () => {
    if (_autoRefreshTimer) clearInterval(_autoRefreshTimer);
    _autoRefreshTimer = setInterval(refresh, 5000);
  };
  const stop = () => {
    if (_autoRefreshTimer) { clearInterval(_autoRefreshTimer); _autoRefreshTimer = null; }
  };

  cb.addEventListener('change', () => { cb.checked ? start() : stop(); });
  if (cb.checked) start();
}

document.addEventListener('DOMContentLoaded', () => {
  refresh();
  initAutoRefresh();

  document.getElementById('sjRefreshBtn')?.addEventListener('click', refresh);
  document.getElementById('sjClearHistoryBtn')?.addEventListener('click', clearHistory);
});

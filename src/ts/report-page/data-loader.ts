/**
 * Report page data loader — fetch API and orchestrate rendering.
 */
import { renderReport, renderEmpty } from './renderer';
import { createPagePerfTracker } from '../shared/page-perf';

interface MonthlyReportData {
  month: string;
  file_count: number;
  prev_month_count: number;
  /** null when there is no previous month baseline (first month or 0-file gap). */
  mom_change_pct: number | null;
  unique_tags: number;
  new_tags: string[];
  top_tags: Array<{
    tag: string; count: number; rank: number;
    prev_rank: number | null; rank_change: number | null;
  }>;
  sources: Record<string, number>;
  most_active_day: { date: string; count: number } | null;
  daily_counts: Array<{ date: string; count: number }>;
  trophies: Array<{ type: string; title: string; threshold?: number; tier?: string; category?: string; is_new?: boolean }>;
  available_months: string[];
}

let _currentMonth = '';
let _availableMonths: string[] = [];
const _perf = createPagePerfTracker('report');
_perf.markOnce('module_ready');

function _el<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

async function _loadReport(month: string): Promise<void> {
  const loading = _el('reportLoading');
  const empty = _el('reportEmpty');
  const summary = _el('reportSummary');
  const body = _el('reportBody');
  const trophies = _el('reportTrophies');

  if (loading) loading.style.display = 'block';
  if (empty) empty.style.display = 'none';
  if (summary) summary.style.display = 'none';
  if (body) body.style.display = 'none';
  if (trophies) trophies.style.display = 'none';

  const url = month ? `/api/stats/monthly-report?month=${encodeURIComponent(month)}` : '/api/stats/monthly-report';
  try {
    const resp = await fetch(url);
    const json = await resp.json();
    if (loading) loading.style.display = 'none';

    const data: MonthlyReportData = json.data || json;
    if (!data.file_count && !data.available_months?.length) {
      renderEmpty();
      _perf.markOnce('empty_ready');
      return;
    }

    _currentMonth = data.month;
    _availableMonths = data.available_months || [];
    _populateMonthSelector(data.available_months, data.month);
    renderReport({
      ...data,
      trophies: (data.trophies || []).map((t) => ({
        ...t,
        tier: t.tier || 'gold',
        category: t.category || t.type,
        is_new: t.is_new || false,
      })),
    });
    _perf.markOnce('summary_ready');
  } catch (e) {
    if (loading) loading.style.display = 'none';
    renderEmpty();
    console.error('Failed to load report:', e);
  }
}

function _populateMonthSelector(months: string[], current: string): void {
  const select = _el<HTMLSelectElement>('reportMonthSelect');
  if (!select) return;

  select.innerHTML = '';
  months.forEach((m) => {
    const opt = document.createElement('option');
    opt.value = m;
    opt.textContent = m;
    if (m === current) opt.selected = true;
    select.appendChild(opt);
  });
}

function _navigateMonth(delta: number): void {
  const idx = _availableMonths.indexOf(_currentMonth);
  // Months are desc sorted, so prev month = idx+1, next = idx-1
  const newIdx = idx - delta;
  if (newIdx >= 0 && newIdx < _availableMonths.length) {
    _loadReport(_availableMonths[newIdx]);
  }
}

export function initReport(): void {
  document.addEventListener('DOMContentLoaded', () => {
    _perf.markOnce('dom_ready');
    const select = _el<HTMLSelectElement>('reportMonthSelect');
    if (select) {
      select.addEventListener('change', () => {
        _loadReport(select.value);
      });
    }

    const prev = _el('reportPrevMonth');
    const next = _el('reportNextMonth');
    if (prev) prev.addEventListener('click', () => _navigateMonth(-1));
    if (next) next.addEventListener('click', () => _navigateMonth(1));

    // Load current month
    _loadReport('');
  });
}

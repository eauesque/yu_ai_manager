/**
 * Report page renderer — DOM rendering, count-up, sparkline.
 */
import { animateCountUp, staggerReveal } from './animations';

interface ReportData {
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
  trophies: Array<{
    type: string; title: string; tier: string;
    category: string; is_new: boolean;
  }>;
}

function _el<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

function _clear(el: HTMLElement): void {
  el.replaceChildren();
}

function _appendTextEl(parent: HTMLElement, tag: string, className: string, text: string): HTMLElement {
  const el = document.createElement(tag);
  el.className = className;
  el.textContent = text;
  parent.appendChild(el);
  return el;
}

function _deferRender(task: () => void): void {
  const win = window as Window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => void };
  if (typeof win.requestIdleCallback === 'function') {
    win.requestIdleCallback(task, { timeout: 1200 });
    return;
  }
  setTimeout(task, 60);
}

export function renderEmpty(): void {
  const empty = _el('reportEmpty');
  if (empty) empty.style.display = 'block';
}

export function renderReport(data: ReportData): void {
  const summary = _el('reportSummary');
  const body = _el('reportBody');
  if (summary) summary.style.display = 'grid';
  if (body) body.style.display = 'grid';

  // Summary cards with count-up
  animateCountUp('rptFileCount', data.file_count);
  animateCountUp('rptUniqueTags', data.unique_tags);

  const newTagsCount = _el('rptNewTags');
  if (newTagsCount) newTagsCount.textContent = String(data.new_tags.length);

  // MoM change — null means no previous month baseline (first month / 0-file gap)
  const mom = _el('rptMomChange');
  if (mom) {
    const pct = data.mom_change_pct;
    if (pct != null && pct > 0) {
      mom.className = 'report-card-mom positive';
      mom.textContent = `+${pct}% vs prev`;
    } else if (pct != null && pct < 0) {
      mom.className = 'report-card-mom negative';
      mom.textContent = `${pct}% vs prev`;
    } else {
      mom.className = 'report-card-mom neutral';
      mom.textContent = '-- vs prev';
    }
  }

  // Most active day
  const activeDay = _el('rptActiveDay');
  const activeDayCount = _el('rptActiveDayCount');
  if (data.most_active_day) {
    if (activeDay) activeDay.textContent = data.most_active_day.date;
    if (activeDayCount) activeDayCount.textContent = `${data.most_active_day.count} files`;
  } else {
    if (activeDay) activeDay.textContent = '-';
    if (activeDayCount) activeDayCount.textContent = '';
  }

  _deferRender(() => {
    _renderTrophies(data.trophies);
    _renderRankings(data.top_tags);
    _renderSources(data.sources);
    _renderNewTags(data.new_tags);
    _renderSparkline(data.daily_counts);
  });
}

const _TIER_ICONS: Record<string, string> = {
  bronze: '\uD83E\uDD49',   // 🥉
  silver: '\uD83E\uDD48',   // 🥈
  gold: '\uD83C\uDFC6',     // 🏆
  platinum: '\uD83D\uDC8E', // 💎
};

function _renderTrophies(trophies: ReportData['trophies']): void {
  const container = _el('reportTrophies');
  if (!container) return;

  if (!trophies.length) {
    container.style.display = 'none';
    return;
  }

  container.style.display = 'flex';
  _clear(container);
  trophies.forEach((t, i) => {
    const icon = _TIER_ICONS[t.tier] || _TIER_ICONS.gold;
    const trophy = document.createElement('div');
    trophy.className = `report-trophy report-trophy--${t.tier}${t.is_new ? ' report-trophy--new' : ''}`;
    if (t.is_new) trophy.style.animationDelay = `${i * 0.15}s`;
    _appendTextEl(trophy, 'span', 'report-trophy-icon', icon);
    _appendTextEl(trophy, 'span', 'report-trophy-text', t.title);
    container.appendChild(trophy);
  });
}

function _renderRankings(tags: ReportData['top_tags']): void {
  const list = _el('rptRankingList');
  if (!list) return;

  _clear(list);
  tags.forEach((t, i) => {
    const item = document.createElement('div');
    item.className = 'report-rank-item';
    item.style.animationDelay = `${i * 0.06}s`;

    _appendTextEl(item, 'span', 'report-rank-num', String(t.rank));
    _appendTextEl(item, 'span', 'report-rank-tag', t.tag);
    _appendTextEl(item, 'span', 'report-rank-count', t.count.toLocaleString());

    const changeEl = document.createElement('span');
    changeEl.className = 'report-rank-change';
    if (t.rank_change === null || t.prev_rank === null) {
      changeEl.classList.add('new');
      changeEl.textContent = 'NEW';
    } else if (t.rank_change > 0) {
      changeEl.classList.add('up');
      changeEl.textContent = `+${t.rank_change}`;
    } else if (t.rank_change < 0) {
      changeEl.classList.add('down');
      changeEl.textContent = String(t.rank_change);
    } else {
      changeEl.textContent = '-';
    }
    item.appendChild(changeEl);
    list.appendChild(item);
  });

  staggerReveal(list);
}

function _renderSources(sources: Record<string, number>): void {
  const container = _el('rptSources');
  if (!container) return;

  const entries = Object.entries(sources).sort((a, b) => b[1] - a[1]);
  const maxVal = entries.length ? entries[0][1] : 1;

  _clear(container);
  entries.forEach(([name, count]) => {
    const pct = Math.round((count / maxVal) * 100);
    const row = document.createElement('div');
    row.className = 'report-source-row';
    _appendTextEl(row, 'span', 'report-source-name', name);
    const bar = document.createElement('div');
    bar.className = 'report-source-bar';
    const fill = document.createElement('div');
    fill.className = 'report-source-fill';
    fill.style.width = `${pct}%`;
    bar.appendChild(fill);
    row.appendChild(bar);
    _appendTextEl(row, 'span', 'report-source-count', String(count));
    container.appendChild(row);
  });
}

function _renderNewTags(tags: string[]): void {
  const container = _el('rptNewTagsList');
  if (!container) return;

  if (!tags.length) {
    _clear(container);
    const empty = document.createElement('span');
    empty.style.color = 'var(--muted)';
    empty.style.fontSize = '12px';
    empty.textContent = 'None';
    container.appendChild(empty);
    return;
  }

  _clear(container);
  tags.forEach((t) => {
    _appendTextEl(container, 'span', 'report-new-tag', t);
  });
}

function _renderSparkline(daily: Array<{ date: string; count: number }>): void {
  const container = _el('rptSparkline');
  if (!container) return;

  if (!daily.length) {
    _clear(container);
    return;
  }

  const maxVal = Math.max(...daily.map((d) => d.count), 1);
  _clear(container);
  daily.forEach((d) => {
    const h = Math.max(4, Math.round((d.count / maxVal) * 56));
    const bar = document.createElement('div');
    bar.className = 'report-spark-bar';
    bar.style.height = `${h}px`;
    bar.title = `${d.date}: ${d.count}`;
    container.appendChild(bar);
  });
}

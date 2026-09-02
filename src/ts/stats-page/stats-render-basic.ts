import type { BasicStatsResponse, MonthlyReport } from './data-loader';

type PerfTracker = { markOnce: (name: string) => void };

export function renderBasicStats(
  basicStats: BasicStatsResponse,
  trFn: ((key: string) => string) | null,
  perf: PerfTracker,
): void {
  const fileCount = Number(basicStats.file_count ?? 0);
  const tagCount = Number(basicStats.tag_count ?? 0);
  const totalFiles = Number(basicStats.total_files ?? fileCount);
  const excludedFiles = Number(basicStats.excluded_files ?? 0);

  const totalFilesEl = document.getElementById('totalFiles');
  if (totalFilesEl) totalFilesEl.textContent = fileCount.toLocaleString();

  const noteEl = document.getElementById('totalFilesNote');
  if (noteEl && excludedFiles > 0) {
    const noteKey = trFn ? trFn('stats.ai_images_note') : '';
    noteEl.textContent = (noteKey || 'AI images only ({total} total)')
      .replace('{total}', totalFiles.toLocaleString());
  }

  const totalTagsEl = document.getElementById('totalTags');
  if (totalTagsEl) totalTagsEl.textContent = tagCount.toLocaleString();

  const avgTags = fileCount > 0
    ? (tagCount / fileCount).toFixed(1)
    : '0';
  const avgTagsEl = document.getElementById('avgTags');
  if (avgTagsEl) avgTagsEl.textContent = avgTags;

  const staleNotice = document.getElementById('statsStaleNotice');
  if (staleNotice) staleNotice.style.display = basicStats._stale ? 'block' : 'none';

  const unknownNotice = document.getElementById('statsUnknownNotice');
  if (unknownNotice && basicStats.sources && totalFiles > 0) {
    const unknownCount = basicStats.sources.unknown || 0;
    const unknownPct = Math.round((unknownCount / totalFiles) * 100);
    if (unknownCount > 0 && unknownPct >= 20) {
      const msgEl = unknownNotice.querySelector<HTMLElement>('#statsUnknownNoticeText');
      if (msgEl) {
        const key = trFn ? trFn('stats.unknown_files_notice') : '';
        msgEl.textContent = (key || 'メタデータ未抽出ファイル: {count}件 (全体の{pct}%)。スキャンを実行して抽出することを推奨します。')
          .replace('{count}', unknownCount.toLocaleString())
          .replace('{pct}', String(unknownPct));
      }
      unknownNotice.style.display = 'block';
    } else {
      unknownNotice.style.display = 'none';
    }
  }

  perf.markOnce('summary_ready');
}

export function showCharts(): void {
  const loadingEl = document.getElementById('loading');
  if (loadingEl) loadingEl.style.display = 'none';
  const chartsEl = document.getElementById('statsCharts');
  if (chartsEl) chartsEl.style.display = 'block';
}

export function renderRatingsChart(
  data: { total_rated: number; distribution: Record<string, number> },
  trFn: ((key: string) => string) | null,
): void {
  const section = document.getElementById('ratingsSection');
  if (!section) return;
  const dist = data.distribution || {};
  const total = data.total_rated || 0;
  if (total === 0) return;
  section.style.display = 'block';

  const chartEl = document.getElementById('ratingsChart');
  const totalEl = document.getElementById('ratingsTotal');
  if (!chartEl) return;
  chartEl.textContent = '';

  const maxCount = Math.max(...[1, 2, 3, 4, 5].map((star) => Number(dist[String(star)] || 0)), 1);
  [1, 2, 3, 4, 5].forEach((star) => {
    makeRatingBar(chartEl, star, Number(dist[String(star)] || 0), maxCount);
  });
  if (totalEl) {
    const msg = (trFn ? trFn('stats.ratings_total') : '') || '{count} rated';
    totalEl.textContent = msg.replace('{count}', String(total));
  }
}

function makeRatingBar(container: HTMLElement, star: number, count: number, maxCount: number): void {
  const col = document.createElement('div');
  col.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:4px;flex:1;';
  const countEl = document.createElement('div');
  countEl.style.cssText = 'font-size:11px;color:var(--muted,#888);';
  countEl.textContent = count.toLocaleString();
  const bar = document.createElement('div');
  const pct = Math.round((count / maxCount) * 100);
  bar.style.cssText = `width:100%;background:rgba(245,158,11,0.8);border-radius:4px 4px 0 0;min-height:4px;height:${pct}%;max-height:60px;`;
  const label = document.createElement('div');
  label.style.cssText = 'font-size:13px;color:var(--rating-star-fg,#92400e);';
  label.textContent = '★'.repeat(star);
  col.appendChild(countEl);
  col.appendChild(bar);
  col.appendChild(label);
  container.appendChild(col);
}

export function renderMonthlyReport(
  data: MonthlyReport,
  trFn: ((key: string) => string) | null,
): void {
  const content = document.getElementById('monthlySummaryContent');
  const dailyEl = document.getElementById('monthlyDailyChart');
  if (!content) return;
  content.textContent = '';

  const changeSign = data.mom_change_pct >= 0 ? '+' : '';
  const changeColor = data.mom_change_pct >= 0 ? 'var(--positive-change-fg,#047857)' : 'var(--negative-change-fg,#b91c1c)';
  const cards: Array<{ label: string; value: string; color?: string }> = [
    { label: (trFn ? trFn('stats.monthly_files') : '') || 'Files', value: data.file_count.toLocaleString() },
    { label: (trFn ? trFn('stats.monthly_change') : '') || 'vs Prev', value: `${changeSign}${data.mom_change_pct.toFixed(1)}%`, color: changeColor },
    { label: (trFn ? trFn('stats.monthly_unique_tags') : '') || 'Unique Tags', value: data.unique_tags.toLocaleString() },
    { label: (trFn ? trFn('stats.monthly_new_tags') : '') || 'New Tags', value: String(data.new_tags) },
    { label: (trFn ? trFn('stats.monthly_peak_day') : '') || 'Most Active', value: data.most_active_day || '-' },
  ];

  cards.forEach((cardDef) => {
    const card = document.createElement('div');
    card.style.cssText = 'background:rgba(128,128,128,0.08);border-radius:8px;padding:10px 12px;';
    const lbl = document.createElement('div');
    lbl.style.cssText = 'font-size:11px;color:var(--muted,#888);margin-bottom:4px;';
    lbl.textContent = cardDef.label;
    const val = document.createElement('div');
    val.style.cssText = `font-size:18px;font-weight:700;${cardDef.color ? `color:${cardDef.color};` : ''}`;
    val.textContent = cardDef.value;
    card.appendChild(lbl);
    card.appendChild(val);
    content.appendChild(card);
  });

  if (dailyEl && data.daily_counts) {
    dailyEl.textContent = '';
    const days = Object.entries(data.daily_counts).sort(([a], [b]) => a.localeCompare(b));
    const maxVal = Math.max(...days.map(([, value]) => Number(value)), 1);
    days.forEach(([day, cnt]) => {
      const pct = Math.round((Number(cnt) / maxVal) * 100);
      const dayNum = day.split('-')[2] || '';
      const col = document.createElement('div');
      col.title = `${day}: ${cnt}`;
      col.style.cssText = 'display:flex;flex-direction:column;align-items:center;flex:1;gap:2px;';
      const bar = document.createElement('div');
      bar.style.cssText = `width:100%;background:rgba(102,126,234,0.7);border-radius:2px 2px 0 0;min-height:2px;height:${pct}%;`;
      const lbl = document.createElement('div');
      lbl.style.cssText = 'font-size:9px;color:var(--muted,#888);';
      lbl.textContent = dayNum;
      col.appendChild(bar);
      col.appendChild(lbl);
      dailyEl.appendChild(col);
    });
  }
}

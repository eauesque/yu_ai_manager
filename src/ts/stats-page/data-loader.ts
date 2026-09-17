/** Stats data loader. */

import {
  displayTimePeriods,
  displayPersonality,
  displayTurningPoints,
  displayTimelineChart,
  displayTopTags,
  displayModelChart,
  displayResolutionChart,
} from './charts/index';
import { createPagePerfTracker } from '../shared/page-perf';
import {
  fetchBasicStats,
  fetchMonthlyReport,
  fetchRatingsStats,
  fetchStatsDetails,
  fetchStreak,
} from './stats-fetch';
import { initCsvButtons } from './stats-csv';
import { renderBasicStats, renderMonthlyReport, renderRatingsChart, showCharts } from './stats-render-basic';
import { observeSectionOnce, runSectionOnce, type RenderSectionState } from './stats-render-details';
import { filterSafeModeTags, initSafeModeToggle } from './stats-safe-mode';

import type { TimePeriod, Personality, TurningPoint } from './charts/panels';
import type { TimelineRow, TagRow, ModelRow, ResolutionRow } from './charts/core';

export interface StatsAllResponse {
  basic: {
    file_count: number;
    total_files: number;
    excluded_files: number;
    tag_count: number;
    top_tags: TagRow[];
  };
  hourly: {
    periods: Record<string, TimePeriod>;
    personality: Personality;
  };
  timeline: { data?: TimelineRow[] } & TimelineRow[];
  models: {
    top_models: ModelRow[];
  };
  resolutions: {
    top_resolutions: ResolutionRow[];
    turning_points: TurningPoint[];
  };
}

export interface BasicStatsResponse {
  file_count: number;
  total_files: number;
  excluded_files: number;
  tag_count: number;
  top_tags: TagRow[];
  sources?: Record<string, number>;
  _stale?: boolean;
}

export interface HourlyStatsResponse {
  periods: Record<string, TimePeriod>;
  personality: Personality;
}

export interface ModelsStatsResponse {
  top_models: ModelRow[];
}

export interface ResolutionStatsResponse {
  top_resolutions: ResolutionRow[];
  turning_points: TurningPoint[];
}

export type MonthlyReport = {
  month: string;
  file_count: number;
  prev_month_count: number;
  mom_change_pct: number;
  unique_tags: number;
  new_tags: number;
  most_active_day: string;
  daily_counts: Record<string, number>;
  available_months: string[];
};

type RatingsStats = {
  total_rated: number;
  distribution: Record<string, number>;
};

let csvData: Record<string, Array<Record<string, unknown>>> = {};
let loadStarted = false;
let allTopTags: TagRow[] = [];
let detailsLoaded = false;
let detailsScheduled = false;
const renderedSections: RenderSectionState = new Set<string>();
const perf = createPagePerfTracker('stats');
perf.markOnce('module_ready');

function scheduleDetailsLoad(): void {
  if (detailsLoaded || detailsScheduled) return;
  detailsScheduled = true;
  const run = () => { void loadStatsDetails(); };
  const win = window as Window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => void };
  if (typeof win.requestIdleCallback === 'function') {
    win.requestIdleCallback(run, { timeout: 1500 });
  } else {
    setTimeout(run, 120);
  }
}

async function loadRatingsChart(trFn: ((key: string) => string) | null): Promise<void> {
  const data = await fetchRatingsStats();
  if (!data) return;
  renderRatingsChart(data as RatingsStats, trFn);
}

async function loadMonthlySummary(trFn: ((key: string) => string) | null): Promise<void> {
  const section = document.getElementById('monthlySection');
  const select = document.getElementById('monthlyMonthSelect') as HTMLSelectElement | null;
  if (!section) return;

  const today = new Date();
  const currentMonth = today.toISOString().slice(0, 7);
  const data = await fetchMonthlyReport(currentMonth);
  if (!data || !data.month) return;
  section.style.display = 'block';

  if (select && data.available_months?.length) {
    select.textContent = '';
    data.available_months.forEach((month) => {
      const opt = document.createElement('option');
      opt.value = month;
      opt.textContent = month;
      if (month === currentMonth) opt.selected = true;
      select.appendChild(opt);
    });
    if (select.dataset.actionBound !== '1') {
      select.dataset.actionBound = '1';
      select.addEventListener('change', () => {
        void fetchMonthlyReport(select.value).then((report) => {
          if (report) renderMonthlyReport(report, trFn);
        });
      });
    }
  }

  renderMonthlyReport(data, trFn);
}

async function loadStreak(trFn: ((key: string) => string) | null): Promise<void> {
  const streak = await fetchStreak();
  const el = document.getElementById('statsStreak');
  if (el) el.textContent = streak.toLocaleString();
  const labelEl = document.getElementById('statsStreakLabel');
  if (labelEl && streak === 0) {
    const msg = (trFn ? trFn('stats.streak_days_none') : '') || '連続記録なし';
    labelEl.textContent = msg;
  }
}

async function loadStatsDetails(): Promise<void> {
  if (detailsLoaded) return;
  showCharts();
  const trFn = typeof window.tr === 'function' ? window.tr : null;
  try {
    const { basicStats, hourly, timelineData, models, resolutions } = await fetchStatsDetails();

    if (hourly) {
      runSectionOnce(renderedSections, 'hourly', () => {
        displayTimePeriods(hourly.periods);
        displayPersonality(hourly.personality);
      });
    }

    observeSectionOnce(
      document.getElementById('timelineChart')?.closest('.chart-container') ?? document.getElementById('timelineChart'),
      renderedSections,
      'timeline',
      () => {
        displayTimelineChart(timelineData);
      },
    );

    allTopTags = basicStats.top_tags;
    observeSectionOnce(
      document.getElementById('topTagsChart')?.closest('.chart-container') ?? document.getElementById('topTagsChart'),
      renderedSections,
      'topTags',
      () => {
        displayTopTags(filterSafeModeTags(allTopTags));
      },
    );
    initSafeModeToggle(
      () => allTopTags,
      (filtered) => {
        displayTopTags(filtered);
        csvData.topTags = filtered.map((tag) => ({ tag: tag.tag, namespace: tag.namespace || '', count: tag.count }));
      },
    );

    {
      const modelSection = document.getElementById('modelSection');
      if (modelSection) modelSection.style.display = 'block';
      if (models.top_models && models.top_models.length > 0) {
        observeSectionOnce(modelSection, renderedSections, 'models', () => {
          displayModelChart(models.top_models);
        });
      } else if (modelSection && !modelSection.querySelector('[data-empty-state="models"]')) {
        const msg = (trFn ? trFn('stats.no_model_data') : '') || 'No model data available';
        const p = document.createElement('p');
        p.dataset.emptyState = 'models';
        p.style.cssText = 'text-align:center;color:var(--text-muted,#888);padding:24px 0;';
        p.textContent = msg;
        modelSection.appendChild(p);
      }
    }

    {
      const resSection = document.getElementById('resolutionSection');
      if (resSection) resSection.style.display = 'block';
      if (resolutions.top_resolutions && resolutions.top_resolutions.length > 0) {
        observeSectionOnce(resSection, renderedSections, 'resolutions', () => {
          displayTurningPoints(resolutions.turning_points);
          displayResolutionChart(resolutions.top_resolutions);
        });
      } else if (resSection && !resSection.querySelector('[data-empty-state="resolutions"]')) {
        const chartEl = resSection.querySelector('canvas, .chart-container, [id*="resolution"]');
        const target = chartEl?.parentElement || resSection;
        const msg = (trFn ? trFn('stats.no_resolution_data') : '') || 'No resolution data available';
        const p = document.createElement('p');
        p.dataset.emptyState = 'resolutions';
        p.style.cssText = 'text-align:center;color:var(--text-muted,#888);padding:24px 0;';
        p.textContent = msg;
        target.appendChild(p);
      }
    }

    csvData.timeline = timelineData.map((row) => ({ period: row.period, count: row.count }));
    csvData.topTags = filterSafeModeTags(allTopTags).map((tag) => ({
      tag: tag.tag,
      namespace: tag.namespace || '',
      count: tag.count,
    }));
    if (models.top_models?.length) {
      csvData.models = models.top_models.map((model) => ({ model: model.model, count: model.count }));
    }
    if (resolutions.top_resolutions?.length) {
      csvData.resolutions = resolutions.top_resolutions.map((row) => ({ resolution: row.resolution, count: row.count }));
    }
    initCsvButtons(csvData);
    detailsLoaded = true;
    perf.markOnce('details_ready');

    observeSectionOnce(document.getElementById('ratingsSection'), renderedSections, 'ratings', () => {
      void loadRatingsChart(trFn);
    });
    observeSectionOnce(document.getElementById('monthlySection'), renderedSections, 'monthly', () => {
      void loadMonthlySummary(trFn);
    });
  } catch (error) {
    console.error('Failed to load stats details:', error);
    const loadingEl = document.getElementById('loading');
    if (loadingEl) {
      const msg = (trFn ? trFn('stats.load_failed') : '') || 'Failed to load statistics';
      loadingEl.innerHTML = '<p style="color: red;">' + msg + '</p>';
      loadingEl.style.display = 'block';
    }
  }
}

export async function loadStats(): Promise<void> {
  if (loadStarted) {
    scheduleDetailsLoad();
    return;
  }
  loadStarted = true;
  const trFn = typeof window.tr === 'function' ? window.tr : null;

  const basicPromise = fetchBasicStats()
    .then((basicStats) => {
      try {
        renderBasicStats(basicStats, trFn, perf);
      } catch (renderErr) {
        console.error('Failed to render basic stats:', renderErr, basicStats);
      }
    })
    .catch((err) => {
      console.error('Failed to fetch basic stats:', err);
    });

  const streakPromise = loadStreak(trFn).catch((err) => {
    console.error('Failed to load streak:', err);
  });

  scheduleDetailsLoad();

  await Promise.all([basicPromise, streakPromise]);
}

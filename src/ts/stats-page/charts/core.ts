/**
 * Stats chart core renderers — timeline, top tags, model, resolution charts.
 * Converted from static/js/stats/charts/render/core.js
 */

import { CHART_COLORS, buildChart, mapLabels } from './core-utils';

/** A single timeline data point. */
export interface TimelineRow {
  period: string;
  count: number;
}

/** A tag with usage count. */
export interface TagRow {
  namespace?: string;
  tag: string;
  count: number;
}

/** A model with usage count. */
export interface ModelRow {
  model: string;
  count: number;
}

/** A resolution with usage count. */
export interface ResolutionRow {
  resolution: string;
  count: number;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const charts: Record<string, any> = {};

/** Destroy an existing Chart.js instance before replacing it. */
function _destroyChart(key: string): void {
  if (charts[key] && typeof charts[key].destroy === 'function') {
    charts[key].destroy();
    charts[key] = null;
  }
}

export function displayTimelineChart(data: TimelineRow[]): void {
  _destroyChart('timeline');
  const trFn = typeof window.tr === 'function' ? window.tr : null;
  const label = (trFn ? trFn('stats.chart.generation_count') : '') || 'Generation count';

  // When only 1 data point, pad with empty prev/next months so the chart is visible
  let chartData = data;
  if (data.length === 1) {
    const ym = data[0].period;
    const [y, m] = ym.split('-').map(Number);
    const prev = new Date(y, m - 2, 1);
    const next = new Date(y, m, 1);
    const fmt = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    chartData = [
      { period: fmt(prev), count: 0 },
      data[0],
      { period: fmt(next), count: 0 },
    ];
  }

  charts.timeline = buildChart('timelineChart', 'line', {
    labels: mapLabels(chartData, 'period'),
    datasets: [
      {
        label,
        data: chartData.map((d) => d.count),
        borderColor: '#4a90e2',
        backgroundColor: 'rgba(74, 144, 226, 0.1)',
        fill: true,
        tension: 0.4,
        pointRadius: data.length === 1 ? 6 : 3,
      },
    ],
  }, {
    plugins: { legend: { display: false } },
    scales: { y: { beginAtZero: true } },
  });
}

export function displayTopTags(tags: TagRow[]): void {
  const trFn = typeof window.tr === 'function' ? window.tr : null;
  const label = (trFn ? trFn('stats.chart.usage_count') : '') || 'Usage count';

  // Destroy previous instance to avoid stacking Chart.js canvases
  _destroyChart('topTags');

  charts.topTags = buildChart('topTagsChart', 'bar', {
    labels: tags.map((t) => (t.namespace ? `${t.namespace}:${t.tag}` : t.tag)),
    datasets: [
      {
        label,
        data: tags.map((t) => t.count),
        backgroundColor: '#4a90e2',
      },
    ],
  }, {
    indexAxis: 'y',
    plugins: { legend: { display: false } },
  });
}

export function displayModelChart(models: ModelRow[]): void {
  _destroyChart('models');
  charts.models = buildChart('modelChart', 'doughnut', {
    labels: mapLabels(models, 'model'),
    datasets: [
      {
        data: models.map((m) => m.count),
        backgroundColor: CHART_COLORS,
      },
    ],
  }, {
    aspectRatio: 2,
    plugins: { legend: { position: 'right' as const } },
  });
}

export function displayResolutionChart(resolutions: ResolutionRow[]): void {
  _destroyChart('resolutions');
  const trFn = typeof window.tr === 'function' ? window.tr : null;
  const label = (trFn ? trFn('stats.chart.usage_count') : '') || 'Usage count';

  // Wider aspect ratio for fewer items to avoid massive empty space
  const n = resolutions.length;
  const aspectRatio = n <= 2 ? 4 : n <= 5 ? 3 : 2;

  charts.resolutions = buildChart('resolutionChart', 'bar', {
    labels: mapLabels(resolutions, 'resolution'),
    datasets: [
      {
        label,
        data: resolutions.map((r) => r.count),
        backgroundColor: '#667eea',
        maxBarThickness: 32,
      },
    ],
  }, {
    indexAxis: 'y',
    aspectRatio,
    plugins: { legend: { display: false } },
  });
}

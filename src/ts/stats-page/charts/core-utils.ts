/**
 * Stats chart core utilities — shared colors, chart builder, label mapper.
 * Converted from static/js/stats/charts/render/core-utils.js
 */

export const CHART_COLORS: string[] = [
  '#4a90e2', '#667eea', '#764ba2', '#f093fb', '#4facfe',
  '#00f2fe', '#43e97b', '#38f9d7', '#fa709a', '#fee140',
];

export function mapLabels<T>(rows: T[], key: keyof T): unknown[] {
  return rows.map((row) => row[key]);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function buildChart(ctxId: string, type: string, data: Record<string, any>, options?: Record<string, any>): unknown {
  const ctx = document.getElementById(ctxId) as HTMLCanvasElement | null;
  if (!ctx) return null;
  return new Chart(ctx, {
    type,
    data,
    options: Object.assign({ responsive: true, maintainAspectRatio: true }, options || {}),
  });
}

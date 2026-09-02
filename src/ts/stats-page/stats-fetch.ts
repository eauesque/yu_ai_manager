import type { BasicStatsResponse, HourlyStatsResponse, ModelsStatsResponse, MonthlyReport, ResolutionStatsResponse } from './data-loader';
import type { TimelineRow } from './charts/core';

type StatsAllPayload = {
  basic: BasicStatsResponse;
  hourly: HourlyStatsResponse;
  timeline: { data?: TimelineRow[] } | TimelineRow[];
  models: ModelsStatsResponse;
  resolutions: ResolutionStatsResponse;
};

export function unwrap<T>(data: { data?: T } | T): T {
  return ((data as { data?: T }).data ?? data) as T;
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  return res.json() as Promise<T>;
}

export async function fetchBasicStats(): Promise<BasicStatsResponse> {
  return unwrap<BasicStatsResponse>(await fetchJson('/api/stats'));
}

export async function fetchStatsDetails(): Promise<{
  basicStats: BasicStatsResponse;
  hourly: HourlyStatsResponse | null;
  timelineData: TimelineRow[];
  models: ModelsStatsResponse;
  resolutions: ResolutionStatsResponse;
}> {
  const allStats = unwrap<StatsAllPayload>(await fetchJson('/api/stats/all'));
  const timelineRaw = allStats.timeline;

  return {
    basicStats: allStats.basic ?? {
      file_count: 0,
      total_files: 0,
      excluded_files: 0,
      tag_count: 0,
      top_tags: [],
    },
    hourly: allStats.hourly ?? null,
    timelineData: Array.isArray(timelineRaw) ? timelineRaw : unwrap<TimelineRow[]>(timelineRaw ?? []),
    models: allStats.models ?? { top_models: [] },
    resolutions: allStats.resolutions ?? { top_resolutions: [], turning_points: [] },
  };
}

export async function fetchRatingsStats(): Promise<{ total_rated: number; distribution: Record<string, number> } | null> {
  try {
    const raw = await fetchJson<{ data?: { total_rated: number; distribution: Record<string, number> }; total_rated: number; distribution: Record<string, number> }>('/api/ratings/stats');
    return unwrap<{ total_rated: number; distribution: Record<string, number> }>(raw);
  } catch {
    return null;
  }
}

export async function fetchMonthlyReport(month: string): Promise<MonthlyReport | null> {
  try {
    const raw = await fetchJson<{ data?: MonthlyReport } | MonthlyReport>(
      `/api/stats/monthly-report?month=${encodeURIComponent(month)}&include_trophies=0`,
    );
    return unwrap<MonthlyReport>(raw);
  } catch {
    return null;
  }
}

export async function fetchStreak(): Promise<number> {
  try {
    const raw = await fetchJson<{ streak_days?: number }>('/api/stats/story');
    return typeof raw.streak_days === 'number' ? raw.streak_days : 0;
  } catch {
    return 0;
  }
}

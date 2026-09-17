/**
 * scheduler-api.ts — Helpers, constants, and API calls for the scheduler page.
 *
 * Extracted from index.ts to keep file sizes manageable.
 */

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

export function tr(key: string, fallback?: string): string {
  return (window as any).tr?.(key, fallback ?? '') ?? fallback ?? '';
}

export function showToast(msg: string): void {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3000);
}

/** Job description map (i18n keys in ui_runtime) */
export const JOB_DESCS: Record<string, string> = {
  db_vacuum: 'scheduler.job_desc_db_vacuum',
  db_integrity_check: 'scheduler.job_desc_db_integrity_check',
  thumbnail_cleanup: 'scheduler.job_desc_thumbnail_cleanup',
  thumbnail_integrity_check: 'scheduler.job_desc_thumbnail_integrity_check',
  github_issue_poll: 'scheduler.job_desc_github_issue_poll',
  bsky_notification_poll: 'scheduler.job_desc_bsky_notification_poll',
  prune_unused_tags: 'scheduler.job_desc_prune_unused_tags',
  refresh_monthly_stats: 'scheduler.job_desc_refresh_monthly_stats',
  rebuild_groups_index: 'scheduler.job_desc_rebuild_groups_index',
  db_backup: 'scheduler.job_desc_db_backup',
};

export function formatTime(iso: string | null): string {
  if (!iso) return '-';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function formatTimestamp(ts: number): string {
  if (!ts) return '-';
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
}

export function escapeHtml(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

/**
 * Parse a cron field value from a text input.
 * Returns undefined for '*' / empty (= APScheduler default = every),
 * an integer for a single value, or the raw string for comma lists.
 */
export function parseCronField(value: string): string | number | undefined {
  const v = value.trim();
  if (!v || v === '*') return undefined;
  // Single integer
  if (/^\d+$/.test(v)) return parseInt(v, 10);
  // Comma-separated list or cron expression -- pass as string
  return v;
}

/** Cron field definitions for the add-job dialog. Easily extensible. */
export interface CronFieldDef {
  /** DOM element ID */
  id: string;
  /** Key sent to trigger_args */
  key: string;
}

export const CRON_FIELDS: CronFieldDef[] = [
  { id: 'schedNewHour', key: 'hour' },
  { id: 'schedNewMinute', key: 'minute' },
  { id: 'schedNewDay', key: 'day' },
  { id: 'schedNewDow', key: 'day_of_week' },
];

/* ------------------------------------------------------------------ */
/*  API calls                                                          */
/* ------------------------------------------------------------------ */

export async function apiFetch(url: string, options?: RequestInit): Promise<any> {
  const resp = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      ...(options?.headers || {}),
    },
  });
  return resp.json();
}

export async function fetchStatus(): Promise<any> {
  return apiFetch('/api/scheduler/status');
}

export async function fetchHistory(): Promise<any> {
  return apiFetch('/api/scheduler/history');
}

export async function triggerJob(jobId: string): Promise<any> {
  return apiFetch(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/trigger`, { method: 'POST' });
}

export async function pauseJob(jobId: string): Promise<any> {
  return apiFetch(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/pause`, { method: 'POST' });
}

export async function resumeJob(jobId: string): Promise<any> {
  return apiFetch(`/api/scheduler/jobs/${encodeURIComponent(jobId)}/resume`, { method: 'POST' });
}

export async function deleteJob(jobId: string): Promise<any> {
  return apiFetch(`/api/scheduler/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' });
}

export async function addJob(body: Record<string, unknown>): Promise<any> {
  return apiFetch('/api/scheduler/jobs', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

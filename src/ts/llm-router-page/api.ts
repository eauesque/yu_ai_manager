/**
 * llm-router-page/api.ts — fetch helpers and types for the admin endpoints.
 *
 * Mirrors the scheduler-page/scheduler-api.ts pattern:
 *   - tr() i18n shim
 *   - showToast() helper
 *   - apiFetch() with X-Requested-With header
 *   - typed wrapper functions per endpoint
 */

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

export interface BackendModel {
  name: string;
  context_window: number | null;
  size_b: number | null;
}

export interface Backend {
  alias: string;
  base_url: string;
  source: 'static' | 'mdns';
  status: string;
  slo_state: string | null;
  disabled: boolean;
  model_count: number;
  models: BackendModel[];
  last_seen: string | null;
  last_error: string | null;
}

export interface StatusData {
  router: { version: string; alias_count: number };
  backends: Backend[];
  aliases: Record<string, string>;
}

export interface StatusEnvelope {
  ok: boolean;
  data: StatusData;
}

export interface RefreshRecord {
  alias: string;
  status: string;
  model_count: number;
  disabled: boolean;
  last_error: string | null;
}

async function apiFetch(url: string, options?: RequestInit): Promise<any> {
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

export async function fetchStatus(): Promise<StatusEnvelope> {
  return apiFetch('/api/llm_router/status');
}

export async function refreshAll(): Promise<{ ok: boolean; data: { refreshed: RefreshRecord[] } }> {
  return apiFetch('/api/llm_router/refresh', {
    method: 'POST',
    body: JSON.stringify({}),
  });
}

export async function refreshOne(alias: string): Promise<{ ok: boolean; data: { refreshed: RefreshRecord[] } }> {
  return apiFetch('/api/llm_router/refresh', {
    method: 'POST',
    body: JSON.stringify({ alias }),
  });
}

export async function disableBackend(alias: string): Promise<any> {
  return apiFetch(`/api/llm_router/backends/${encodeURIComponent(alias)}/disable`, {
    method: 'POST',
  });
}

export async function enableBackend(alias: string): Promise<any> {
  return apiFetch(`/api/llm_router/backends/${encodeURIComponent(alias)}/enable`, {
    method: 'POST',
  });
}

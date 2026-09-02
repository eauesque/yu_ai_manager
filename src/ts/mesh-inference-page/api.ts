/**
 * mesh-inference-page/api.ts — fetch helpers and types.
 * Mirrors llm-router-page/api.ts patterns for consistency.
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

export const ALL_TYPES = ['tagger', 'clip', 'yolo', 'whisper'] as const;
export type InferenceType = typeof ALL_TYPES[number];

export interface Peer {
  peer_id: string;
  name: string;
  status: 'online' | 'offline' | string;
  is_local: boolean;
  inference_types: string[];
  device_info: string;
  disabled_types: string[];
}

export interface StateResponse {
  ok: boolean;
  peers: Peer[];
}

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    ...(init ?? {}),
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      ...(init?.headers ?? {}),
    },
  });
  return resp.json() as Promise<T>;
}

export function fetchState(): Promise<StateResponse> {
  return apiFetch<StateResponse>('/api/mesh-inference/state');
}

export function refresh(): Promise<StateResponse> {
  return apiFetch<StateResponse>('/api/mesh-inference/refresh', { method: 'POST' });
}

export function toggle(
  peer_id: string,
  inference_type: InferenceType,
  disabled: boolean,
): Promise<any> {
  return apiFetch('/api/mesh-inference/toggle', {
    method: 'POST',
    body: JSON.stringify({ peer_id, inference_type, disabled }),
  });
}

export function bulk(
  action: 'disable_all_remote' | 'enable_all' | 'local_only',
  inference_type?: InferenceType,
): Promise<any> {
  return apiFetch('/api/mesh-inference/bulk', {
    method: 'POST',
    body: JSON.stringify(inference_type ? { action, inference_type } : { action }),
  });
}

/**
 * lan-cowork-page/api.ts — fetch helpers and shared types.
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

export interface Peer {
  peer_id: string;
  name: string;
  api_host: string;
  api_port: number;
  status: 'online' | 'offline' | string;
  version: string;
  gpu: string;
  token_expires_at?: number | null;
}

export interface ClientPairRequestResponse {
  ok: boolean;
  request_id?: string;
  sas?: string;
  error?: string;
}

export function clientPairRequest(peer_id: string): Promise<ClientPairRequestResponse> {
  return apiFetch<ClientPairRequestResponse>('/ext/lan_cowork/api/client/pair/request', {
    method: 'POST',
    body: JSON.stringify({ peer_id }),
  });
}

export function clientPairVerify(
  peer_id: string,
  request_id: string,
  pin: string,
): Promise<{ ok: boolean; error?: string }> {
  return apiFetch<{ ok: boolean; error?: string }>('/ext/lan_cowork/api/client/pair/verify', {
    method: 'POST',
    body: JSON.stringify({ peer_id, request_id, pin }),
  });
}

export interface DiscoverResponse {
  ok: boolean;
  peers?: Peer[];
  error?: string;
}

export interface SessionResponse {
  ok: boolean;
  session_id?: string;
  error?: string;
}

export interface ImportSession {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  total_files: number | null;
  done_files: number;
  peer_id: string;
  mode: string;
  import_folder: string;
}

export interface PollResponse {
  ok: boolean;
  session?: ImportSession;
  error?: string;
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

export function discoverPeers(): Promise<DiscoverResponse> {
  return apiFetch<DiscoverResponse>('/ext/lan_cowork/api/peer/discover');
}

export function createSession(
  peer_id: string,
  peer_name: string,
  mode: string,
  import_folder: string,
  options: { include_favorites: boolean; merge_metadata: boolean },
): Promise<SessionResponse> {
  return apiFetch<SessionResponse>('/ext/lan_cowork/api/peer/import/session', {
    method: 'POST',
    body: JSON.stringify({ peer_id, peer_name, mode, import_folder, options }),
  });
}

export function executeImport(session_id: string): Promise<{ ok: boolean; error?: string }> {
  return apiFetch<{ ok: boolean; error?: string }>('/ext/lan_cowork/api/peer/import/execute', {
    method: 'POST',
    body: JSON.stringify({ session_id }),
  });
}

export function pollSession(session_id: string): Promise<PollResponse> {
  return apiFetch<PollResponse>(`/ext/lan_cowork/api/peer/import/session/${session_id}`);
}

export interface LocalStatusResponse {
  ok: boolean;
  peer?: { roles?: string[] };
  error?: string;
}

export function fetchLocalStatus(): Promise<LocalStatusResponse> {
  return apiFetch<LocalStatusResponse>('/ext/lan_cowork/api/peer/status');
}

export function removePeer(peer_id: string): Promise<{ ok: boolean; error?: string }> {
  return apiFetch<{ ok: boolean; error?: string }>(
    `/ext/lan_cowork/api/peer/admin/${encodeURIComponent(peer_id)}`,
    { method: 'DELETE' },
  );
}

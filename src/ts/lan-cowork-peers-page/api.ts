/**
 * lan-cowork-peers-page/api.ts
 * API fetch helpers and shared types for the peer management page.
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

export interface PairingRequest {
  request_id: string;
  peer_id: string;
  host: string;
  port: number;
  status: string;
  created_at: number;
  expires_at: number;
  requester_ip: string;
  sas: string;
}

export interface TokenRecord {
  peer_id: string;
  created_at: number;
  expires_at: number | null;
  last_used: number | null;
}

export interface ApiResponse {
  ok: boolean;
  error?: string;
  state?: string;
  code?: string;
  attempts_remaining?: number;
}

export interface ListRequestsResponse extends ApiResponse {
  requests?: PairingRequest[];
}

export interface ListTokensResponse extends ApiResponse {
  tokens?: TokenRecord[];
}

export interface ApproveResponse extends ApiResponse {
  pin?: string;
  expires_in?: number;
}

export interface VerifyResponse extends ApiResponse {
  token?: string;
  expires_at?: number;
  peer_id?: string;
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

export function listPairingRequests(): Promise<ListRequestsResponse> {
  return apiFetch<ListRequestsResponse>('/ext/lan_cowork/api/peer/pair/requests');
}

export function listTokens(): Promise<ListTokensResponse> {
  return apiFetch<ListTokensResponse>('/ext/lan_cowork/api/peer/tokens');
}

export function approveRequest(request_id: string): Promise<ApproveResponse> {
  return apiFetch<ApproveResponse>('/ext/lan_cowork/api/peer/pair/approve', {
    method: 'POST',
    body: JSON.stringify({ request_id }),
  });
}

export function rejectRequest(request_id: string): Promise<ApiResponse> {
  return apiFetch<ApiResponse>('/ext/lan_cowork/api/peer/pair/reject', {
    method: 'POST',
    body: JSON.stringify({ request_id }),
  });
}

export function revokeToken(peer_id: string): Promise<ApiResponse> {
  return apiFetch<ApiResponse>(`/ext/lan_cowork/api/peer/tokens/${encodeURIComponent(peer_id)}/revoke`, {
    method: 'POST',
  });
}

export function verifyPin(request_id: string, pin: string): Promise<VerifyResponse> {
  return apiFetch<VerifyResponse>('/ext/lan_cowork/api/peer/pair/verify', {
    method: 'POST',
    body: JSON.stringify({ request_id, pin }),
  });
}

// --- client-side pairing proxy (Task 16) ---

export interface ClientPairRequestResponse extends ApiResponse {
  request_id?: string;
  sas?: string;
}

/** Ask local server to initiate pairing with a remote peer. */
export function clientPairRequest(peer_id: string): Promise<ClientPairRequestResponse> {
  return apiFetch<ClientPairRequestResponse>('/ext/lan_cowork/api/client/pair/request', {
    method: 'POST',
    body: JSON.stringify({ peer_id }),
  });
}

/** Submit PIN to complete pairing via local proxy. */
export function clientPairVerify(peer_id: string, request_id: string, pin: string): Promise<ApiResponse> {
  return apiFetch<ApiResponse>('/ext/lan_cowork/api/client/pair/verify', {
    method: 'POST',
    body: JSON.stringify({ peer_id, request_id, pin }),
  });
}

// --- fleet settings ---

export interface FleetSettingsResponse extends ApiResponse {
  chief?: boolean;
}

export function getFleetSettings(): Promise<FleetSettingsResponse> {
  return apiFetch<FleetSettingsResponse>('/ext/lan_cowork/api/settings/fleet');
}

export function saveFleetSettings(chief: boolean): Promise<FleetSettingsResponse> {
  return apiFetch<FleetSettingsResponse>('/ext/lan_cowork/api/settings/fleet', {
    method: 'POST',
    body: JSON.stringify({ chief }),
  });
}

// --- Fleet permissions ---

export interface FleetAllowlistsResponse extends ApiResponse {
  allow_log_stream_from?: string[];
  allow_update_from?: string[];
  allow_restart_from?: string[];
  allow_remote_update?: boolean;
}

export interface FleetAllowlistsSavePayload {
  allow_log_stream_from?: string[];
  allow_update_from?: string[];
  allow_restart_from?: string[];
  allow_remote_update?: boolean;
}

export interface PeerPermissionResult {
  peer_id: string;
  name: string;
  status: string;
  restart: boolean | null;
  update: boolean | null;
  log_stream: boolean | null;
  allow_remote_update: boolean | null;
  error: string | null;
}

export interface MyPermissionsResponse extends ApiResponse {
  peers?: PeerPermissionResult[];
}

export interface DiscoverWithAuthResponse {
  ok: boolean;
  peers?: Array<{
    peer_id: string;
    name: string;
    status: string;
    token_expires_at?: number | null;
    has_inbound_token?: boolean;
  }>;
}

export function getFleetAllowlists(): Promise<FleetAllowlistsResponse> {
  return apiFetch<FleetAllowlistsResponse>('/ext/lan_cowork/api/settings/fleet/allowlists');
}

export function saveFleetAllowlists(payload: FleetAllowlistsSavePayload): Promise<FleetAllowlistsResponse> {
  return apiFetch<FleetAllowlistsResponse>('/ext/lan_cowork/api/settings/fleet/allowlists', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getMyPermissions(bust = false): Promise<MyPermissionsResponse> {
  const url = bust
    ? '/ext/lan_cowork/api/settings/fleet/my-permissions?bust=1'
    : '/ext/lan_cowork/api/settings/fleet/my-permissions';
  return apiFetch<MyPermissionsResponse>(url);
}

export function discoverPeersWithAuth(): Promise<DiscoverWithAuthResponse> {
  return apiFetch<DiscoverWithAuthResponse>('/ext/lan_cowork/api/peer/discover');
}

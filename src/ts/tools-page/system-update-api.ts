import type {
  ApiEnvelope,
  ApiErrorPayload,
  ExtensionUpdateResult,
  SystemUpdateCheckResult,
  UnifiedCheckResult,
  UpdateActionResult,
  UpdateStatusResult,
} from './system-update-types';

const REQUEST_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' };

export interface JsonRequestResult<T> {
  ok: boolean;
  status: number;
  payload: T | ApiEnvelope<T> | ApiErrorPayload;
}

function _isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

export function unwrapApiPayload<T extends object>(payload: T | ApiEnvelope<T>): T {
  if (!_isObject(payload)) {
    throw new Error('Invalid API response');
  }

  if ('data' in payload && _isObject(payload.data)) {
    const hasLegacyKeys = Object.keys(payload).some((key) => !['ok', 'error', 'data'].includes(key));
    if (!hasLegacyKeys) {
      return payload.data as T;
    }
  }

  return payload as T;
}

export function getApiErrorMessage(payload: unknown, fallback: string): string {
  if (_isObject(payload) && typeof payload.error === 'string' && payload.error) {
    return payload.error;
  }
  return fallback;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<JsonRequestResult<T>> {
  const response = await fetch(url, init);
  const payload = await response.json() as T | ApiEnvelope<T> | ApiErrorPayload;
  return {
    ok: response.ok,
    status: response.status,
    payload,
  };
}

export async function fetchSystemUpdateCheck(): Promise<SystemUpdateCheckResult> {
  const { payload } = await requestJson<SystemUpdateCheckResult>('/api/system/update/check', {
    headers: REQUEST_HEADERS,
  });
  return unwrapApiPayload(payload as SystemUpdateCheckResult | ApiEnvelope<SystemUpdateCheckResult>);
}

export async function fetchUpdateStatus(): Promise<UpdateStatusResult> {
  const { payload } = await requestJson<UpdateStatusResult>('/api/system/update/status', {
    headers: REQUEST_HEADERS,
  });
  return unwrapApiPayload(payload as UpdateStatusResult | ApiEnvelope<UpdateStatusResult>);
}

export async function fetchUnifiedUpdateCheck(): Promise<UnifiedCheckResult> {
  const { payload } = await requestJson<UnifiedCheckResult>('/api/system/update/unified-check?force=1', {
    headers: REQUEST_HEADERS,
  });
  return unwrapApiPayload(payload as UnifiedCheckResult | ApiEnvelope<UnifiedCheckResult>);
}

export async function requestApplySystemUpdate(): Promise<JsonRequestResult<UpdateActionResult>> {
  return requestJson<UpdateActionResult>('/api/system/update/apply', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...REQUEST_HEADERS,
    },
    body: JSON.stringify({ confirm: 'update' }),
  });
}

export async function requestSingleExtensionUpdate(name: string): Promise<JsonRequestResult<ExtensionUpdateResult>> {
  return requestJson<ExtensionUpdateResult>(`/api/extensions/${encodeURIComponent(name)}/update`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...REQUEST_HEADERS,
    },
    body: '{}',
  });
}

export async function requestApplyUnifiedUpdates(body: Record<string, unknown>): Promise<JsonRequestResult<UpdateActionResult>> {
  return requestJson<UpdateActionResult>('/api/system/update/unified-apply', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...REQUEST_HEADERS,
    },
    body: JSON.stringify(body),
  });
}

import {
  clearSendTarget,
  fetchBackends,
  fetchGroups,
  loadSendTarget,
  resolveTargetToBackends,
  type BackendEntry,
} from '../shared/bridge-server';
import { customConfirm } from '../shared/dialog';

export type BridgeFanOutType = 'comfyui' | 'sd_webui';

export type ServerTaskState = {
  backend: BackendEntry | null;
  task_id: string;
  backend_id: string;
  base_url: string;
  status: 'pending' | 'generating' | 'done' | 'error';
  progress: number;
  step: number;
  total_steps: number;
  images: Array<{ url: string; received_at_ms: number }>;
  elapsed_ms?: number;
  error_message?: string;
};

export type FanOutResult = {
  state: ServerTaskState;
  data: Record<string, unknown> | null;
};

type RunFanOutOptions = {
  onResult?: (result: FanOutResult) => void;
};

type ProgressPayload = {
  status?: string;
  progress?: number;
  step?: number;
  total_steps?: number;
  registered?: boolean;
};

const _taskMap = new Map<string, ServerTaskState>();
let _currentBridgeType: BridgeFanOutType | null = null;

export async function initFanOut(bridgeType: BridgeFanOutType): Promise<ServerTaskState[]> {
  _taskMap.clear();
  _currentBridgeType = bridgeType;

  const target = await loadSendTarget(bridgeType);
  if (target.kind === 'default') {
    const state: ServerTaskState = {
      backend: null,
      task_id: crypto.randomUUID(),
      backend_id: '__fallback__',
      base_url: '',
      status: 'pending',
      progress: 0,
      step: 0,
      total_steps: 0,
      images: [],
    };
    _taskMap.set('__default__', state);
    return [state];
  }

  const [beRes, grRes] = await Promise.all([fetchBackends(), fetchGroups()]);
  if (!beRes.ok || !grRes.ok) {
    await clearSendTarget(bridgeType);
    return [];
  }

  const resolved = resolveTargetToBackends(target, beRes.data, grRes.data, bridgeType);
  if (resolved.length === 0) {
    await clearSendTarget(bridgeType);
    return [];
  }

  const states = resolved.map((backend): ServerTaskState => ({
    backend,
    task_id: crypto.randomUUID(),
    backend_id: backend.id,
    base_url: backend.base_url,
    status: 'pending',
    progress: 0,
    step: 0,
    total_steps: 0,
    images: [],
  }));
  for (const state of states) _taskMap.set(state.backend_id, state);
  return states;
}

export function isDefaultFanOut(states: ServerTaskState[]): boolean {
  return states.length === 1 && states[0]?.backend_id === '__fallback__';
}

export async function runFanOut(
  states: ServerTaskState[],
  requestBody: Record<string, unknown>,
  generateUrl: string,
  options: RunFanOutOptions = {},
): Promise<FanOutResult[]> {
  if (states.length > 8) {
    const ok = await customConfirm(`Sending to ${states.length} servers. Continue?`);
    if (!ok) return [];
  }

  const results = await Promise.allSettled(
    states.map(state => _sendOne(state, requestBody, generateUrl, options)),
  );
  const fanOutResults: FanOutResult[] = [];
  results.forEach((result, index) => {
    if (result.status === 'rejected') {
      states[index].status = 'error';
      states[index].error_message = String(result.reason);
    } else {
      fanOutResults.push(result.value);
    }
  });
  _onAllComplete();
  return fanOutResults;
}

export function getFanOutStates(): ServerTaskState[] {
  return [..._taskMap.values()];
}

async function _sendOne(
  state: ServerTaskState,
  baseBody: Record<string, unknown>,
  generateUrl: string,
  options: RunFanOutOptions,
): Promise<FanOutResult> {
  state.task_id = crypto.randomUUID();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  };
  if (state.backend_id !== '__fallback__') headers['X-Backend-Id'] = state.backend_id;

  const body = {
    ...baseBody,
    task_id: state.task_id,
    ...(state.backend_id !== '__fallback__' ? { backend_id: state.backend_id } : {}),
  };
  state.status = 'generating';

  const res = await fetch(generateUrl, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    state.status = 'error';
    state.error_message = `HTTP ${res.status}`;
    const result = { state, data: null };
    options.onResult?.(result);
    return result;
  }

  _pollProgress(state, generateUrl.replace('/api/generate', '/api/progress'));

  const data = await _readJsonObject(res);
  if (data && data.ok === false) {
    state.status = 'error';
    state.error_message = String(data.error ?? 'Generation failed');
  } else {
    state.status = 'done';
    if (typeof data?.elapsed_ms === 'number') state.elapsed_ms = data.elapsed_ms;
  }
  const result = { state, data };
  options.onResult?.(result);
  return result;
}

function _pollProgress(state: ServerTaskState, progressUrl: string): void {
  const taskId = state.task_id;
  const interval = window.setInterval(async () => {
    try {
      if (state.status === 'done' || state.status === 'error') {
        clearInterval(interval);
        _onAllComplete();
        return;
      }
      const url = `${progressUrl}?task_id=${encodeURIComponent(taskId)}`;
      const res = await fetch(
        url,
        state.backend_id !== '__fallback__'
          ? { headers: { 'X-Backend-Id': state.backend_id } }
          : {},
      );
      if (!res.ok) return;
      const d = await res.json() as ProgressPayload | { data?: ProgressPayload };
      const progressData: ProgressPayload = 'data' in d && d.data ? d.data : d as ProgressPayload;
      state.progress = progressData.progress ?? 0;
      state.step = progressData.step ?? 0;
      state.total_steps = progressData.total_steps ?? 0;
      const status = progressData.status ?? '';
      if (status === 'done' || status === 'error') {
        state.status = status;
        clearInterval(interval);
        _onAllComplete();
      } else if (progressData.registered || status) {
        state.status = 'generating';
      }
    } catch {
      // Keep polling; transient network errors are common while a backend starts.
    }
  }, 1000);
}

async function _readJsonObject(res: Response): Promise<Record<string, unknown> | null> {
  try {
    const data = await res.json();
    return data && typeof data === 'object' && !Array.isArray(data)
      ? data as Record<string, unknown>
      : null;
  } catch {
    return null;
  }
}

function _onAllComplete(): void {
  const allDone = [..._taskMap.values()].every(
    state => state.status === 'done' || state.status === 'error',
  );
  if (allDone && _currentBridgeType) {
    void clearSendTarget(_currentBridgeType);
  }
}

export const BridgeFanOut = {
  initFanOut,
  isDefaultFanOut,
  runFanOut,
  getFanOutStates,
};

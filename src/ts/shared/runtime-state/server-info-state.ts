type ServerInfoPayload = Record<string, unknown>;

let _cachedServerInfo: ServerInfoPayload | undefined;
let _oneShotServerInfo: ServerInfoPayload | undefined;
let _serverInfoPromise: Promise<ServerInfoPayload | null> | null = null;
let _serverInfoHasPin: boolean | undefined;
let _serverFileCount: number | undefined;
let _serverBootState = 'ready';
let _serverPlatform = '';

export function getCachedServerInfo(): ServerInfoPayload | undefined {
  return _cachedServerInfo;
}

export function primeCachedServerInfo(data: ServerInfoPayload): void {
  _cachedServerInfo = data;
  _oneShotServerInfo = data;
  _serverInfoPromise = Promise.resolve(data);
}

export function consumeCachedServerInfo(): ServerInfoPayload | undefined {
  const data = _oneShotServerInfo;
  _oneShotServerInfo = undefined;
  return data;
}

export function invalidateCachedServerInfo(): void {
  _cachedServerInfo = undefined;
  _oneShotServerInfo = undefined;
  _serverInfoPromise = null;
}

export function setServerInfoHasPin(value: boolean): void {
  _serverInfoHasPin = value;
}

export function getServerInfoHasPin(): boolean | undefined {
  return _serverInfoHasPin;
}

export function getServerFileCount(): number | undefined {
  return _serverFileCount;
}

export function getServerBootState(): string {
  return _serverBootState;
}

export function getServerPlatform(): string {
  return _serverPlatform;
}

export function applyServerInfoPayload(data: ServerInfoPayload): void {
  _serverInfoHasPin = !!data.has_pin;
  _serverFileCount = typeof data.file_count === 'number' ? data.file_count : undefined;
  _serverBootState = typeof data.boot_state === 'string' ? data.boot_state : 'ready';
  _serverPlatform = typeof data.platform === 'string' ? data.platform : '';
}

export function loadServerInfo(
  fetcher: (input: string, init?: RequestInit) => Promise<Response> = fetch,
  options?: RequestInit,
  loadOptions?: { force?: boolean },
): Promise<ServerInfoPayload | null> {
  if (!loadOptions?.force) {
    if (_cachedServerInfo) return Promise.resolve(_cachedServerInfo);
    if (_serverInfoPromise) return _serverInfoPromise;
  }

  _serverInfoPromise = fetcher('/api/server-info', options)
    .then((resp) => resp.json())
    .then((info) => {
      const data = (info?.data || info) as ServerInfoPayload | null;
      if (!data || typeof data !== 'object') return null;
      primeCachedServerInfo(data);
      applyServerInfoPayload(data);
      return data;
    })
    .catch(() => null)
    .finally(() => {
      if (!_cachedServerInfo) {
        _serverInfoPromise = null;
      }
    });

  return _serverInfoPromise;
}

export function reloadServerInfo(
  fetcher: (input: string, init?: RequestInit) => Promise<Response> = fetch,
  options?: RequestInit,
): Promise<ServerInfoPayload | null> {
  return loadServerInfo(fetcher, options, { force: true });
}

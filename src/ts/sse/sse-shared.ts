/**
 * sse-shared.ts -- Singleton SSE connection manager.
 *
 * All modules share a single EventSource via pub/sub API.
 * Visibility-aware: disconnects when tab is hidden, reconnects when visible.
 * Lazy: only connects when at least one subscriber exists.
 *
 * Types, constants, and EventSource guard are in sse-types.ts.
 */

import {
  type SseHandler,
  type SseEventType,
  _NativeEventSource,
  SSE_FALLBACK_URL,
  SSE_INFO_URL,
  BACKOFF_INITIAL_MS,
  BACKOFF_MAX_MS,
} from './sse-types';

// Re-export types and guard for backward compatibility
export { _NativeEventSource } from './sse-types';
export type { SseHandler, SseEventType } from './sse-types';

/* ------------------------------------------------------------------ */
/*  State                                                              */
/* ------------------------------------------------------------------ */

/** Direct connection URL to the dedicated SSE server (cached) */
let _sseDirectBase: string | null | undefined = undefined; // undefined = not yet fetched
let _sseDirectExpiry = 0;

/** eventType -> Set of handlers */
const _subs = new Map<string, Set<SseHandler>>();
let _es: EventSource | null = null;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _backoff = BACKOFF_INITIAL_MS;
let _boundEvents: string[] = [];
/** Delay connection until page load completes (prevents HTTP/1.1 connection contention) */
let _pageLoaded = document.readyState === 'complete';
if (!_pageLoaded) {
  window.addEventListener('load', () => {
    _pageLoaded = true;
    // After load completes, start connection if subscribers are waiting
    if (totalSubscribers() > 0 && !document.hidden) {
      connect();
    }
  }, { once: true });
}

/* ------------------------------------------------------------------ */
/*  Internal helpers                                                   */
/* ------------------------------------------------------------------ */

/** Build the SSE URL with a `?types=` filter for currently subscribed types.
 *  If the dedicated SSE server is known, connect directly to avoid 307 redirects.
 *  (Firefox fails EventSource on cross-port 307 redirects) */
function buildUrl(): string {
  const types = Array.from(_subs.keys());
  const query = types.length > 0 ? `types=${types.join(',')}` : '';

  if (_sseDirectBase !== undefined) {
    // Already resolved: null means fallback, string means direct connection
    const base = _sseDirectBase ?? SSE_FALLBACK_URL;
    if (!query) return base;
    return `${base}${base.includes('?') ? '&' : '?'}${query}`;
  }
  // Not yet resolved: connect via fallback URL first, fetch SSE port in background
  return query ? `${SSE_FALLBACK_URL}?${query}` : SSE_FALLBACK_URL;
}

/** Count total subscribers across all event types. */
function totalSubscribers(): number {
  let n = 0;
  for (const set of _subs.values()) n += set.size;
  return n;
}

/** Dispatch parsed data to all handlers for a given event type. */
function dispatch(eventType: string, data: unknown): void {
  const handlers = _subs.get(eventType);
  if (!handlers) return;
  for (const fn of handlers) {
    try {
      fn(data);
    } catch (e) {
      console.warn('[SSE] handler error:', e);
    }
  }
}

/** Fetch SSE server port info and cache the direct connection URL. */
async function resolveSseUrl(): Promise<void> {
  if (_sseDirectBase !== undefined) return; // already resolved
  try {
    const resp = await fetch(SSE_INFO_URL);
    if (!resp.ok) { _sseDirectBase = null; return; }
    let info: Record<string, unknown>;
    try { info = await resp.json(); } catch { _sseDirectBase = null; return; }
    if (typeof info.stream_url === 'string' && info.stream_url) {
      _sseDirectBase = info.stream_url;
      _sseDirectExpiry = typeof info.refresh_after === 'number' ? info.refresh_after : 0;
    } else {
      _sseDirectBase = null; // fallback
      _sseDirectExpiry = 0;
    }
  } catch {
    _sseDirectBase = null;
    _sseDirectExpiry = 0;
  }
}

/** Create and wire up the EventSource. */
function openEventSource(): void {
  const url = buildUrl();
  _es = new _NativeEventSource(url);

  // Listen for each subscribed event type using addEventListener
  // (server sends `event: <type>` format, so onmessage won't fire)
  const types = Array.from(_subs.keys());
  for (const t of types) {
    _es.addEventListener(t, ((ev: MessageEvent) => {
      _backoff = BACKOFF_INITIAL_MS; // reset on success
      let parsed: unknown;
      try {
        parsed = JSON.parse(ev.data);
      } catch {
        parsed = ev.data;
      }
      dispatch(t, parsed);
    }) as EventListener);
  }
  _boundEvents = types;

  _es.onerror = () => {
    disconnect();
    scheduleReconnect();
  };

  // Reset backoff on successful open
  _es.onopen = () => {
    _backoff = BACKOFF_INITIAL_MS;
  };
}

/** Connect the shared EventSource. */
function connect(): void {
  if (_es) return;
  if (totalSubscribers() === 0) return;
  // Don't connect during page load (conflicts with HTTP/1.1 connection limit, fails in Firefox)
  if (!_pageLoaded) return;

  const now = Math.floor(Date.now() / 1000);
  if (_sseDirectBase !== undefined && _sseDirectExpiry > 0 && now >= _sseDirectExpiry) {
    _sseDirectBase = undefined;
    _sseDirectExpiry = 0;
  }

  // Fetch SSE port info before connecting (async on first call only)
  if (_sseDirectBase === undefined) {
    resolveSseUrl().then(() => {
      if (!_es && totalSubscribers() > 0 && !document.hidden) {
        openEventSource();
      }
    });
    return;
  }
  openEventSource();
}

/** Disconnect the shared EventSource. */
function disconnect(): void {
  if (_es) {
    _es.close();
    _es = null;
  }
  _boundEvents = [];
}

/** Schedule a reconnection with exponential backoff. */
function scheduleReconnect(): void {
  if (_reconnectTimer) return;
  if (totalSubscribers() === 0) return;

  _reconnectTimer = setTimeout(() => {
    _reconnectTimer = null;
    if (!document.hidden) connect();
  }, _backoff);

  _backoff = Math.min(_backoff * 2, BACKOFF_MAX_MS);
}

/** Cancel any pending reconnect timer. */
function cancelReconnect(): void {
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer);
    _reconnectTimer = null;
  }
}

/**
 * If subscribed types changed while connected, reconnect to update
 * the server-side filter.
 */
function maybeReconnect(): void {
  if (!_es) return;
  const current = Array.from(_subs.keys()).sort().join(',');
  const bound = _boundEvents.slice().sort().join(',');
  if (current !== bound) {
    disconnect();
    connect();
  }
}

/* ------------------------------------------------------------------ */
/*  Visibility handler                                                 */
/* ------------------------------------------------------------------ */

function onVisibilityChange(): void {
  if (document.hidden) {
    disconnect();
    cancelReconnect();
  } else {
    connect();
  }
}

// Register once
document.addEventListener('visibilitychange', onVisibilityChange);

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */

/**
 * Subscribe to a named SSE event type.
 * Connection is established lazily on first subscriber.
 */
export function sseSubscribe(eventType: SseEventType, handler: SseHandler): void {
  let set = _subs.get(eventType);
  if (!set) {
    set = new Set();
    _subs.set(eventType, set);
  }
  set.add(handler);

  // First subscriber for this type -- connect or reconnect to add the filter
  if (!document.hidden) {
    if (!_es) {
      connect();
    } else {
      maybeReconnect();
    }
  }
}

/**
 * Unsubscribe a handler from a named SSE event type.
 * If no subscribers remain, the connection is closed.
 */
export function sseUnsubscribe(eventType: SseEventType, handler: SseHandler): void {
  const set = _subs.get(eventType);
  if (!set) return;
  set.delete(handler);
  if (set.size === 0) {
    _subs.delete(eventType);
  }

  if (totalSubscribers() === 0) {
    disconnect();
    cancelReconnect();
  } else {
    maybeReconnect();
  }
}

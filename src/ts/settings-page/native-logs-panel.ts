/**
 * Settings page — Rust native logs panel.
 *
 * Independent from Python logs-tab.ts. Uses /api/logs/native/* endpoints
 * backed by the Rust LogRingBuffer. SSE event type is "log".
 */

import { _NativeEventSource } from '../sse';

interface LogEntry {
  seq: number;
  timestamp: number;
  level: string;
  target: string;
  message: string;
  fields?: Record<string, unknown>;
}

const LOG_API_RECENT = '/api/logs/native/recent';
const LOG_API_STREAM = '/api/logs/native/stream';
const MAX_DISPLAYED_LINES = 2000;

let _es: EventSource | null = null;
let _paused = false;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _initialized = false;
let _searchText = '';
let _pendingEntries: LogEntry[] = [];
let _flushScheduled = false;

function container(): HTMLElement | null {
  return document.getElementById('nativeLogContent');
}

function setStatus(text: string): void {
  const el = document.getElementById('nativeLogStatus');
  if (el) el.textContent = text;
}

function selectedLevel(): string {
  const sel = document.getElementById('nativeLogLevelFilter') as HTMLSelectElement | null;
  return sel?.value ?? '';
}

function isNearBottom(el: HTMLElement): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 50;
}

function levelClass(level: string): string {
  switch (level.toUpperCase()) {
    case 'DEBUG': return 'log-debug';
    case 'INFO': return 'log-info';
    case 'WARN': return 'log-warning';
    case 'ERROR': return 'log-error';
    default: return 'log-info';
  }
}

function formatTimestamp(ts: number): string {
  const d = new Date(ts * 1000);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

function createLogLine(entry: LogEntry): HTMLDivElement {
  const div = document.createElement('div');
  div.className = `log-line ${levelClass(entry.level)}`;
  const ts = formatTimestamp(entry.timestamp);
  const lvl = entry.level.substring(0, 4).padEnd(4);
  div.textContent = `${ts} [${lvl}] ${entry.target}: ${entry.message}`;
  if (_searchText && !div.textContent.toLowerCase().includes(_searchText)) {
    div.style.display = 'none';
  }
  return div;
}

function appendEntries(entries: LogEntry[]): void {
  const c = container();
  if (!c) return;
  const wasBottom = isNearBottom(c);
  const frag = document.createDocumentFragment();
  for (const entry of entries) frag.appendChild(createLogLine(entry));
  c.appendChild(frag);
  const overflow = c.children.length - MAX_DISPLAYED_LINES;
  for (let i = 0; i < overflow; i++) c.removeChild(c.firstChild!);
  if (wasBottom) c.scrollTop = c.scrollHeight;
}

function scheduleFlush(): void {
  if (_flushScheduled) return;
  _flushScheduled = true;
  requestAnimationFrame(() => {
    _flushScheduled = false;
    if (!_pendingEntries.length) return;
    const batch = _pendingEntries;
    _pendingEntries = [];
    appendEntries(batch);
  });
}

function queueEntry(entry: LogEntry): void {
  _pendingEntries.push(entry);
  if (_pendingEntries.length > MAX_DISPLAYED_LINES) {
    _pendingEntries.splice(0, _pendingEntries.length - MAX_DISPLAYED_LINES);
  }
  scheduleFlush();
}

function connect(): void {
  disconnect();
  const level = selectedLevel();
  const params = level ? `?level=${encodeURIComponent(level)}` : '';
  _es = new _NativeEventSource(`${LOG_API_STREAM}${params}`);
  _es.addEventListener('log', ((ev: MessageEvent) => {
    if (_paused) return;
    try { queueEntry(JSON.parse(ev.data) as LogEntry); } catch { /* ignore */ }
  }) as EventListener);
  _es.onopen = () => setStatus('Connected');
  _es.onerror = () => {
    setStatus('Disconnected');
    // Server closes the stream after MAX_STREAM_AGE_SECS (3600 s); reconnect automatically.
    if (_reconnectTimer) return;
    _reconnectTimer = setTimeout(() => {
      _reconnectTimer = null;
      connect();
    }, 3000);
  };
}

export function disconnect(): void {
  if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
  if (_es) { _es.close(); _es = null; }
  setStatus('');
}

export async function init(): Promise<void> {
  if (_initialized) {
    if (!_es) connect();
    return;
  }
  _initialized = true;
  setStatus('Loading...');
  try {
    const level = selectedLevel();
    const params = level ? `?level=${encodeURIComponent(level)}&limit=200` : '?limit=200';
    const resp = await fetch(`${LOG_API_RECENT}${params}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = await resp.json() as { entries?: LogEntry[] };
    const c = container();
    if (c) c.replaceChildren();
    _pendingEntries = [];
    appendEntries(json.entries ?? []);
  } catch {
    setStatus('Failed to load');
  }
  connect();
}

export function togglePause(): void {
  _paused = !_paused;
  const btn = document.getElementById('nativeLogPauseBtn');
  if (btn) btn.textContent = _paused ? 'Resume' : 'Pause';
  setStatus(_paused ? 'Paused' : 'Connected');
}

export function clear(): void {
  _pendingEntries = [];
  container()?.replaceChildren();
}

export function onLevelChange(): void {
  _initialized = false;
  void init();
}

export function onSearchInput(): void {
  const input = document.getElementById('nativeLogSearchInput') as HTMLInputElement | null;
  _searchText = (input?.value ?? '').toLowerCase();
  const c = container();
  if (!c) return;
  for (const child of Array.from(c.children)) {
    const el = child as HTMLElement;
    el.style.display = (!_searchText || el.textContent?.toLowerCase().includes(_searchText)) ? '' : 'none';
  }
}

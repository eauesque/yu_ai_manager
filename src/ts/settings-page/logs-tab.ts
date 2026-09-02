/**
 * Settings page — Logs tab.
 *
 * Fetches recent log entries on tab open, then connects a dedicated SSE
 * stream for real-time updates.  Uses _NativeEventSource directly (not
 * the shared SSE engine) because this is a high-frequency, page-specific
 * stream.
 */

import { _NativeEventSource } from '../sse';

/* ------------------------------------------------------------------ */
/*  State                                                              */
/* ------------------------------------------------------------------ */

let _es: EventSource | null = null;
let _paused = false;
let _initialized = false;
let _searchText = '';

// rAF-batched append buffer. SSE events can arrive at high frequency
// (hundreds/sec under DEBUG); appending per-event forces a layout flush
// each time and, combined with atelier's backdrop-filter buttons in the
// same viewport, drags down whole-desktop compositing on Windows.
let _pendingEntries: LogEntry[] = [];
let _flushScheduled = false;

const LOG_API_RECENT = '/api/logs/recent';
const LOG_API_STREAM = '/api/logs/stream';
const MAX_DISPLAYED_LINES = 2000;

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

interface LogEntry {
  timestamp: number;
  level: string;
  target: string;
  message: string;
  seq: number;
  fields?: Record<string, unknown>;
}

function levelClass(level: string): string {
  switch (level.toUpperCase()) {
    case 'DEBUG': return 'log-debug';
    case 'INFO': return 'log-info';
    case 'WARNING': return 'log-warning';
    case 'ERROR': return 'log-error';
    case 'CRITICAL': return 'log-critical';
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

function getLogContainer(): HTMLElement | null {
  return document.getElementById('logContent');
}

function getSelectedLevel(): string {
  const sel = document.getElementById('logLevelFilter') as HTMLSelectElement | null;
  return sel?.value ?? '';
}

function setStatus(text: string): void {
  const el = document.getElementById('logStatus');
  if (el) el.textContent = text;
}

function isNearBottom(el: HTMLElement): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 50;
}

/* ------------------------------------------------------------------ */
/*  DOM manipulation                                                   */
/* ------------------------------------------------------------------ */

function formatFields(fields: Record<string, unknown> | undefined): string {
  if (!fields) return '';
  const parts = Object.entries(fields).map(([k, v]) => `${k}=${String(v)}`);
  return parts.length ? ` {${parts.join(', ')}}` : '';
}

function createLogLine(entry: LogEntry): HTMLDivElement {
  const div = document.createElement('div');
  div.className = `log-line ${levelClass(entry.level)}`;
  const ts = formatTimestamp(entry.timestamp);
  const lvl = entry.level.substring(0, 4).padEnd(4);
  const src = entry.target ? `${entry.target}: ` : '';
  div.textContent = `${ts} [${lvl}] ${src}${entry.message}${formatFields(entry.fields)}`;
  // hide if doesn't match search
  if (_searchText && !div.textContent.toLowerCase().includes(_searchText)) {
    div.style.display = 'none';
  }
  return div;
}

function appendEntries(entries: LogEntry[]): void {
  const container = getLogContainer();
  if (!container) return;

  const wasBottom = isNearBottom(container);

  const frag = document.createDocumentFragment();
  for (const entry of entries) {
    frag.appendChild(createLogLine(entry));
  }
  container.appendChild(frag);

  // Trim excess lines
  const overflow = container.children.length - MAX_DISPLAYED_LINES;
  for (let i = 0; i < overflow; i++) {
    container.removeChild(container.firstChild!);
  }

  if (wasBottom) {
    container.scrollTop = container.scrollHeight;
  }
}

function scheduleFlush(): void {
  if (_flushScheduled) return;
  _flushScheduled = true;
  requestAnimationFrame(() => {
    _flushScheduled = false;
    if (_pendingEntries.length === 0) return;
    const batch = _pendingEntries;
    _pendingEntries = [];
    appendEntries(batch);
  });
}

function queueEntry(entry: LogEntry): void {
  _pendingEntries.push(entry);
  // Cap buffer so a flood while the tab is hidden / rAF is throttled
  // can't grow without bound. We only display MAX_DISPLAYED_LINES anyway.
  if (_pendingEntries.length > MAX_DISPLAYED_LINES) {
    _pendingEntries.splice(0, _pendingEntries.length - MAX_DISPLAYED_LINES);
  }
  scheduleFlush();
}

/* ------------------------------------------------------------------ */
/*  SSE connection                                                     */
/* ------------------------------------------------------------------ */

function connectLogStream(): void {
  disconnectLogStream();
  const level = getSelectedLevel();
  const params = level ? `?level=${encodeURIComponent(level)}` : '';
  const url = `${LOG_API_STREAM}${params}`;

  _es = new _NativeEventSource(url);
  _es.addEventListener('log.entry', ((ev: MessageEvent) => {
    if (_paused) return;
    try {
      const entry: LogEntry = JSON.parse(ev.data);
      queueEntry(entry);
    } catch {
      // ignore parse errors
    }
  }) as EventListener);

  _es.onopen = () => setStatus('Connected');
  _es.onerror = () => setStatus('Disconnected');
}

export function disconnectLogStream(): void {
  if (_es) {
    _es.close();
    _es = null;
  }
  setStatus('');
}

/* ------------------------------------------------------------------ */
/*  Public API (window bridges)                                        */
/* ------------------------------------------------------------------ */

export async function initLogTab(): Promise<void> {
  if (_initialized) {
    // Re-connect if tab re-shown
    if (!_es) connectLogStream();
    return;
  }
  _initialized = true;

  setStatus('Loading...');

  try {
    const level = getSelectedLevel();
    const params = level ? `?level=${encodeURIComponent(level)}&limit=200` : '?limit=200';
    const resp = await fetch(`${LOG_API_RECENT}${params}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = await resp.json();
    const entries: LogEntry[] = json.data ?? [];
    const container = getLogContainer();
    if (container) container.replaceChildren();
    _pendingEntries = [];
    appendEntries(entries);
  } catch {
    setStatus('Failed to load logs');
  }

  connectLogStream();
}

export function toggleLogPause(): void {
  _paused = !_paused;
  const btn = document.getElementById('logPauseBtn');
  if (btn) btn.textContent = _paused ? 'Resume' : 'Pause';
  setStatus(_paused ? 'Paused' : 'Connected');
}

export function clearLogDisplay(): void {
  _pendingEntries = [];
  const container = getLogContainer();
  if (container) container.replaceChildren();
}

function _legacyCopy(text: string): boolean {
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return !!ok;
  } catch { return false; }
}

export function copyLogDisplay(): void {
  const container = getLogContainer();
  if (!container) return;
  const lines = Array.from(container.children)
    .map(el => (el as HTMLElement).textContent ?? '')
    .join('\n');
  // navigator.clipboard requires a secure context (HTTPS or localhost). On
  // plain HTTP intranet hosts (e.g. http://pi2.local:5000) it is undefined,
  // so fall back to the legacy textarea + execCommand path.
  const onOk = () => {
    setStatus('Copied!');
    setTimeout(() => setStatus(_es ? 'Connected' : ''), 1500);
  };
  const onFail = () => setStatus('Copy failed');
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(lines).then(onOk).catch(() => {
      if (_legacyCopy(lines)) onOk(); else onFail();
    });
    return;
  }
  if (_legacyCopy(lines)) onOk(); else onFail();
}

export function downloadLogDisplay(): void {
  const container = getLogContainer();
  if (!container) return;
  const lines = Array.from(container.children)
    .map(el => (el as HTMLElement).textContent ?? '')
    .join('\n');
  const now = new Date();
  const ts = now.toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const blob = new Blob([lines], { type: 'text/plain; charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `server-log-${ts}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export function onLogLevelChange(): void {
  // Reconnect SSE with new level filter + reload recent
  _initialized = false;
  initLogTab();
}

export function onLogSearchInput(): void {
  const input = document.getElementById('logSearchInput') as HTMLInputElement | null;
  _searchText = (input?.value ?? '').toLowerCase();
  const container = getLogContainer();
  if (!container) return;
  for (const child of Array.from(container.children)) {
    const el = child as HTMLElement;
    if (!_searchText) {
      el.style.display = '';
    } else {
      el.style.display = (el.textContent?.toLowerCase().includes(_searchText)) ? '' : 'none';
    }
  }
}

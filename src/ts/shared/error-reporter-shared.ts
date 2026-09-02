import { apiUrl } from './api-base';

export type UiEventItem = {
  ts: string;
  type: string;
  target: string;
};

export type ErrorContext = {
  source?: string;
  sectionId?: string;
  action?: string;
  request?: Record<string, unknown>;
};

export type ApiFailure = {
  url: string;
  method: string;
  status: number;
  statusText: string;
  requestId?: string;
  responsePreview?: string;
  context?: ErrorContext;
};

/** A single caught-error entry stored in the session history mailbox. */
export type CaughtErrorItem = {
  id: string;           // `${Date.now()}-${Math.random().toString(36).slice(2,7)}`
  ts: string;           // ISO 8601
  component: string;    // e.g. 'qr/generateQR'
  message: string;      // err.message.slice(0, 500)
  stack?: string | undefined;       // err.stack.slice(-3000)
  detail?: Record<string, unknown> | undefined; // sanitizeDetail(detail) applied
  uiEvents: UiEventItem[];          // deep-copy snapshot
};

export type ReporterState = {
  installed: boolean;
  uiEvents: UiEventItem[];
  latestBundle: Record<string, unknown> | null;
  enrichSeq: number;
  launcherReady: boolean;
  caughtErrors: CaughtErrorItem[];
  actionsReady: boolean;
};

export const reporterState: ReporterState = {
  installed: false,
  uiEvents: [],
  latestBundle: null,
  enrichSeq: 0,
  launcherReady: false,
  caughtErrors: [],
  actionsReady: false,
};

// ── Existing ID constants ─────────────────────────────────────────────────────
export const UI_EVENT_LIMIT = 20;
export const REPORTER_STYLE_ID = 'yu-error-reporter-style';
export const LAUNCHER_ID = 'yuErrorReportLauncher';
export const MODAL_ID = 'yuErrorReportModal';
export const TEXT_ID = 'yuErrorReportText';
export const SUMMARY_ID = 'yuErrorReportSummary';
export const STATUS_ID = 'yuErrorReportStatus';
export const COUNT_ID = 'yuErrorReportCount';

// ── New constants for history mailbox ─────────────────────────────────────────
export const CAUGHT_ERROR_LIMIT   = 50;
export const HISTORY_LIST_ID      = 'yuErrorReportHistoryList';
export const HISTORY_COUNT_ID     = 'yuErrorReportHistoryCount';
export const HISTORY_TAB_BTN_ID   = 'yuErrorReportHistoryTabBtn';
export const LATEST_TAB_BTN_ID    = 'yuErrorReportLatestTabBtn';
export const LATEST_PANEL_ID      = 'yuErrorReportLatestPanel';
export const HISTORY_PANEL_ID     = 'yuErrorReportHistoryPanel';
export const COPY_ALL_BTN_ID      = 'yuErrorReportCopyAll';
export const CLEAR_HISTORY_BTN_ID = 'yuErrorReportClearHistory';
export const HISTORY_ROW_CLASS    = 'yu-error-history-row';
export const HISTORY_ROW_COPY_CLASS = 'yu-error-history-copy';

// ── i18n helper (fallback to hardcoded string when key missing) ───────────────
export function t(path: string, fallback: string): string {
  try {
    if (typeof window.tr === 'function') {
      const translated = String(window.tr(path));
      if (translated && translated !== path) return translated;
    }
  } catch {
    // ignore
  }
  return fallback;
}

export function nowIso(): string {
  return new Date().toISOString();
}

export function safeJson(value: unknown): unknown {
  if (value == null || typeof value === 'number' || typeof value === 'boolean') return value;
  if (typeof value === 'string') return value.slice(0, 600);
  if (Array.isArray(value)) return value.slice(0, 20).map(safeJson);
  if (typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(value as Record<string, unknown>).slice(0, 30)) {
      if (/token|secret|password|authorization|cookie|key|session/i.test(key)) out[key] = '***';
      else out[key] = safeJson(val);
    }
    return out;
  }
  return String(value);
}

/** Typed wrapper around safeJson for detail objects. */
export function sanitizeDetail(detail: Record<string, unknown>): Record<string, unknown> {
  return safeJson(detail) as Record<string, unknown>;
}

/** Ring-buffer push: keeps at most CAUGHT_ERROR_LIMIT entries (oldest dropped). */
export function pushCaughtError(item: CaughtErrorItem): void {
  reporterState.caughtErrors.push(item);
  if (reporterState.caughtErrors.length > CAUGHT_ERROR_LIMIT) {
    reporterState.caughtErrors.splice(0, reporterState.caughtErrors.length - CAUGHT_ERROR_LIMIT);
  }
}

/**
 * Clipboard helper with LAN HTTP fallback.
 * Pure DOM utility — no reporter state dependency.
 */
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try { await navigator.clipboard.writeText(text); return; } catch { /* fall through */ }
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch { ok = false; }
  document.body.removeChild(ta);
  if (!ok) throw new Error('clipboard copy failed');
}

/**
 * Build a yu://client-error-bundle/1 JSON object for a CaughtErrorItem.
 * Pure helper — no side-effects.
 */
export function buildCaughtBundle(item: CaughtErrorItem): Record<string, unknown> {
  return {
    schema: 'yu://client-error-bundle/1',
    captured_at: item.ts,
    app: { route: location.pathname + location.search, title: document.title },
    error: {
      kind: 'caught',
      component: item.component,
      message: item.message,
      stack: item.stack,
    },
    context: { detail: item.detail ?? {} },
    repro: { ui_events: item.uiEvents },
  };
}

export function getReasonMessage(reason: unknown): string {
  if (reason instanceof Error) return String(reason.message || '');
  if (typeof reason === 'string') return reason;
  if (typeof reason === 'object' && reason && 'message' in reason) {
    return String((reason as { message?: unknown }).message || '');
  }
  return String(reason || '');
}

export function getReasonName(reason: unknown): string {
  if (reason instanceof Error) return String(reason.name || '');
  if (typeof reason === 'object' && reason && 'name' in reason) {
    return String((reason as { name?: unknown }).name || '');
  }
  return '';
}

export function isBenignViewTransitionSkip(reason: unknown): boolean {
  if (!reason) return false;
  const name = getReasonName(reason);
  const message = getReasonMessage(reason);
  if (message !== 'Transition was skipped') return false;
  return !name || name === 'AbortError';
}

export function pushUiEvent(type: string, target: string): void {
  reporterState.uiEvents.push({
    ts: nowIso(),
    type,
    target: String(target || '').slice(0, 160),
  });
  if (reporterState.uiEvents.length > UI_EVENT_LIMIT) {
    reporterState.uiEvents.splice(0, reporterState.uiEvents.length - UI_EVENT_LIMIT);
  }
}

export function describeTarget(el: EventTarget | null): string {
  const node = el as HTMLElement | null;
  if (!node) return 'unknown';
  const action = node.closest<HTMLElement>('[data-action]')?.dataset.action;
  if (action) return `action:${action}`;
  const withId = node.closest<HTMLElement>('[id]');
  if (withId?.id) return `id:${withId.id}`;
  const name = node.getAttribute?.('name');
  if (name) return `name:${name}`;
  const cls = (node.className || '').toString().trim().split(/\s+/).filter(Boolean).slice(0, 2).join('.');
  return [node.tagName?.toLowerCase() || 'node', cls ? '.' + cls : ''].join('');
}

export async function enrichBundle(bundle: Record<string, unknown>, onEnriched: (bundle: Record<string, unknown>) => void, setStatus: (message: string) => void): Promise<void> {
  const seq = ++reporterState.enrichSeq;
  try {
    const resp = await fetch(apiUrl('/api/error-report/enrich'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ bundle }),
    });
    if (!resp.ok) return;
    const json = await resp.json() as { data?: { bundle?: Record<string, unknown> } };
    const enriched = json?.data?.bundle;
    if (!enriched || seq !== reporterState.enrichSeq) return;
    onEnriched(enriched);
    setStatus(t('error_report.enriched', 'サーバー情報を補完しました。'));
  } catch {
    // ignore enrich failure
  }
}

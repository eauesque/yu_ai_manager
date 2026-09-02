import {
  ApiFailure,
  CaughtErrorItem,
  ErrorContext,
  LAUNCHER_ID,
  MODAL_ID,
  describeTarget,
  isBenignViewTransitionSkip,
  nowIso,
  pushCaughtError,
  pushUiEvent,
  reporterState,
  sanitizeDetail,
} from './error-reporter-shared';
import { captureBundle, createBaseBundle, initReporterUi } from './error-reporter-bundle';
import { updateHistoryBadge } from './error-reporter-ui';

const UI_STALL_MS = 2500;
let _fetchWrapped = false;
let _wrappedFetch: typeof window.fetch | null = null;
let _lastFetchAt = 0;
let _lastFetch: Record<string, unknown> | null = null;
let _domObserver: MutationObserver | null = null;
let _lastDomMutationAt = 0;
let _lastDomMutation = '';

export function captureApiFailure(failure: ApiFailure): void {
  const bundle = createBaseBundle(
    'http',
    `${failure.method} ${failure.url} -> ${failure.status} ${failure.statusText}`,
    '',
    failure.context,
  );
  bundle.request = {
    url: failure.url,
    method: failure.method,
    status: failure.status,
    status_text: failure.statusText,
    request_id: failure.requestId || '',
    response_preview: String(failure.responsePreview || '').slice(0, 800),
  };
  captureBundle(bundle, '一部の読み込みに失敗しました。報告できます。');
}

export function captureThrownError(error: unknown, context?: ErrorContext): void {
  const err = error instanceof Error ? error : new Error(String(error || 'Unknown error'));
  const bundle = createBaseBundle('client', err.message || 'Unhandled client error', err.stack || '', context);
  captureBundle(bundle, '画面の一部でエラーが発生しました。報告できます。');
}

export function captureUiMismatch(actionEl: HTMLElement, startedAt: number): void {
  const action = actionEl.dataset.action || '';
  const bundle = createBaseBundle(
    'ui_mismatch',
    `Action produced no observable effect: ${action || describeTarget(actionEl)}`,
    '',
    {
      source: 'ui.stall',
      action,
      request: {
        target: describeTarget(actionEl),
        elapsed_ms: Date.now() - startedAt,
        last_fetch: _lastFetch,
        last_dom_mutation: _lastDomMutation,
      },
    },
  );
  captureBundle(bundle, '操作に反応がありません。報告できます。');
}

/**
 * Record a caught (silent) error to the session history mailbox.
 * Safe to call from any catch block — internal errors are swallowed.
 *
 * NOTE: Works correctly only after document.body exists (user-interaction phase).
 * For init-phase catch sites, readyState gating + a pre-body queue is needed
 * (out of scope for this implementation).
 */
export function reportCaughtError(
  component: string,
  error: unknown,
  detail?: Record<string, unknown>,
): void {
  try {
    const err = error instanceof Error ? error : new Error(String(error ?? 'Unknown error'));

    // Sanitize detail individually so a safeJson failure doesn't lose the main error.
    let safeDetail: Record<string, unknown> | undefined;
    if (detail) {
      try {
        safeDetail = sanitizeDetail(detail);
      } catch {
        safeDetail = { sanitize_error: 'sanitize failed' };
      }
    }

    const item: CaughtErrorItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      ts: nowIso(),
      component,
      message: err.message.slice(0, 500),
      stack: err.stack ? err.stack.slice(-3000) : undefined,
      detail: safeDetail,
      uiEvents: reporterState.uiEvents.map(e => ({ ...e })), // deep copy snapshot
    };

    pushCaughtError(item);
    updateHistoryBadge();

    console.warn(`[reportError] ${component}:`, err);
    if (safeDetail) console.warn('[reportError] detail:', safeDetail);
  } catch (metaErr) {
    try { console.warn('[reportCaughtError failed]', metaErr); } catch { /* ignore */ }
  }
}

function _isReporterNode(node: Node): boolean {
  // Duck-type instead of `instanceof Element` — MutationObserver callbacks
  // can fire in a realm where the ambient `Element` global doesn't resolve
  // to the same constructor as the node's own (observed under vitest's
  // jsdom pool), which throws ReferenceError/always-false instead of
  // correctly identifying element nodes.
  const el = typeof (node as Element).closest === 'function' ? (node as Element) : node.parentElement;
  return !!el?.closest(`#${LAUNCHER_ID}, #${MODAL_ID}`);
}

function _redactFetchUrl(url: string): string {
  try {
    const parsed = new URL(url, location.href);
    const path = `${parsed.pathname}${parsed.search ? '?[redacted]' : ''}`;
    return path.slice(0, 240);
  } catch {
    return url.split(/[?#]/, 1)[0].slice(0, 240);
  }
}

function _installFetchActivityObserver(): void {
  if (typeof window.fetch !== 'function') return;
  if (_fetchWrapped && window.fetch === _wrappedFetch) return;
  _fetchWrapped = true;
  const originalFetch = window.fetch.bind(window);
  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    const isRequest = typeof Request !== 'undefined' && input instanceof Request;
    const method = (init?.method || (isRequest ? input.method : 'GET')).toUpperCase();
    const url = isRequest ? input.url : String(input);
    _lastFetchAt = Date.now();
    _lastFetch = { method, url: _redactFetchUrl(url) };
    return originalFetch(input, init);
  }) as typeof window.fetch;
  _wrappedFetch = window.fetch;
}

function _installDomActivityObserver(): void {
  if (_domObserver || !document.body || typeof MutationObserver === 'undefined') return;
  _domObserver = new MutationObserver(records => {
    const record = records.find(r => !_isReporterNode(r.target));
    if (!record) return;
    _lastDomMutationAt = Date.now();
    _lastDomMutation = describeTarget(record.target);
  });
  _domObserver.observe(document.body, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['aria-busy', 'aria-live', 'class', 'disabled', 'hidden', 'style'],
  });
}

function _trackMaybeSilentAction(event: Event): void {
  const target = event.target as HTMLElement | null;
  const actionEl = target?.closest<HTMLElement>('[data-action]');
  if (!actionEl) return;
  const actionEvent = actionEl.dataset.actionEvent;
  if (actionEvent && actionEvent !== event.type) return;
  if (actionEl.closest(`#${LAUNCHER_ID}, #${MODAL_ID}`)) return;
  if (actionEl.dataset.noStallReport === '1') return;

  const startedAt = Date.now();
  const bundleBefore = reporterState.latestBundle;
  window.setTimeout(() => {
    if (!actionEl.isConnected) return;
    if (document.visibilityState === 'hidden') return;
    if (reporterState.latestBundle !== bundleBefore) return;
    // >= (not >): a fetch/DOM mutation triggered synchronously by the same
    // click can land on the exact same millisecond as startedAt (Date.now()
    // resolution, or frozen fake timers) — treat a tie as activity, not silence.
    if (_lastFetchAt >= startedAt || _lastDomMutationAt >= startedAt) return;
    captureUiMismatch(actionEl, startedAt);
  }, UI_STALL_MS);
}

export function installGlobalErrorReporter(): void {
  if (reporterState.installed) return;
  reporterState.installed = true;
  initReporterUi();
  _installFetchActivityObserver();
  _installDomActivityObserver();
  pushUiEvent('page_open', location.pathname + location.search);
  document.addEventListener('click', (e) => {
    pushUiEvent('click', describeTarget(e.target));
    _trackMaybeSilentAction(e);
  }, true);
  document.addEventListener('submit', (e) => {
    pushUiEvent('submit', describeTarget(e.target));
  }, true);
  window.addEventListener('error', (e) => {
    const err = e.error instanceof Error ? e.error : new Error(e.message || 'Unhandled error');
    captureThrownError(err, {
      source: 'window.error',
      action: e.filename ? `${e.filename}:${e.lineno}:${e.colno}` : '',
    });
  });
  window.addEventListener('unhandledrejection', (e) => {
    if (isBenignViewTransitionSkip(e.reason)) return;
    captureThrownError(e.reason, { source: 'window.unhandledrejection' });
  });
}

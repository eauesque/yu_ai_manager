import { showToast } from './toast';
import {
  CaughtErrorItem,
  ErrorContext,
  UiEventItem,
  copyText,
  pushCaughtError,
  reporterState,
  safeJson,
  nowIso,
  enrichBundle,
} from './error-reporter-shared';
import { ensureLauncher, renderModalBundle, setLatestBundle, setStatus, bindLauncherActions } from './error-reporter-ui';

function buildBaseBundle(kind: 'http' | 'client' | 'ui_mismatch', message: string, stack: string, context?: ErrorContext): Record<string, unknown> {
  return {
    schema: 'yu://client-error-bundle/1',
    captured_at: nowIso(),
    app: {
      route: location.pathname + location.search,
      title: document.title,
    },
    error: {
      kind,
      message: message.slice(0, 500),
      stack: String(stack || '').slice(-3000),
    },
    context: safeJson(context || {}),
    repro: {
      ui_events: reporterState.uiEvents.slice(),
    },
  };
}

function dedupeSignature(bundle: Record<string, unknown>): string {
  const req = (bundle.request || {}) as Record<string, unknown>;
  const err = (bundle.error || {}) as Record<string, unknown>;
  return [err.kind || '', req.method || '', req.url || req.path || '', err.message || ''].join('|');
}

/** Convert an auto-captured bundle (http/client) into a session-history entry. */
function bundleToCaughtErrorItem(bundle: Record<string, unknown>): CaughtErrorItem {
  const err = (bundle.error || {}) as Record<string, unknown>;
  const req = (bundle.request || {}) as Record<string, unknown>;
  const repro = (bundle.repro || {}) as Record<string, unknown>;
  const component = req.url
    ? `${String(err.kind || 'http')}:${String(req.method || '')} ${String(req.url || '')}`
    : String(err.kind || 'client');
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    ts: String(bundle.captured_at || nowIso()),
    component,
    message: String(err.message || '').slice(0, 500),
    stack: err.stack ? String(err.stack).slice(-3000) : undefined,
    detail: { ...(bundle.context as Record<string, unknown> || {}), request: req },
    uiEvents: (repro.ui_events as UiEventItem[] | undefined) || [],
  };
}

let lastSig = '';
let lastSigAt = 0;

export function captureBundle(bundle: Record<string, unknown>, toastMessage: string): void {
  const sig = dedupeSignature(bundle);
  const now = Date.now();
  if (sig && lastSig === sig && now - lastSigAt < 3000) return;
  lastSig = sig;
  lastSigAt = now;
  pushCaughtError(bundleToCaughtErrorItem(bundle));
  setLatestBundle(bundle);
  showToast(toastMessage, true);
  void enrichBundle(bundle, setLatestBundle, setStatus);
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadBundle(): Promise<void> {
  if (!reporterState.latestBundle) return;
  const json = JSON.stringify(reporterState.latestBundle, null, 2);
  const name = `${String((reporterState.latestBundle.error_id as string) || 'client-error')}.json.gz`;
  if (typeof CompressionStream !== 'undefined') {
    const stream = new Blob([json], { type: 'application/json' }).stream()
      .pipeThrough(new CompressionStream('gzip'));
    const blob = await new Response(stream, { headers: { 'Content-Type': 'application/gzip' } }).blob();
    downloadBlob(blob, name);
  } else {
    downloadBlob(new Blob([json], { type: 'application/json' }), name.replace(/\.gz$/, '.json'));
  }
}

/** Copy the latest bundle JSON to the clipboard. */
export async function copyBundle(): Promise<void> {
  if (!reporterState.latestBundle) return;
  await copyText(JSON.stringify(reporterState.latestBundle, null, 2));
}

export function buildGithubUrl(): string {
  const bundle = reporterState.latestBundle || {};
  const err = (bundle.error || {}) as Record<string, unknown>;
  const app = (bundle.app || {}) as Record<string, unknown>;
  const req = (bundle.request || {}) as Record<string, unknown>;
  const title = `[Bug] ${String(err.message || 'Client error report').slice(0, 80)}`;
  let body = '## Client Error Report\n\n';
  body += `**Version:** ${String(app.version || '(pending enrich)')}\n`;
  body += `**Route:** ${String(app.route || location.pathname)}\n`;
  body += `**Request:** ${String(req.method || '')} ${String(req.url || req.path || '')}\n\n`;
  body += '```json\n' + JSON.stringify(bundle, null, 2) + '\n```\n';
  return `https://github.com/eauesque/yu_ai_manager/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}&labels=bug`;
}

export function initReporterUi(): void {
  ensureLauncher();
  bindLauncherActions(copyBundle, downloadBundle, buildGithubUrl);
  renderModalBundle();
  const github = document.getElementById('yuErrorReportModalGithub') as HTMLAnchorElement | null;
  if (github) github.href = buildGithubUrl();
}

export function createBaseBundle(kind: 'http' | 'client' | 'ui_mismatch', message: string, stack: string, context?: ErrorContext): Record<string, unknown> {
  return buildBaseBundle(kind, message, stack, context);
}

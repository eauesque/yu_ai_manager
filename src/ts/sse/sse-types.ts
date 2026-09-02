/**
 * sse-types.ts -- SSE type definitions, constants, and EventSource guard.
 *
 * Extracted from sse-shared.ts to keep each module under 300 lines.
 */

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type SseHandler = (data: unknown) => void;

/** Known SSE event types emitted by the server. */
export type SseEventType =
  | 'scan.start'
  | 'scan.progress'
  | 'scan.complete'
  | 'scan.error'
  | 'scan.db_busy'
  | 'scan.queued'
  | 'scan.queue_next'
  | 'scan.queue_cleared'
  | 'config.scan_roots_changed'
  | 'favorite.add'
  | 'favorite.remove'
  | 'collection.create'
  | 'collection.delete'
  | 'semantic_index.start'
  | 'semantic_index.progress'
  | 'semantic_index.complete'
  | 'vlm_caption.start'
  | 'vlm_caption.progress'
  | 'vlm_caption.complete'
  | 'yolo_detect.start'
  | 'yolo_detect.progress'
  | 'yolo_detect.complete'
  | 'fpb.start'
  | 'fpb.progress'
  | 'fpb.complete'
  | 'fpb.error'
  | 'hash_backfill.progress'
  | 'hash_backfill.complete'
  | 'chatlog_reprocess.start'
  | 'chatlog_reprocess.progress'
  | 'chatlog_reprocess.complete'
  | 'chatlog_reprocess.error'
  | 'sandbox.token_revoked'
  | 'agent.killed'
  | 'agent.resumed'
  | 'agent.circuit_open'
  | 'agent.circuit_closed'
  | 'agent.circuit_half_open'
  | 'agent.budget_warning'
  | 'agent.budget_exhausted'
  | 'agent.budget_reset'
  | 'audit.secret_access'
  | 'audit.external_send'
  | 'audit.report_ready'
  | 'audit.rule_gap_detected'
  | 's2t.batch_start'
  | 's2t.batch_progress'
  | 's2t.batch_complete'
  | 's2t.stream_start'
  | 's2t.stream_chunk'
  | 's2t.stream_final'
  | 's2t.stream_interim'
  | 's2t.stream_complete'
  | 's2t.stream_error'
  | 'scheduler.job_executed'
  | 'scheduler.job_error'
  | 'github_queue.new_issues'
  | 'github_queue.triage_complete'
  | 'github_queue.dismissed'
  | 'bsky_queue.new_notifications'
  | 'bsky_queue.triage_complete'
  | 'bsky_queue.auto_responded'
  | 'update.progress'
  | 'update.complete'
  | 'peer.pairing_request'
  | 'peer.token_revoked'
  | 'peer.auth_lost'
  | 'fleet.consent_request'
  | (string & {});  // allow arbitrary strings but offer autocomplete

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

export const SSE_FALLBACK_URL = '/api/events/stream';
export const SSE_INFO_URL = '/api/events/info';
export const BACKOFF_INITIAL_MS = 1_000;
export const BACKOFF_MAX_MS = 30_000;

/* ------------------------------------------------------------------ */
/*  EventSource guard                                                  */
/* ------------------------------------------------------------------ */

// IMPORTANT: this module is sometimes duplicated across esbuild chunks
// (different entry points pull it independently). Without idempotency the
// second copy would observe `window.EventSource` already replaced by the
// first copy's Proxy and capture the Proxy itself as
// `_NativeEventSource` — every shared SSE connection would then throw with
// "[SSE] new EventSource() is not allowed" the first time the module
// instantiates the constructor it thought was native. We stash the
// original constructor on `window` once and re-use it on subsequent
// module loads, and we only install the Proxy when none is present yet.

interface SSEGuardWindow {
  __yuNativeEventSource?: typeof EventSource;
  __yuEventSourceGuardInstalled?: boolean;
}

const _guardWin = window as Window & SSEGuardWindow;

if (!_guardWin.__yuNativeEventSource) {
  _guardWin.__yuNativeEventSource = window.EventSource;
}

// Exported for modules that need a dedicated EventSource (e.g. log stream).
export const _NativeEventSource = _guardWin.__yuNativeEventSource;

if (!_guardWin.__yuEventSourceGuardInstalled) {
  _guardWin.__yuEventSourceGuardInstalled = true;
  // Replace window.EventSource so that direct usage throws an error.
  // Extensions and other modules must use sseSubscribe() instead.
  window.EventSource = new Proxy(_NativeEventSource, {
    construct(_target, args) {
      const url = args[0];
      throw new Error(
        `[SSE] new EventSource() is not allowed. ` +
        `Use window.sseSubscribe(eventType, handler) instead. ` +
        `Attempted URL: ${url}`
      );
    },
  });
}

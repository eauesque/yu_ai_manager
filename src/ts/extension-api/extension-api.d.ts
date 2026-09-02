/**
 * YU AI Manager — Extension API Type Definitions
 *
 * Usage (in your extension's TypeScript):
 *
 *   /// <reference types="yu-api" />
 *   import { showToast, sseSubscribe, tr, apiFetch } from 'yu-api';
 *
 * Or copy this file into your project as a local .d.ts.
 *
 * API Version: 1
 */

declare module 'yu-api' {
  /* ------------------------------------------------------------------ */
  /*  Toast                                                              */
  /* ------------------------------------------------------------------ */

  /**
   * Show a toast notification.
   * @param message - Text to display.
   * @param isError - If true, the toast uses error styling and a longer duration.
   */
  export function showToast(message: string, isError?: boolean): void;

  /* ------------------------------------------------------------------ */
  /*  SSE (Server-Sent Events)                                           */
  /* ------------------------------------------------------------------ */

  /** Callback signature for SSE event handlers. */
  export type SseHandler = (data: unknown) => void;

  /**
   * Known SSE event types emitted by the server.
   * Arbitrary strings are also accepted for custom events.
   */
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
    | (string & {});

  /**
   * Subscribe to a named SSE event type.
   * The shared SSE connection is established lazily on first subscriber.
   * @param eventType - The event type to listen for.
   * @param handler - Callback invoked with parsed event data.
   */
  export function sseSubscribe(eventType: SseEventType, handler: SseHandler): void;

  /**
   * Unsubscribe a handler from a named SSE event type.
   * If no subscribers remain, the shared connection is closed.
   * @param eventType - The event type to stop listening for.
   * @param handler - The previously registered callback.
   */
  export function sseUnsubscribe(eventType: SseEventType, handler: SseHandler): void;

  /* ------------------------------------------------------------------ */
  /*  i18n                                                               */
  /* ------------------------------------------------------------------ */

  /**
   * Translate an i18n key to the current UI language.
   * @param path - Dot-separated key path (e.g. "settings.title").
   * @param a - Fallback string, or interpolation variables object.
   * @param b - Fallback string if `a` is an interpolation object.
   * @returns The translated string, or fallback, or the key path itself.
   */
  export function tr(path: string, a?: unknown, b?: unknown): string;

  /* ------------------------------------------------------------------ */
  /*  API Fetch                                                          */
  /* ------------------------------------------------------------------ */

  /**
   * Build a full API URL from a relative path.
   * Respects the `apiBase` localStorage override for file:// protocol.
   * @param path - Relative API path (e.g. "/api/files").
   */
  export function apiUrl(path: string): string;

  /**
   * Fetch wrapper with CSRF header injection and error handling.
   * Automatically adds `X-Requested-With: XMLHttpRequest`.
   * Throws on non-2xx responses with a translated error message.
   * @param path - Relative API path (e.g. "/api/files").
   * @param opts - Standard RequestInit options.
   */
  export function apiFetch(path: string, opts?: RequestInit): Promise<Response>;

  /* ------------------------------------------------------------------ */
  /*  HTML Utilities                                                     */
  /* ------------------------------------------------------------------ */

  /**
   * Escape HTML special characters to prevent XSS.
   * @param text - Raw text to escape. Non-string values are coerced via String().
   */
  export function escapeHtml(text: unknown): string;
}

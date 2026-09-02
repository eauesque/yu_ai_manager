/**
 * Extension API v1 — Public module interface for extensions.
 *
 * New extensions using `"script_type": "module"` in extension.json
 * can import from this bundle via Import Maps:
 *
 *   import { showToast, sseSubscribe, tr, apiFetch } from 'yu-api';
 *
 * Legacy extensions using classic `<script>` tags continue to use
 * the window.* globals (showToast, sseSubscribe, etc.) as before.
 *
 * This module re-exports the canonical implementations from the
 * internal codebase.  It is the ONLY public contract for extensions.
 */

// --- Toast ---
export { showToast } from '../main/main';

// --- SSE ---
export { sseSubscribe, sseUnsubscribe } from '../sse/sse-shared';
export type { SseHandler, SseEventType } from '../sse/sse-types';

// --- i18n ---
export { tr } from '../main/adaptive-runtime-i18n';

// --- Fetch / HTML ---
export { apiFetch, apiUrl, escapeHtml } from '../main/api-utils';

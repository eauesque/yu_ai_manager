/**
 * Window bridge for the shared extension-health renderer.
 *
 * Installs ``window.extensionHealthApi`` so inline scripts in extension
 * templates (Tools page Hailo panels, etc.) can render the unified health
 * badge without re-implementing the rendering logic.
 *
 * Both ``apps/extensions-app.ts`` and ``apps/tools-app.ts`` import this
 * module so the API is available on the page the user is viewing.
 *
 * Security: the rendered HTML strings are produced by extension-health.ts
 * which HTML-escapes every dynamic value (see _esc() in that module), so
 * assigning the result to innerHTML below is safe by construction.
 */

import { installWindowApi } from './window-api';
import {
  type HealthInfo,
  healthReasonText,
  healthVerdict,
  renderHealthBadge,
  renderHealthDetails,
} from './extension-health';

/** Fetch /api/extensions and return the health entry for ``extensionName``. */
async function fetchHealth(extensionName: string): Promise<HealthInfo | null> {
  const res = await fetch('/api/extensions', { credentials: 'same-origin' });
  if (!res.ok) return null;
  const data = await res.json();
  const list = Array.isArray(data.extensions) ? data.extensions : [];
  for (const ext of list) {
    if (ext?.name === extensionName) return (ext.health as HealthInfo | null) || null;
  }
  return null;
}

/**
 * Fetch and render unified health into ``#${targetId}`` (innerHTML).
 *
 * @param targetId  DOM id of the container element.
 * @param extensionName  Manifest name (e.g. "builtin-hailo-semantic-search").
 * @param mode  "badge" for compact inline badge, "details" for the full block.
 */
async function renderInto(
  targetId: string,
  extensionName: string,
  mode: 'badge' | 'details' = 'details',
): Promise<void> {
  const el = document.getElementById(targetId);
  if (!el) return;
  try {
    const health = await fetchHealth(extensionName);
    // Safe: render helpers escape every dynamic value (see _esc in extension-health.ts).
    el.innerHTML = mode === 'badge' ? renderHealthBadge(health) : renderHealthDetails(health);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    // Safe: span structure is static; only msg is dynamic and assigned via textContent below.
    el.textContent = `health fetch failed: ${msg}`;
  }
}

installWindowApi('extensionHealthApi', {
  renderHealthBadge,
  renderHealthDetails,
  healthReasonText,
  healthVerdict,
  fetchHealth,
  renderInto,
});

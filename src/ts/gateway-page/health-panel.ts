/**
 * health-panel.ts -- 10-second polling of /api/gateway/local/status.
 * All API response strings rendered via innerHTML are sanitized with escapeHtml().
 */
import { apiFetch, escapeHtml } from '../main/api-utils';

const STATE_CLASS: Record<string, string> = {
  running: 'dot-green',
  stopped: 'dot-red',
  unknown: 'dot-gray',
};

export function initHealthPanel(): void {
  void _poll();
  setInterval(() => { void _poll(); }, 10_000);
}

async function _poll(): Promise<void> {
  try {
    const resp = await apiFetch('/api/gateway/local/status');
    if (!resp.ok) return;
    const { backends } = (await resp.json()) as {
      backends: Array<{ id: string; type: string; base_url: string; state: string }>;
    };
    const el = document.getElementById('gw-health-list');
    if (!el) return;
    if (!backends.length) {
      el.textContent = '-';
      return;
    }
    el.innerHTML = backends.map(b => {
      const cls = escapeHtml(STATE_CLASS[b.state] ?? STATE_CLASS.unknown);
      const typeStr = escapeHtml(b.type);
      const urlStr = escapeHtml(b.base_url);
      return `<div class="row gap-2 align-center">
        <span class="dot ${cls}">&#9679;</span>
        <span>${typeStr}</span>
        <span class="muted">${urlStr}</span>
      </div>`;
    }).join('');
  } catch {
    // Ignore network errors.
  }
}

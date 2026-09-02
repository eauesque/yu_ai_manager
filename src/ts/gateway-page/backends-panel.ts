/**
 * backends-panel.ts -- backend list, add form, delete.
 * All API response strings rendered via innerHTML are sanitized with escapeHtml().
 */
import { apiFetch, escapeHtml } from '../main/api-utils';
import { getAppApi } from '../shared/browser-apis';
import { customAlert } from '../shared/dialog';
import { mutationHeaders } from '../shared/gateway-auth';

interface BackendEntry {
  id: string;
  type: string;
  base_url: string;
  status: 'running' | 'stopped' | 'unknown';
}

const STATE_CLASS: Record<string, string> = {
  running: 'dot-green',
  stopped: 'dot-red',
  unknown: 'dot-gray',
};

let _registeredPorts = new Set<number>();

export function getRegisteredPorts(): Set<number> {
  return _registeredPorts;
}

function _portFromUrl(base_url: string): number | null {
  try {
    const p = parseInt(new URL(base_url).port, 10);
    return Number.isFinite(p) && p > 0 ? p : null;
  } catch {
    return null;
  }
}

export async function loadBackends(): Promise<void> {
  const resp = await apiFetch('/api/gateway/backends');
  if (!resp.ok) return;
  const { backends } = (await resp.json()) as { backends: BackendEntry[] };
  _renderList(backends);
}

function _renderList(backends: BackendEntry[]): void {
  _registeredPorts = new Set(
    backends.map(b => _portFromUrl(b.base_url)).filter((p): p is number => p !== null)
  );

  const el = document.getElementById('gw-backends-list');
  if (!el) return;
  if (!backends.length) {
    const p = document.createElement('p');
    p.className = 'muted';
    p.textContent = getAppApi().tr('gateway.no_backends', 'No backends');
    el.replaceChildren(p);
    return;
  }
  // All user-data values escaped before innerHTML insertion.
  const rows = backends.map(b => {
    const stateClass = escapeHtml(STATE_CLASS[b.status] ?? STATE_CLASS.unknown);
    const typeText = escapeHtml(b.type);
    const urlText = escapeHtml(b.base_url);
    const idAttr = escapeHtml(b.id);
    return `<tr data-backend-id="${idAttr}">
      <td>${typeText}</td>
      <td>${urlText}</td>
      <td><span class="dot ${stateClass}">&#9679;</span></td>
      <td><button class="btn-icon" data-action="delete-backend"
                  data-id="${idAttr}" aria-label="${escapeHtml(getAppApi().tr('gateway.col_actions', 'Actions'))}">&#x1F5D1;</button></td>
    </tr>`;
  }).join('');
  el.innerHTML = `<table class="table"><thead><tr>
    <th>${escapeHtml(getAppApi().tr('gateway.col_type', 'Type'))}</th>
    <th>URL</th>
    <th>${escapeHtml(getAppApi().tr('gateway.col_state', 'Status'))}</th>
    <th></th>
  </tr></thead><tbody>${rows}</tbody></table>`;
}

export function initBackendsPanel(): void {
  void loadBackends();

  document.getElementById('gw-add-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget as HTMLFormElement;
    const type = (form.querySelector('#gw-add-type') as HTMLSelectElement).value;
    const port = parseInt((form.querySelector('#gw-add-port') as HTMLInputElement).value, 10);
    try {
      await apiFetch('/api/gateway/backends', {
        method: 'POST',
        headers: await mutationHeaders(),
        body: JSON.stringify({ type, port }),
      });
      (form.querySelector('#gw-add-port') as HTMLInputElement).value = '';
      await loadBackends();
    } catch (err) {
      void customAlert(err instanceof Error ? err.message : getAppApi().tr('gateway.error_add', 'An error occurred'));
    }
  });

  document.getElementById('gw-backends-list')?.addEventListener('click', async (e) => {
    const btn = (e.target as HTMLElement).closest('[data-action="delete-backend"]') as HTMLElement | null;
    if (!btn) return;
    const id = btn.dataset.id ?? '';
    if (!id) return;
    const resp = await apiFetch(`/api/gateway/backends/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: await mutationHeaders(),
    });
    if (resp.ok) await loadBackends();
  });
}

export { loadBackends as refreshBackends };

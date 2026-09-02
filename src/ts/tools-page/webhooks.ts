/**
 * tools-page/webhooks.ts — Webhook management UI.
 *
 * Lists webhooks, allows adding/deleting/testing from the Tools page.
 */

import { apiFetch } from './api';
import { getAppApi } from '../shared/browser-apis';

interface Webhook {
  id: string;
  url: string;
  events: string[];
  active: boolean;
  label?: string;
}

function _esc(s: string): string {
  return getAppApi().escapeHtml(s);
}

async function loadWebhooks(): Promise<void> {
  const list = document.getElementById('webhookList');
  if (!list) return;
  try {
    const res = await apiFetch('/api/webhooks');
    const json = await res.json();
    const data = json.data ?? json;
    const webhooks: Webhook[] = data.webhooks ?? [];
    if (webhooks.length === 0) {
      list.textContent = 'No webhooks configured';
      list.style.color = 'var(--muted)';
      return;
    }
    list.textContent = '';
    list.style.color = '';
    webhooks.forEach(wh => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:6px;padding:4px 0;border-bottom:1px solid var(--border,#333);';

      const url = document.createElement('span');
      url.style.cssText = 'flex:1;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
      url.textContent = wh.url;
      url.title = wh.url;

      const events = document.createElement('span');
      events.style.cssText = 'font-size:10px;color:var(--muted);';
      events.textContent = (wh.events || []).join(', ') || '*';

      const testBtn = document.createElement('button');
      testBtn.className = 'btn btn-sm';
      testBtn.textContent = 'Test';
      testBtn.style.cssText = 'font-size:10px;padding:2px 6px;';
      testBtn.addEventListener('click', async () => {
        try {
          await apiFetch(`/api/webhooks/${wh.id}/test`, { method: 'POST' });
          testBtn.textContent = '\u2713';
          setTimeout(() => { testBtn.textContent = 'Test'; }, 1500);
        } catch { testBtn.textContent = '\u2717'; }
      });

      const delBtn = document.createElement('button');
      delBtn.className = 'btn btn-sm';
      delBtn.textContent = '\u00d7';
      delBtn.style.cssText = 'font-size:12px;padding:2px 6px;color:#e74c3c;';
      delBtn.addEventListener('click', async () => {
        if (!confirm('Delete this webhook?')) return;
        try {
          await apiFetch(`/api/webhooks/${wh.id}`, { method: 'DELETE' });
          loadWebhooks();
        } catch {
          delBtn.textContent = 'Error';
          setTimeout(() => { delBtn.textContent = '\u00d7'; }, 1500);
        }
      });

      row.appendChild(url);
      row.appendChild(events);
      row.appendChild(testBtn);
      row.appendChild(delBtn);
      list.appendChild(row);
    });
  } catch {
    list.textContent = 'Failed to load webhooks';
    list.style.color = '#e74c3c';
  }
}

function initWebhookAdd(): void {
  const btn = document.getElementById('webhookAddBtn');
  const input = document.getElementById('webhookUrlInput') as HTMLInputElement | null;
  if (!btn || !input) return;
  btn.addEventListener('click', async () => {
    const url = input.value.trim();
    if (!url) return;
    try {
      await apiFetch('/api/webhooks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, events: ['*'] }),
      });
      input.value = '';
      loadWebhooks();
    } catch (e) {
      console.error('Failed to add webhook:', e);
    }
  });
}

// Init on DOMContentLoaded
if (document.getElementById('webhookCard')) {
  loadWebhooks();
  initWebhookAdd();
}

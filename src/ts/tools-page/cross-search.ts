/**
 * cross-search.ts -- Cross-text search (MD + Chat + Prompt).
 * Calls GET /ext/chatlog/api/text-search
 */

import { apiFetch } from './api';

function _esc(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

interface CrossSearchResult {
  type: string;
  id: number;
  title?: string;
  path?: string;
  snippet?: string;
  score?: number;
  role?: string;
  source?: string;
  conversation_id?: number;
}

export async function crossSearch(): Promise<void> {
  const queryEl = document.getElementById('crossSearchQuery') as HTMLInputElement | null;
  const resultEl = document.getElementById('crossSearchResult');
  if (!queryEl || !resultEl) return;

  const q = queryEl.value.trim();
  if (!q) return;

  const targets: string[] = [];
  if ((document.getElementById('crossSearchMd') as HTMLInputElement | null)?.checked) targets.push('md');
  if ((document.getElementById('crossSearchChat') as HTMLInputElement | null)?.checked) targets.push('chat');
  if ((document.getElementById('crossSearchPrompt') as HTMLInputElement | null)?.checked) targets.push('prompt');

  if (!targets.length) {
    resultEl.innerHTML = '<p style="color:var(--muted,#888)">Select at least one target</p>';
    return;
  }

  resultEl.innerHTML = '<span style="color:var(--muted,#888)">Searching...</span>';

  try {
    const params = new URLSearchParams({ q, target: targets.join(','), limit: '50' });
    const res = await apiFetch(`/ext/chatlog/api/text-search?${params}`);
    const d = await res.json();
    const data = d.data ?? d;
    const results: CrossSearchResult[] = data.results ?? [];

    if (!results.length) {
      resultEl.innerHTML = '<p style="color:var(--muted,#888)">No results found</p>';
      return;
    }

    const typeLabel: Record<string, string> = { md: 'MD', chat: 'Chat', prompt: 'Prompt' };
    const typeColor: Record<string, string> = {
      md: 'rgba(59,130,246,0.15);color:#3b82f6',
      chat: 'rgba(16,185,129,0.15);color:#10b981',
      prompt: 'rgba(245,158,11,0.15);color:#f59e0b',
    };

    let html = `<div style="margin-bottom:6px;font-size:12px;color:var(--muted,#888)">${results.length} results</div>`;
    for (const r of results) {
      const badge = `<span style="display:inline-block;padding:1px 6px;border-radius:4px;font-size:11px;font-weight:600;background:${typeColor[r.type] || 'rgba(128,128,128,0.2);color:#888'}">${typeLabel[r.type] || r.type}</span>`;
      const title = r.title || r.path || `#${r.id}`;
      const snippet = _esc(r.snippet || '');
      html += `<div style="padding:8px 0;border-bottom:1px solid var(--border,#333);">
        <div style="display:flex;gap:6px;align-items:center;">${badge} <strong style="font-size:13px;">${_esc(title)}</strong></div>
        <div style="font-size:12px;color:var(--muted,#aaa);margin-top:2px;line-height:1.4;">${snippet}</div>
      </div>`;
    }
    resultEl.innerHTML = html;
  } catch (err) {
    resultEl.innerHTML = `<p style="color:#ef4444">${_esc(err instanceof Error ? err.message : String(err))}</p>`;
  }
}

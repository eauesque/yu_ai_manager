/**
 * tools-page/chatlog-search.ts — Chat log search and browse UI.
 */

import { apiFetch } from './api';
import { getAppApi } from '../shared/browser-apis';

interface Conversation {
  id: number;
  title?: string;
  source?: string;
  model?: string;
  message_count?: number;
  created_at?: string;
}

interface SearchResult {
  conversation_id: number;
  conversation_title?: string;
  role?: string;
  content?: string;
  score?: number;
}

function _esc(s: string): string {
  return getAppApi().escapeHtml(s);
}

async function loadChatlogStats(): Promise<void> {
  const el = document.getElementById('chatlogStats');
  if (!el) return;
  try {
    const res = await apiFetch('/ext/chatlog/api/stats');
    const json = await res.json();
    const data = json.data ?? json;
    const total = data.total_conversations ?? 0;
    const messages = data.total_messages ?? 0;
    el.textContent = `${total} conversations, ${messages} messages`;
  } catch {
    el.textContent = 'Chat log extension not available';
  }
}

async function searchChatlogs(query: string): Promise<void> {
  const results = document.getElementById('chatlogResults');
  if (!results) return;

  if (!query) {
    // Show recent conversations
    try {
      const res = await apiFetch('/ext/chatlog/api/conversations?limit=20');
      const json = await res.json();
      const data = json.data ?? json;
      const convs: Conversation[] = data.conversations ?? [];
      renderConversations(results, convs);
    } catch {
      results.textContent = 'Failed to load conversations';
      results.style.color = '#e74c3c';
    }
    return;
  }

  try {
    const res = await apiFetch(`/ext/chatlog/api/search?q=${encodeURIComponent(query)}&limit=20`);
    const json = await res.json();
    const data = json.data ?? json;
    const items: SearchResult[] = data.results ?? [];
    if (items.length === 0) {
      results.textContent = 'No results found';
      results.style.color = 'var(--muted)';
      return;
    }
    results.textContent = '';
    results.style.color = '';
    items.forEach(item => {
      const row = document.createElement('div');
      row.style.cssText = 'padding:6px 0;border-bottom:1px solid var(--border,#333);';

      const header = document.createElement('div');
      header.style.cssText = 'font-size:12px;font-weight:600;margin-bottom:2px;';
      header.textContent = item.conversation_title || `Conversation #${item.conversation_id}`;
      if (item.role) {
        const badge = document.createElement('span');
        badge.style.cssText = 'font-size:10px;padding:1px 4px;border-radius:3px;margin-left:6px;background:rgba(128,128,128,0.15);color:var(--muted);';
        badge.textContent = item.role;
        header.appendChild(badge);
      }

      const content = document.createElement('div');
      content.style.cssText = 'font-size:11px;color:var(--muted);max-height:3em;overflow:hidden;';
      content.textContent = (item.content || '').substring(0, 200);

      row.appendChild(header);
      row.appendChild(content);
      results.appendChild(row);
    });
  } catch {
    results.textContent = 'Search failed';
    results.style.color = '#e74c3c';
  }
}

function renderConversations(container: HTMLElement, convs: Conversation[]): void {
  if (convs.length === 0) {
    container.textContent = 'No conversations';
    container.style.color = 'var(--muted)';
    return;
  }
  container.textContent = '';
  container.style.color = '';
  convs.forEach(c => {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--border,#333);';

    const title = document.createElement('span');
    title.style.cssText = 'flex:1;font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
    title.textContent = c.title || `#${c.id}`;

    const meta = document.createElement('span');
    meta.style.cssText = 'font-size:10px;color:var(--muted);white-space:nowrap;';
    const parts: string[] = [];
    if (c.source) parts.push(c.source);
    if (c.model) parts.push(c.model);
    if (c.message_count) parts.push(`${c.message_count} msgs`);
    meta.textContent = parts.join(' | ');

    row.appendChild(title);
    row.appendChild(meta);
    container.appendChild(row);
  });
}

function initChatlogSearch(): void {
  const btn = document.getElementById('chatlogSearchBtn');
  const input = document.getElementById('chatlogQuery') as HTMLInputElement | null;
  if (!btn || !input) return;

  const doSearch = () => searchChatlogs(input.value.trim());
  btn.addEventListener('click', doSearch);
  input.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') doSearch();
  });

  // Load stats and recent conversations on init
  loadChatlogStats();
  searchChatlogs('');
}

if (document.getElementById('chatlogCard')) {
  initChatlogSearch();
}

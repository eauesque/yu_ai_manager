const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

type ScopeSession = { preset?: string; name?: string; denied_count?: number };

function formatScopeDetail(scope: ScopeSession | undefined): string {
  if (!scope || typeof scope !== 'object') return '';
  const parts: string[] = [];
  if (scope.preset) parts.push(`preset=${scope.preset}`);
  if (scope.name) parts.push(`name=${scope.name}`);
  if (typeof scope.denied_count === 'number') parts.push(`denied=${scope.denied_count}`);
  return parts.join(' / ').substring(0, 80);
}

export async function loadScopes(): Promise<void> {
  const section = document.getElementById('ajScopeSection');
  const content = document.getElementById('ajScopeContent');
  if (!section || !content) return;
  try {
    const res = await fetch('/api/agent/scope');
    const json = await res.json();
    const data = json.data ?? json;
    const sessions: Record<string, ScopeSession> =
      (data && typeof data === 'object' && data.sessions && typeof data.sessions === 'object')
        ? data.sessions
        : {};
    const keys = Object.keys(sessions);
    section.style.display = '';
    content.textContent = '';
    const tr = typeof window.tr === 'function' ? window.tr : (_k: string, fb: string) => fb;
    if (keys.length === 0) {
      const p = document.createElement('p');
      p.style.cssText = 'font-size:12px;color:var(--muted,#888);margin:4px 0 0;';
      const defaultPreset = data && typeof data.default_preset === 'string' ? data.default_preset : '';
      p.textContent = defaultPreset
        ? `${tr('agent_journal.scopes_empty_with_default', '（アクティブなセッションスコープなし — 既定プリセット: ')}${defaultPreset}）`
        : tr('agent_journal.scopes_empty', '（スコープ未設定 = 無制限）');
      content.appendChild(p);
      return;
    }
    keys.forEach((sid) => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--border,#333);';
      const label = document.createElement('span');
      label.style.cssText = 'font-family:monospace;font-size:11px;color:var(--muted);flex:0 0 auto;max-width:50%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
      label.textContent = sid;
      const detail = document.createElement('span');
      detail.style.cssText = 'font-size:11px;color:var(--muted);flex:1;';
      detail.textContent = formatScopeDetail(sessions[sid]);
      const delBtn = document.createElement('button');
      delBtn.className = 'aj-cb-reset-btn';
      delBtn.textContent = '×';
      delBtn.title = tr('agent_journal.scope_delete', 'スコープを削除');
      delBtn.addEventListener('click', async () => {
        await fetch(`/api/agent/scope/${encodeURIComponent(sid)}`, { method: 'DELETE', headers: XHR_HEADERS });
        loadScopes();
      });
      row.append(label, detail, delBtn);
      content.appendChild(row);
    });
  } catch {
    section.style.display = 'none';
  }
}

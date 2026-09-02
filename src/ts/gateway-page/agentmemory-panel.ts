/**
 * agentmemory-panel.ts -- polls /agentmemory/livez every 10s and updates the status card.
 */

const DOT_CLASS: Record<string, string> = {
  running: 'dot-green',
  stopped: 'dot-red',
  unknown: 'dot-gray',
};

export function initAgentmemoryPanel(): void {
  const urlEl = document.getElementById('gw-am-url');
  if (urlEl) urlEl.textContent = window.location.origin + '/agentmemory';
  void _poll();
  setInterval(() => { void _poll(); }, 10_000);
  void _loadConfig();
  document.getElementById('gw-am-save')?.addEventListener('click', () => { void _saveConfig(); });
}

async function _loadConfig(): Promise<void> {
  try {
    const resp = await fetch('/api/gateway/agentmemory/config', { cache: 'no-store' });
    if (!resp.ok) return;
    const data = await resp.json() as { base_url: string };
    const input = document.getElementById('gw-am-base-url') as HTMLInputElement | null;
    if (input) input.value = data.base_url;
  } catch { /* ignore */ }
}

async function _saveConfig(): Promise<void> {
  const input = document.getElementById('gw-am-base-url') as HTMLInputElement | null;
  const msg = document.getElementById('gw-am-save-msg');
  if (!input) return;
  try {
    const resp = await fetch('/api/gateway/agentmemory/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url: input.value.trim() }),
    });
    const data = await resp.json() as { base_url?: string; error?: string };
    if (resp.ok) {
      if (msg) msg.textContent = (window as any).__i18n?.t('gateway.agentmemory_save_ok') ?? '保存しました';
      void _poll();
    } else {
      if (msg) msg.textContent = data.error ?? ((window as any).__i18n?.t('gateway.agentmemory_save_err') ?? 'エラー');
    }
  } catch {
    if (msg) msg.textContent = (window as any).__i18n?.t('gateway.agentmemory_save_err') ?? 'エラー';
  }
}

async function _poll(): Promise<void> {
  const dot = document.getElementById('gw-am-dot');
  const label = document.getElementById('gw-am-label');
  if (!dot || !label) return;
  try {
    const resp = await fetch('/agentmemory/livez', { cache: 'no-store' });
    const state = resp.ok ? 'running' : 'stopped';
    _apply(dot, label, state);
  } catch {
    _apply(dot, label, 'stopped');
  }
}

function _apply(dot: HTMLElement, label: HTMLElement, state: string): void {
  const prev = Object.values(DOT_CLASS);
  prev.forEach(c => dot.classList.remove(c));
  dot.classList.add(DOT_CLASS[state] ?? DOT_CLASS.unknown);
  const text: Record<string, string> = {
    running: 'オンライン',
    stopped: 'オフライン',
    unknown: '不明',
  };
  label.textContent = text[state] ?? text.unknown;
}

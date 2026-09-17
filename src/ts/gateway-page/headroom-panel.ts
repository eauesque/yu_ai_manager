/**
 * headroom-panel.ts -- gateway page headroom section
 */

const DOT_CLASS: Record<string, string> = {
  running: 'dot-green',
  stopped: 'dot-red',
  unknown: 'dot-gray',
};

export function initHeadroomPanel(): void {
  void _poll();
  setInterval(() => { void _poll(); }, 10_000);
  void _loadConfig();
  document.getElementById('gw-hr-save')?.addEventListener('click', () => { void _saveConfig(); });
}

async function _poll(): Promise<void> {
  const dot = document.getElementById('gw-hr-dot');
  const label = document.getElementById('gw-hr-label');
  if (!dot || !label) return;
  try {
    const resp = await fetch('/api/headroom/health', { cache: 'no-store' });
    const state = resp.ok ? 'running' : 'stopped';
    _apply(dot, label, state);
  } catch {
    _apply(dot, label, 'stopped');
  }
}

function _apply(dot: HTMLElement, label: HTMLElement, state: string): void {
  Object.values(DOT_CLASS).forEach(c => dot.classList.remove(c));
  dot.classList.add(DOT_CLASS[state] ?? DOT_CLASS.unknown);
  const text: Record<string, string> = {
    running: 'オンライン',
    stopped: 'オフライン',
    unknown: '不明',
  };
  label.textContent = text[state] ?? text.unknown;
}

async function _loadConfig(): Promise<void> {
  try {
    const resp = await fetch('/api/gateway/headroom/config', { cache: 'no-store' });
    if (!resp.ok) return;
    const data = await resp.json() as { base_url: string; auth_key: string };
    const urlInput = document.getElementById('gw-hr-base-url') as HTMLInputElement | null;
    if (urlInput) urlInput.value = data.base_url;
    const keyInput = document.getElementById('gw-hr-auth-key') as HTMLInputElement | null;
    if (keyInput) keyInput.value = data.auth_key ?? '';
    const urlEl = document.getElementById('gw-hr-url');
    if (urlEl) urlEl.textContent = data.base_url;
  } catch { /* ignore */ }
}

async function _saveConfig(): Promise<void> {
  const urlInput = document.getElementById('gw-hr-base-url') as HTMLInputElement | null;
  const keyInput = document.getElementById('gw-hr-auth-key') as HTMLInputElement | null;
  const msg = document.getElementById('gw-hr-save-msg');
  if (!urlInput) return;
  try {
    const resp = await fetch('/api/gateway/headroom/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_url: urlInput.value.trim(),
        auth_key: keyInput?.value.trim() ?? '',
      }),
    });
    const data = await resp.json() as { base_url?: string; auth_key?: string; error?: string };
    if (resp.ok) {
      if (msg) msg.textContent = (window as any).__i18n?.t('gateway.headroom_save_ok') ?? '保存しました';
      const urlEl = document.getElementById('gw-hr-url');
      if (urlEl && data.base_url) urlEl.textContent = data.base_url;
      void _poll();
    } else {
      if (msg) msg.textContent = data.error ?? ((window as any).__i18n?.t('gateway.headroom_save_err') ?? 'エラー');
    }
  } catch {
    if (msg) msg.textContent = (window as any).__i18n?.t('gateway.headroom_save_err') ?? 'エラー';
  }
}

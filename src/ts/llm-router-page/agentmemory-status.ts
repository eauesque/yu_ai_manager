/**
 * agentmemory-status.ts -- polls /agentmemory/livez and updates the status indicator
 * on the LLM Router page.
 */

export function initLrAgentmemoryStatus(): void {
  const urlEl = document.getElementById('lrAmUrl');
  if (urlEl) urlEl.textContent = window.location.origin + '/agentmemory';
  void _poll();
  setInterval(() => { void _poll(); }, 15_000);
}

async function _poll(): Promise<void> {
  const dot = document.getElementById('lrAmDot');
  if (!dot) return;
  try {
    const resp = await fetch('/agentmemory/livez', { cache: 'no-store' });
    _setDot(dot, resp.ok ? 'running' : 'stopped');
  } catch {
    _setDot(dot, 'stopped');
  }
}

function _setDot(dot: HTMLElement, state: 'running' | 'stopped'): void {
  dot.classList.remove('dot-green', 'dot-red', 'dot-gray');
  dot.classList.add(state === 'running' ? 'dot-green' : 'dot-red');
}

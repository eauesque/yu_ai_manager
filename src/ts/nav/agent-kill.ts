/**
 * agent-kill.ts -- Agent Kill Switch + Circuit Breaker navbar button control.
 *
 * - Fetches initial state via GET /api/agent/status
 * - Click -> confirm -> POST /api/agent/kill or /api/agent/resume
 * - Real-time sync via SSE: agent.killed / agent.resumed / agent.circuit_open / agent.circuit_closed
 */

import { sseSubscribe } from '../sse';

const ICON_STOP = '<svg class="agent-kill-icon agent-kill-icon--stop" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path class="agent-kill-icon__plate" d="M9.05 2.75h5.9l4.3 4.3v5.9l-4.3 4.3h-5.9l-4.3-4.3v-5.9z"/><path class="agent-kill-icon__bolt" d="M12.8 5.75 8.4 12h3.05l-.35 6.25 4.55-7.15h-3.1z"/><path class="agent-kill-icon__stop" d="M8.15 19.15h7.7v1.85h-7.7z"/></svg>';
const ICON_PLAY = '<svg class="agent-kill-icon agent-kill-icon--resume" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path class="agent-kill-icon__plate" d="M9.05 2.75h5.9l4.3 4.3v5.9l-4.3 4.3h-5.9l-4.3-4.3v-5.9z"/><path class="agent-kill-icon__play" d="M9.25 7.1v9.8l7.55-4.9z"/></svg>';
const INITIAL_STATUS_DELAY_MS = 2500;
const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

let isKilled = false;
let isCircuitOpen = false;
let btn: HTMLButtonElement | null = null;
let initialStatusQueued = false;
let initialStatusLoaded = false;

function setAgentKillIcon(icon: string): void {
  if (!btn || btn.innerHTML === icon) return;
  btn.innerHTML = icon;
}

function updateButton(): void {
  if (!btn) return;
  if (isKilled) {
    setAgentKillIcon(ICON_PLAY);
    btn.classList.add('killed');
    btn.classList.remove('circuit-open');
    btn.title = 'Agent Resume';
    btn.setAttribute('aria-label', 'Agent Resume');
  } else if (isCircuitOpen) {
    setAgentKillIcon(ICON_STOP);
    btn.classList.remove('killed');
    btn.classList.add('circuit-open');
    btn.title = 'Agent Emergency Stop (Circuit Breaker OPEN)';
    btn.setAttribute('aria-label', 'Agent Emergency Stop - Circuit Breaker is open');
  } else {
    setAgentKillIcon(ICON_STOP);
    btn.classList.remove('killed', 'circuit-open');
    btn.title = 'Agent Emergency Stop';
    btn.setAttribute('aria-label', 'Agent Emergency Stop');
  }
  btn.style.display = '';
}

async function toggleKillSwitch(): Promise<void> {
  if (!btn) return;
  if (isKilled) {
    if (!confirm(window.tr('agent.confirm_kill_release', 'Release Agent Kill Switch?'))) return;
    try {
      const res = await fetch('/api/agent/resume', {
        method: 'POST',
        headers: XHR_HEADERS,
      });
      if (res.ok) {
        isKilled = false;
        updateButton();
      }
    } catch (e) {
      console.error('Failed to resume agent:', e);
    }
  } else {
    if (!confirm(window.tr('agent.confirm_kill_activate', 'Activate Agent Kill Switch?\nAll agent operations will be stopped.'))) return;
    try {
      const res = await fetch('/api/agent/kill', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ reason: 'Manual kill via UI' }),
      });
      if (res.ok) {
        isKilled = true;
        updateButton();
      }
    } catch (e) {
      console.error('Failed to kill agent:', e);
    }
  }
}

function _deferVisibleWork(fn: () => void, timeout = INITIAL_STATUS_DELAY_MS): void {
  const run = (): void => {
    if (document.hidden) return;
    fn();
  };

  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(run, { timeout });
    return;
  }

  setTimeout(run, timeout);
}

function _scheduleInitialStatusFetch(): void {
  if (!btn || initialStatusQueued || initialStatusLoaded) return;
  initialStatusQueued = true;

  const run = (): void => {
    initialStatusQueued = false;
    if (!btn || document.hidden || initialStatusLoaded) return;
    initialStatusLoaded = true;

    fetch('/api/agent/status')
      .then(r => r.json())
      .then(data => {
        const d = data.data ?? data;
        isKilled = !!d.killed;
        const cbState = d.circuit_breaker?.state;
        isCircuitOpen = cbState === 'open' || cbState === 'half_open';
        updateButton();
      })
      .catch(() => {
        // Keep button hidden if API is unavailable
      });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => _deferVisibleWork(run), { once: true });
    return;
  }

  _deferVisibleWork(run);
}

export function initAgentKillButton(): void {
  btn = document.getElementById('agentKillBtn') as HTMLButtonElement | null;
  if (!btn) return;

  btn.addEventListener('click', toggleKillSwitch);

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) _scheduleInitialStatusFetch();
  });

  _scheduleInitialStatusFetch();

  // Real-time sync via SSE
  sseSubscribe('agent.killed', () => {
    isKilled = true;
    updateButton();
  });
  sseSubscribe('agent.resumed', () => {
    isKilled = false;
    updateButton();
  });
  sseSubscribe('agent.circuit_open', () => {
    isCircuitOpen = true;
    updateButton();
  });
  sseSubscribe('agent.circuit_closed', () => {
    isCircuitOpen = false;
    updateButton();
  });
  sseSubscribe('agent.circuit_half_open', () => {
    isCircuitOpen = true;
    updateButton();
  });
}

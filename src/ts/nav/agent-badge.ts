import { sseSubscribe } from '../sse';

function setAgentJournalBadge(count: number): void {
  const badge = document.getElementById('navAgentJournalBadge');
  const overflowBtn = document.getElementById('navOverflowBtn');
  const overflowBadge = document.getElementById('navOverflowBadge');
  if (!badge) return;
  if (count > 0) {
    badge.textContent = String(count);
    badge.style.display = '';
    if (overflowBtn) overflowBtn.setAttribute('data-agent-alert', '1');
    if (overflowBadge) {
      overflowBadge.textContent = '!';
      overflowBadge.style.display = '';
      overflowBadge.style.background = '#e53e3e';
      overflowBadge.style.color = '#fff';
    }
    return;
  }
  badge.textContent = '';
  badge.style.display = 'none';
  if (overflowBtn) overflowBtn.removeAttribute('data-agent-alert');
  if (!overflowBadge) return;
  overflowBadge.style.background = '';
  overflowBadge.style.color = '';
  const popup = document.getElementById('navOverflowMenu');
  if (!popup) return;
  const items = popup.querySelectorAll('.nav-overflow-item:not([style*="display:none"]):not([style*="display: none"])');
  if (items.length > 0) {
    overflowBadge.textContent = String(items.length);
    overflowBadge.style.display = '';
  } else {
    overflowBadge.style.display = 'none';
  }
}

let agentApprovalDisabled = false;

async function pollAgentApproval(): Promise<void> {
  if (agentApprovalDisabled) return;
  try {
    const resp = await fetch('/api/agent/approval', {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (resp.status === 401 || resp.status === 403) {
      agentApprovalDisabled = true;
      return;
    }
    if (!resp.ok) return;
    const json = await resp.json() as { data?: { pending_count?: number } };
    setAgentJournalBadge(json?.data?.pending_count ?? 0);
  } catch {
    // ignore fetch errors
  }
}

function showBudgetBadge(show: boolean): void {
  const badge = document.getElementById('navBudgetBadge');
  const overflowBadge = document.getElementById('navOverflowBadge');
  const overflowBtn = document.getElementById('navOverflowBtn');
  if (!badge) return;
  if (show) {
    badge.style.display = '';
    if (overflowBtn) overflowBtn.setAttribute('data-agent-alert', '1');
    if (overflowBadge && overflowBadge.style.display === 'none') {
      overflowBadge.textContent = '!';
      overflowBadge.style.display = '';
      overflowBadge.style.background = '#f59e0b';
      overflowBadge.style.color = '#000';
    }
  } else {
    badge.style.display = 'none';
  }
}

export function initAgentJournalBadge(): void {
  if (window.location.pathname.startsWith('/agent-journal')) return;
  setTimeout(() => { void pollAgentApproval(); }, 2000);
  setInterval(() => { void pollAgentApproval(); }, 30000);
  sseSubscribe('agent.approval_required', () => { void pollAgentApproval(); });
  sseSubscribe('agent.budget_warning', () => { showBudgetBadge(true); });
  sseSubscribe('agent.budget_exhausted', () => { showBudgetBadge(true); });
  sseSubscribe('agent.budget_reset', () => { showBudgetBadge(false); });
}

/**
 * agent-journal-app.ts -- Agent Journal page entry point.
 *
 * Handles filtering, pagination, Kill Switch banner,
 * Circuit Breaker state, and Budget display.
 * Data loading and rendering logic is in agent-journal-data.ts.
 */

import { sseSubscribe } from '../sse';
import {
  renderTable,
  updatePagination,
  loadStats,
  loadAgentStatus,
} from './agent-journal-data';
import { loadApprovalQueue as loadApprovalQueueView } from './agent-journal-approval';
import { loadScopes } from './agent-journal-scope';
import { initAnomaly, loadAnomaly } from './agent-journal-anomaly';
import { initAudit, loadAudit } from './agent-journal-audit';
import { initToolLevels } from './agent-journal-tool-levels';
import { initUndo, loadUndo } from './agent-journal-undo';

const PAGE_SIZE = 50;
const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;
let currentOffset = 0;
let totalItems = 0;

/* ------------------------------------------------------------------ */
/*  DOM References                                                     */
/* ------------------------------------------------------------------ */

const approvalSection = document.getElementById('ajApprovalSection') as HTMLElement;
const approvalList = document.getElementById('ajApprovalList') as HTMLElement;
const approvalCount = document.getElementById('ajApprovalCount') as HTMLElement;
const tbody = document.getElementById('ajTableBody') as HTMLTableSectionElement;
const killBanner = document.getElementById('ajKillBanner') as HTMLElement;
const cbBanner = document.getElementById('ajCbBanner') as HTMLElement;
const statsContainer = document.getElementById('ajStats') as HTMLElement;
const budgetContent = document.getElementById('ajBudgetContent') as HTMLElement;
const budgetResetBtn = document.getElementById('ajBudgetResetBtn') as HTMLButtonElement;
const killToggleBtn = document.getElementById('ajKillToggleBtn') as HTMLButtonElement;
const resumeBtn = document.getElementById('ajResumeBtn') as HTMLButtonElement;
const cbResetBtn = document.getElementById('ajCbResetBtn') as HTMLButtonElement;
const filterStatus = document.getElementById('ajFilterStatus') as HTMLSelectElement;
const filterTool = document.getElementById('ajFilterTool') as HTMLInputElement;
const filterSession = document.getElementById('ajFilterSession') as HTMLInputElement;
const filterBtn = document.getElementById('ajFilterBtn') as HTMLButtonElement;
const prevBtn = document.getElementById('ajPrevBtn') as HTMLButtonElement;
const nextBtn = document.getElementById('ajNextBtn') as HTMLButtonElement;
const pageInfo = document.getElementById('ajPageInfo') as HTMLElement;

/* ------------------------------------------------------------------ */
/*  Data Loading                                                       */
/* ------------------------------------------------------------------ */

async function loadJournal(): Promise<void> {
  const params = new URLSearchParams();
  if (filterStatus.value) params.set('status', filterStatus.value);
  if (filterTool.value) params.set('tool_name', filterTool.value);
  if (filterSession.value) params.set('session_id', filterSession.value);
  params.set('limit', String(PAGE_SIZE));
  params.set('offset', String(currentOffset));

  try {
    const res = await fetch(`/api/agent/journal?${params}`);
    const json = await res.json();
    const data = json.data ?? json;
    totalItems = data.total ?? 0;
    const items: Array<Record<string, unknown>> = data.items ?? [];
    renderTable(tbody, items);
    updatePagination(pageInfo, prevBtn, nextBtn, currentOffset, totalItems, PAGE_SIZE);
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="6" class="aj-empty">Failed to load journal</td></tr>';
  }
}

/** Wrapper to reload agent status with all required DOM refs. */
function reloadAgentStatus(): void {
  loadAgentStatus(killBanner, cbBanner, killToggleBtn, cbResetBtn, statsContainer, budgetContent);
}

/* ------------------------------------------------------------------ */
/*  Events                                                             */
/* ------------------------------------------------------------------ */

filterBtn.addEventListener('click', () => {
  currentOffset = 0;
  loadJournal();
});

// Execute filter on Enter key
[filterTool, filterSession].forEach(el => {
  el.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      currentOffset = 0;
      loadJournal();
    }
  });
});

filterStatus.addEventListener('change', () => {
  currentOffset = 0;
  loadJournal();
});

prevBtn.addEventListener('click', () => {
  currentOffset = Math.max(0, currentOffset - PAGE_SIZE);
  loadJournal();
});

nextBtn.addEventListener('click', () => {
  currentOffset += PAGE_SIZE;
  loadJournal();
});

budgetResetBtn.addEventListener('click', async () => {
  if (!confirm(window.tr('agent.confirm_budget_reset', 'Reset budget counter?'))) return;
  try {
    await fetch('/api/agent/budget/reset', {
      method: 'POST',
      headers: XHR_HEADERS,
    });
    reloadAgentStatus();
  } catch {
    // ignore
  }
});

killToggleBtn.addEventListener('click', async () => {
  const isKilled = killBanner.classList.contains('active');
  if (isKilled) return; // Use the Banner's release button
  if (!confirm(window.tr('agent.confirm_kill_enable', 'Enable Agent Kill Switch? All agent operations will be blocked.'))) return;
  try {
    await fetch('/api/agent/kill', { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    reloadAgentStatus();
  } catch { /* ignore */ }
});

resumeBtn.addEventListener('click', async () => {
  if (!confirm(window.tr('agent.confirm_kill_disable', 'Release Kill Switch?'))) return;
  try {
    await fetch('/api/agent/resume', { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    reloadAgentStatus();
  } catch { /* ignore */ }
});

cbResetBtn.addEventListener('click', async () => {
  if (!confirm(window.tr('agent.confirm_cb_reset', 'Reset Circuit Breaker?'))) return;
  try {
    await fetch('/api/agent/circuit-breaker/reset', { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    reloadAgentStatus();
  } catch { /* ignore */ }
});

/* ------------------------------------------------------------------ */
/*  Approval Queue                                                     */
/* ------------------------------------------------------------------ */

async function loadApprovalQueue(): Promise<void> {
  await loadApprovalQueueView(approvalSection, approvalList, approvalCount, loadJournal);
}

// SSE real-time sync
sseSubscribe('agent.killed', () => {
  killBanner.classList.add('active');
});
sseSubscribe('agent.resumed', () => {
  killBanner.classList.remove('active');
});
sseSubscribe('agent.circuit_open', () => {
  reloadAgentStatus();
});
sseSubscribe('agent.circuit_closed', () => {
  reloadAgentStatus();
});
sseSubscribe('agent.circuit_half_open', () => {
  reloadAgentStatus();
});
sseSubscribe('agent.budget_warning', () => {
  reloadAgentStatus();
});
sseSubscribe('agent.budget_exhausted', () => {
  reloadAgentStatus();
});

sseSubscribe('agent.approval_required', () => {
  loadApprovalQueue();
});
sseSubscribe('agent.anomaly_detected', () => void loadAnomaly());
sseSubscribe('agent.anomaly_cleared', () => void loadAnomaly());
sseSubscribe('agent.action_completed', () => { void loadUndo(); void loadAudit(); });

/* ------------------------------------------------------------------ */
/*  Init                                                               */
/* ------------------------------------------------------------------ */

loadJournal();
loadApprovalQueue();
loadStats(statsContainer).then(() => reloadAgentStatus());
loadScopes();
initAnomaly();
initAudit();
initToolLevels();
initUndo();

// Re-render after the i18n dictionary loads so the initial English-fallback
// labels (Total Actions / Sessions / Success / Errors / Run Now…) get
// replaced with their localized equivalents.
const i18nReload = () => {
  loadJournal();
  loadStats(statsContainer);
  loadScopes();
};
document.addEventListener('tr-runtime:ready', i18nReload, { once: true });
document.addEventListener('i18n:changed', i18nReload);

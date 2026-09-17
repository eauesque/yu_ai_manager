/**
 * agent-journal-data.ts -- Data loading, rendering, and status display
 * for the Agent Journal page.
 *
 * Extracted from agent-journal-app.ts to keep each module under 300 lines.
 */

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

export function escapeHtml(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

export function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString('ja-JP', { hour12: false });
  } catch {
    return iso;
  }
}

export function statusClass(status: string): string {
  switch (status) {
    case 'success': return 'aj-status-success';
    case 'error': return 'aj-status-error';
    case 'killed': return 'aj-status-killed';
    case 'circuit_blocked': return 'aj-status-error';
    case 'budget_blocked': return 'aj-status-error';
    default: return '';
  }
}

export function budgetBarClass(used: number, limit: number): string {
  if (limit <= 0) return 'ok';
  const pct = used / limit;
  if (pct >= 1) return 'danger';
  if (pct >= 0.8) return 'warn';
  return 'ok';
}

/* ------------------------------------------------------------------ */
/*  Table rendering                                                    */
/* ------------------------------------------------------------------ */

export function renderTable(
  tbody: HTMLTableSectionElement,
  items: Array<Record<string, unknown>>,
): void {
  if (items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="aj-empty">No entries found</td></tr>';
    return;
  }
  tbody.innerHTML = items.map(item => `
    <tr>
      <td class="aj-time">${formatTime(String(item.timestamp ?? ''))}</td>
      <td class="aj-tool-name">${escapeHtml(String(item.tool_name ?? ''))}</td>
      <td><span class="aj-status ${statusClass(String(item.status ?? ''))}">${escapeHtml(String(item.status ?? ''))}</span></td>
      <td>${item.duration_ms ?? 0}ms</td>
      <td class="aj-session">${escapeHtml(String(item.session_id ?? ''))}</td>
      <td>${escapeHtml(String(item.result_summary ?? '').substring(0, 100))}</td>
    </tr>
  `).join('');
}

/* ------------------------------------------------------------------ */
/*  Pagination display                                                 */
/* ------------------------------------------------------------------ */

export function updatePagination(
  pageInfo: HTMLElement,
  prevBtn: HTMLButtonElement,
  nextBtn: HTMLButtonElement,
  currentOffset: number,
  totalItems: number,
  pageSize: number,
): void {
  const page = Math.floor(currentOffset / pageSize) + 1;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  pageInfo.textContent = `${page} / ${totalPages} (${totalItems} entries)`;
  prevBtn.disabled = currentOffset <= 0;
  nextBtn.disabled = currentOffset + pageSize >= totalItems;
}

/* ------------------------------------------------------------------ */
/*  Stats loading                                                      */
/* ------------------------------------------------------------------ */

function ajTr(key: string, fallback: string): string {
  return typeof window.tr === 'function' ? window.tr(key, fallback) : fallback;
}

function buildStatCard(value: string | number, label: string): HTMLDivElement {
  const card = document.createElement('div');
  card.className = 'aj-stat-card';
  const v = document.createElement('div');
  v.className = 'aj-stat-value';
  v.textContent = String(value);
  const l = document.createElement('div');
  l.className = 'aj-stat-label';
  l.textContent = label;
  card.append(v, l);
  return card;
}

export async function loadStats(statsContainer: HTMLElement): Promise<void> {
  try {
    const res = await fetch('/api/agent/journal/stats');
    const json = await res.json();
    const data = json.data ?? json;
    statsContainer.replaceChildren(
      buildStatCard(data.total_actions ?? 0, ajTr('agent_journal.total_actions', '総アクション数')),
      buildStatCard(data.total_sessions ?? 0, ajTr('agent_journal.sessions', 'セッション数')),
      buildStatCard(data.by_status?.success ?? 0, ajTr('agent_journal.success', '成功')),
      buildStatCard(data.by_status?.error ?? 0, ajTr('agent_journal.errors', '失敗')),
    );
  } catch {
    // ignore
  }
}

/* ------------------------------------------------------------------ */
/*  Agent status + budget display                                      */
/* ------------------------------------------------------------------ */

export function renderBudget(
  budgetContent: HTMLElement,
  budget: Record<string, unknown>,
): void {
  const used = budget.used as Record<string, number> ?? {};
  const limits = budget.limits as Record<string, number> ?? {};

  const rows = [
    { label: 'Total', usedKey: 'total', limitKey: 'total_actions' },
    { label: 'Write', usedKey: 'write', limitKey: 'write_actions' },
    { label: 'Destructive', usedKey: 'destructive', limitKey: 'destructive_actions' },
  ];

  budgetContent.innerHTML = rows.map(r => {
    const u = (used as Record<string, number>)[r.usedKey] ?? 0;
    const l = (limits as Record<string, number>)[r.limitKey] ?? 1;
    const pct = l > 0 ? Math.min(100, Math.round((u / l) * 100)) : 0;
    const cls = budgetBarClass(u, l);
    return `
      <div class="aj-budget-row">
        <span>${r.label}</span>
        <span>${u} / ${l}</span>
      </div>
      <div class="aj-budget-bar">
        <div class="aj-budget-fill ${cls}" style="width:${pct}%"></div>
      </div>
    `;
  }).join('');
}

export async function loadAgentStatus(
  killBanner: HTMLElement,
  cbBanner: HTMLElement,
  killToggleBtn: HTMLButtonElement,
  cbResetBtn: HTMLButtonElement,
  statsContainer: HTMLElement,
  budgetContent: HTMLElement,
): Promise<void> {
  try {
    const res = await fetch('/api/agent/status');
    const json = await res.json();
    const data = json.data ?? json;

    // Kill Switch banner + button state
    const killed = !!data.killed;
    killBanner.classList.toggle('active', killed);
    killToggleBtn.classList.toggle('active', killed);
    killToggleBtn.textContent = killed
      ? '🛑 ' + ajTr('agent_journal.kill_active', '緊急停止中')
      : '🛑 ' + ajTr('agent_journal.kill_btn', '緊急停止');

    // Circuit Breaker banner + reset button visibility
    const cbState = data.circuit_breaker?.state ?? 'closed';
    cbBanner.classList.remove('open', 'half-open');
    cbResetBtn.style.display = (cbState === 'open' || cbState === 'half_open') ? '' : 'none';
    if (cbState === 'open') {
      cbBanner.classList.add('open');
      const reason = data.circuit_breaker?.reason ?? '';
      cbBanner.textContent = `Circuit Breaker: OPEN${reason ? ' - ' + reason : ''}`;
    } else if (cbState === 'half_open') {
      cbBanner.classList.add('half-open');
      cbBanner.textContent = 'Circuit Breaker: HALF_OPEN (read-only mode)';
    }

    // Circuit Breaker stats in stat cards
    if (data.circuit_breaker) {
      const cb = data.circuit_breaker;
      const cbCard = document.createElement('div');
      cbCard.className = 'aj-stat-card';
      const stateColors: Record<string, string> = {
        closed: '#64748b', open: '#ef4444', half_open: '#f59e0b'
      };
      const stateLabels: Record<string, string> = {
        closed: '正常稼働', open: 'OPEN（遮断中）', half_open: 'HALF_OPEN',
      };
      const valEl = document.createElement('div');
      valEl.className = 'aj-stat-value';
      valEl.style.color = stateColors[cb.state] ?? 'inherit';
      valEl.textContent = stateLabels[cb.state] ?? cb.state.toUpperCase();
      if (cb.state === 'closed') valEl.title = 'Circuit Breaker が正常状態です（リクエスト通過中）';
      const lbl = document.createElement('div');
      lbl.className = 'aj-stat-label';
      lbl.textContent = ajTr('agent_journal.circuit_breaker', 'サーキットブレーカー');
      cbCard.appendChild(valEl);
      cbCard.appendChild(lbl);
      statsContainer.appendChild(cbCard);
    }

    // Budget display
    if (data.budget?.used) {
      renderBudget(budgetContent, data.budget);
    }
  } catch {
    // ignore
  }
}

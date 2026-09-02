import { icon } from '../shared/icon';

export interface ApprovalItem {
  request_id: string;
  session_id: string;
  tool_name: string;
  params: Record<string, unknown>;
  created_at: number;
  remaining_seconds: number;
}

const APPROVAL_RETRY_COOLDOWN_MS = 30_000;

let agentJournalApprovalDisabled = false;
let agentJournalApprovalRetryAt = 0;

async function respondApproval(requestId: string, decision: string, reloadQueue: () => Promise<void>, reloadJournal: () => Promise<void>): Promise<void> {
  try {
    await fetch(`/api/agent/approval/${encodeURIComponent(requestId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision }),
    });
    await reloadQueue();
    await reloadJournal();
  } catch {
    // ignore
  }
}

export async function loadApprovalQueue(
  approvalSection: HTMLElement,
  approvalList: HTMLElement,
  approvalCount: HTMLElement,
  reloadJournal: () => Promise<void>,
): Promise<void> {
  if (agentJournalApprovalDisabled) {
    if (Date.now() >= agentJournalApprovalRetryAt) {
      agentJournalApprovalDisabled = false;
    } else {
      approvalSection.style.display = 'none';
      return;
    }
  }
  try {
    const res = await fetch('/api/agent/approval', {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (res.status === 401 || res.status === 403) {
      agentJournalApprovalDisabled = true;
      agentJournalApprovalRetryAt = Date.now() + APPROVAL_RETRY_COOLDOWN_MS;
      approvalSection.style.display = 'none';
      return;
    }
    agentJournalApprovalRetryAt = 0;
    approvalSection.style.display = 'none';
    if (!res.ok) {
      return;
    }
    const json = await res.json();
    const data = json.data ?? json;
    const pending: ApprovalItem[] = data.pending ?? [];
    if (pending.length === 0) {
      approvalSection.style.display = 'none';
      return;
    }
    approvalSection.style.display = '';
    approvalCount.textContent = String(pending.length);
    while (approvalList.firstChild) approvalList.removeChild(approvalList.firstChild);
    for (const item of pending) {
      const el = document.createElement('div');
      el.className = 'aj-approval-item';
      const header = document.createElement('div');
      header.className = 'aj-approval-header';
      const toolEl = document.createElement('span');
      toolEl.className = 'aj-approval-tool';
      toolEl.textContent = item.tool_name;
      const sessionEl = document.createElement('span');
      sessionEl.className = 'aj-approval-session';
      sessionEl.textContent = item.session_id.substring(0, 16) + '…';
      const timerEl = document.createElement('span');
      timerEl.className = 'aj-approval-timer';
      timerEl.textContent = window.tr('agent_journal.approval_remaining', '残り {s}s').replace('{s}', String(Math.round(item.remaining_seconds)));
      header.append(toolEl, sessionEl, timerEl);
      el.appendChild(header);
      const paramsEl = document.createElement('div');
      paramsEl.className = 'aj-approval-params';
      const p = item.params ?? {};
      const lines: string[] = [];
      if (p.tool_name) lines.push(`ツール: ${p.tool_name}`);
      if (p.path) lines.push(`パス: ${p.path}`);
      if (p.command) lines.push(`コマンド: ${p.command}`);
      if (p.description) lines.push(`説明: ${p.description}`);
      if (p.action) lines.push(`操作: ${p.action}`);
      paramsEl.textContent = lines.length ? lines.join('\n') : JSON.stringify(item.params, null, 2);
      el.appendChild(paramsEl);
      const btns = document.createElement('div');
      btns.className = 'aj-approval-btns';
      const makeButton = (iconName: string, label: string, decision: string, className: string) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = className;
        // Trusted SVG markup from sprite helper + static i18n label.
        btn.insertAdjacentHTML('beforeend', icon(iconName));
        btn.append(' ' + label);
        btn.addEventListener('click', () => {
          void respondApproval(item.request_id, decision, () => loadApprovalQueue(approvalSection, approvalList, approvalCount, reloadJournal), reloadJournal);
        });
        return btn;
      };
      btns.append(
        makeButton('check', window.tr('agent_journal.approval_allow', '許可'), 'allow', 'aj-btn-allow'),
        makeButton('star-filled', window.tr('agent_journal.approval_always_allow', '常に許可'), 'always_allow', 'aj-btn-always'),
        makeButton('x', window.tr('agent_journal.approval_deny', '拒否'), 'deny', 'aj-btn-deny'),
      );
      el.appendChild(btns);
      approvalList.appendChild(el);
    }
  } catch {
    approvalSection.style.display = 'none';
  }
}

/**
 * Agent Journal — Audit Log section.
 * Table + acknowledge per row, verify chain, export report.
 * Uses GET /api/agent/audit/log (NOT /api/agent/audit which is status-only).
 */

interface AuditEntry {
  id: number;
  action: string;
  timestamp: string;
  severity: string;
  acknowledged: boolean;
}

interface AuditVerifyResult {
  verified: boolean;
  broken_at_index: number | null;
  hash_chain_length: number;
}

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function tStr(key: string, fallback: string): string {
  return typeof window.tr === 'function' ? window.tr(key, fallback) : fallback;
}

function renderAuditEntries(content: HTMLElement, entries: AuditEntry[]): void {
  if (entries.length === 0) {
    content.innerHTML = `<div class="aj-empty" data-i18n="agent_journal.audit_empty">${tStr('agent_journal.audit_empty', 'No audit log entries')}</div>`;
    return;
  }
  content.innerHTML = entries
    .map(
      (e) =>
        `<div class="aj-audit-item">
          <span class="aj-time">${new Date(e.timestamp).toLocaleString()}</span>
          <span class="aj-tool-name">${escHtml(e.action)}</span>
          <span class="aj-level-${escHtml(e.severity)}">${escHtml(e.severity)}</span>
          ${
            !e.acknowledged
              ? `<button class="aj-btn aj-btn-ack aj-audit-ack-btn" data-id="${e.id}"
                   data-i18n="agent_journal.audit_acknowledge">
                   ${tStr('agent_journal.audit_acknowledge', 'Acknowledge')}</button>`
              : '<span>✓</span>'
          }
        </div>`,
    )
    .join('');
  content.querySelectorAll<HTMLButtonElement>('.aj-audit-ack-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset['id'];
      if (!id) return;
      btn.disabled = true;
      void fetch(`/api/agent/audit/acknowledge/${encodeURIComponent(id)}`, { method: 'POST' })
        .then(() => loadAudit());
    });
  });
}

export async function loadAudit(): Promise<void> {
  const section = document.getElementById('ajAuditSection');
  const content = document.getElementById('ajAuditContent');
  if (!section || !content) return;
  try {
    const res = await fetch('/api/agent/audit/log?limit=50');
    if (!res.ok) return;
    const entries = (await res.json()) as AuditEntry[];
    section.style.display = '';
    renderAuditEntries(content, entries);
  } catch { /* ignore */ }
}

export function initAudit(): void {
  document.getElementById('ajAuditVerifyBtn')?.addEventListener('click', () => {
    const el = document.getElementById('ajAuditVerifyResult');
    if (!el) return;
    void fetch('/api/agent/audit/verify')
      .then((r) => r.json() as Promise<AuditVerifyResult>)
      .then((data) => {
        el.style.display = '';
        if (data.verified) {
          el.className = 'aj-audit-verify-result ok';
          el.textContent = tStr('agent_journal.audit_verify_ok', 'Chain verified ✓');
        } else {
          el.className = 'aj-audit-verify-result broken';
          el.textContent = tStr('agent_journal.audit_verify_broken', 'Chain broken at index {n}')
            .replace('{n}', String(data.broken_at_index ?? '?'));
        }
      })
      .catch(() => { /* ignore */ });
  });

  document.getElementById('ajAuditReportBtn')?.addEventListener('click', () => {
    void fetch('/api/agent/audit/report', { method: 'POST' })
      .then((r) => r.json())
      .then((data) => {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `audit-report-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      })
      .catch(() => { /* ignore */ });
  });

  void loadAudit();
}

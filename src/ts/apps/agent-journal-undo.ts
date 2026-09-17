/**
 * Agent Journal — Undoable Actions section.
 * GET /api/agent/undoable, POST /api/agent/undo/<id>.
 */

interface UndoableAction {
  journal_id: number;
  tool_name: string;
  timestamp: string;
  result_summary: string;
}

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function tStr(key: string, fallback: string): string {
  return typeof window.tr === 'function' ? window.tr(key, fallback) : fallback;
}

function renderUndoActions(content: HTMLElement, actions: UndoableAction[]): void {
  if (actions.length === 0) {
    content.innerHTML = `<div class="aj-empty" data-i18n="agent_journal.undo_empty">${tStr('agent_journal.undo_empty', 'No undoable actions')}</div>`;
    return;
  }
  content.innerHTML = actions
    .map(
      (a) =>
        `<div class="aj-undo-item">
          <span class="aj-time">${new Date(a.timestamp).toLocaleString()}</span>
          <span class="aj-tool-name">${escHtml(a.tool_name)}</span>
          <span>${escHtml(a.result_summary ?? '')}</span>
          <button class="aj-btn aj-btn-undo aj-undo-btn" data-id="${a.journal_id}"
                  data-i18n="agent_journal.undo_btn">
            ${tStr('agent_journal.undo_btn', 'Undo')}
          </button>
        </div>`,
    )
    .join('');
  content.querySelectorAll<HTMLButtonElement>('.aj-undo-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset['id'];
      if (!id) return;
      btn.disabled = true;
      void fetch(`/api/agent/undo/${encodeURIComponent(id)}`, { method: 'POST' })
        .then(() => loadUndo());
    });
  });
}

export async function loadUndo(): Promise<void> {
  const section = document.getElementById('ajUndoSection');
  const content = document.getElementById('ajUndoContent');
  if (!section || !content) return;
  try {
    const res = await fetch('/api/agent/undoable');
    if (!res.ok) return;
    const actions = (await res.json()) as UndoableAction[];
    section.style.display = actions.length > 0 ? '' : 'none';
    renderUndoActions(content, actions);
  } catch { /* ignore */ }
}

export function initUndo(): void { void loadUndo(); }

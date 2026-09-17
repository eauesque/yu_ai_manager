/**
 * Agent Journal — Tool Safety Levels section.
 * Read-only table. Loaded once at init. GET /api/agent/tool-levels.
 */

type ToolLevelValue = 'auto' | 'notify' | 'approve';
interface ToolLevels { [toolName: string]: ToolLevelValue; }

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function tStr(key: string, fallback: string): string {
  return typeof window.tr === 'function' ? window.tr(key, fallback) : fallback;
}

export async function loadToolLevels(): Promise<void> {
  const section = document.getElementById('ajToolLevelsSection');
  const content = document.getElementById('ajToolLevelsContent');
  if (!section || !content) return;
  try {
    const res = await fetch('/api/agent/tool-levels');
    if (!res.ok) return;
    const levels = (await res.json()) as ToolLevels;
    const entries = Object.entries(levels);
    section.style.display = '';
    if (entries.length === 0) {
      content.innerHTML = `<div class="aj-empty" data-i18n="agent_journal.tool_levels_empty">${tStr('agent_journal.tool_levels_empty', 'No tool levels configured')}</div>`;
      return;
    }
    const rows = entries
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, level]) =>
        `<tr><td class="aj-tool-name">${escHtml(name)}</td><td class="aj-level-${escHtml(level)}">${escHtml(level)}</td></tr>`)
      .join('');
    content.innerHTML = `<table class="aj-tool-levels-table"><thead><tr><th>Tool</th><th>Level</th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch { /* ignore */ }
}

export function initToolLevels(): void { void loadToolLevels(); }

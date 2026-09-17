import type { StoryEvent } from './page';

function escHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export async function loadTrophyDetails(trFn: ((k: string, p?: unknown) => unknown) | null): Promise<void> {
  const section = document.getElementById('trophyDetailSection');
  if (!section) return;
  try {
    const res = await fetch('/api/trophies');
    if (!res.ok) return;
    const data: { trophies?: Array<{ id: string; icon: string; title: string; description?: string; earned: boolean; earned_date?: string }> } = await res.json();
    const trophies = data.trophies;
    if (!trophies || trophies.length === 0) return;
    const earned = trophies.filter((t) => t.earned);
    const unearned = trophies.filter((t) => !t.earned);
    const titleEarned = escHtml((trFn ? trFn('story.trophies_earned') as string : '') || 'Earned Trophies');
    const titleLocked = escHtml((trFn ? trFn('story.trophies_locked') as string : '') || 'Locked Trophies');
    let html = `<h2 style="font-size:14px;margin:0 0 10px 0;color:var(--muted,#888);">${titleEarned} (${earned.length})</h2><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px;margin-bottom:20px;">`;
    for (const trophy of earned) {
      html += `<div style="padding:12px;border-radius:8px;background:rgba(255,215,0,0.08);border:1px solid rgba(255,215,0,0.25);display:flex;flex-direction:column;align-items:center;text-align:center;gap:4px;"><span style="font-size:28px;">${escHtml(trophy.icon || '🏆')}</span><div style="font-size:12px;font-weight:600;">${escHtml(trophy.title)}</div>${trophy.description ? `<div style="font-size:10px;color:var(--muted,#888);">${escHtml(trophy.description)}</div>` : ''}${trophy.earned_date ? `<div style="font-size:10px;color:var(--muted,#888);">${escHtml(trophy.earned_date)}</div>` : ''}</div>`;
    }
    html += '</div>';
    if (unearned.length > 0) {
      html += `<h2 style="font-size:14px;margin:0 0 10px 0;color:var(--muted,#888);">${titleLocked} (${unearned.length})</h2><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px;">`;
      for (const trophy of unearned) {
        html += `<div style="padding:12px;border-radius:8px;background:rgba(100,100,100,0.06);border:1px solid rgba(100,100,100,0.15);display:flex;flex-direction:column;align-items:center;text-align:center;gap:4px;opacity:0.5;"><span style="font-size:28px;filter:grayscale(1);">🏆</span><div style="font-size:12px;font-weight:600;">${escHtml(trophy.title)}</div>${trophy.description ? `<div style="font-size:10px;color:var(--muted,#888);">${escHtml(trophy.description)}</div>` : ''}</div>`;
      }
      html += '</div>';
    }
    section.innerHTML = html;
    section.style.display = 'block';
  } catch {
    // non-critical
  }
}

export function renderMilestoneShelf(events: StoryEvent[], trFn: ((k: string, p?: unknown) => unknown) | null): void {
  const milestoneEvents = events.filter((e) => e.type && e.type.startsWith('milestone'));
  if (milestoneEvents.length === 0) return;
  const shelf = document.getElementById('trophyShelf');
  const list = document.getElementById('trophyList');
  if (!list) return;
  list.innerHTML = milestoneEvents.map((e) => {
    const title = escHtml((trFn ? trFn(e.title_key || '', e.params || {}) as string : '') || e.type || '');
    const icon = escHtml(e.icon || '');
    const date = escHtml(e.date);
    return `<div style="display:flex;align-items:center;gap:6px;padding:8px 14px;border-radius:8px;background:rgba(255,215,0,0.08);border:1px solid rgba(255,215,0,0.2);"><span style="font-size:22px;">${icon}</span><div><div style="font-size:13px;font-weight:600;">${title}</div><div style="font-size:11px;color:var(--muted,#888);">${date}</div></div></div>`;
  }).join('');
  if (shelf) shelf.style.display = 'block';
}

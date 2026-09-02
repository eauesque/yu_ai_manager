import type { ConditionDef } from './config';

export function updateConditionHintState(
  chipCount: number,
  chipsContainer: HTMLElement,
  activeConditions: Set<string>,
  conditions: Record<string, ConditionDef>,
  clearAllConditions: (() => void) | undefined,
  tr: (key: string, fallback?: string | Record<string, unknown>) => string,
  esc: (value: unknown) => string,
): void {
  const hintEl = document.getElementById('conditionMenuHint');
  if (hintEl) {
    if (chipCount >= 2) {
      hintEl.innerHTML = `<span style="color:var(--muted-accessible,#aab);">${esc(tr('conditions.hint.count_many', { count: chipCount }))}</span> `
        + `<button type="button" data-action="clear-all" style="background:none;border:none;color:#e74c3c;cursor:pointer;font-size:11px;text-decoration:underline;padding:0;">${esc(tr('conditions.clear_all'))}</button>`;
      const clearBtn = hintEl.querySelector<HTMLButtonElement>('[data-action="clear-all"]');
      if (clearBtn) clearBtn.addEventListener('click', () => { clearAllConditions?.(); });
    } else if (chipCount === 1) {
      hintEl.textContent = tr('conditions.hint.count_one');
    } else {
      const previewKeys = ['period', 'format', 'model', 'inPrompt', 'favOnly', 'collection'];
      const labels = previewKeys
        .map((k) => conditions[k]?.icon || '')
        .filter(Boolean)
        .join(' ');
      hintEl.textContent = labels ? labels + ' ...' : '';
    }
  }

  requestAnimationFrame(() => {
    const isOverflowing = chipsContainer.scrollHeight > chipsContainer.clientHeight + 4;
    let toggleBtn = document.getElementById('chipExpandToggle') as HTMLButtonElement | null;

    if (isOverflowing && chipCount >= 3) {
      if (!toggleBtn) {
        toggleBtn = document.createElement('button');
        toggleBtn.id = 'chipExpandToggle';
        toggleBtn.type = 'button';
        Object.assign(toggleBtn.style, {
          background: 'none', border: 'none', color: '#667eea',
          cursor: 'pointer', fontSize: '11px', padding: '2px 0',
          marginTop: '2px', display: 'block',
        });
        toggleBtn.addEventListener('click', () => {
          const expanded = chipsContainer.style.maxHeight === 'none';
          chipsContainer.style.maxHeight = expanded ? '' : 'none';
          toggleBtn!.textContent = expanded ? tr('conditions.toggle.close') : tr('conditions.toggle.more');
        });
        chipsContainer.parentNode?.insertBefore(toggleBtn, chipsContainer.nextSibling);
      }
      const expanded = chipsContainer.style.maxHeight === 'none';
      toggleBtn.textContent = expanded ? tr('conditions.toggle.close') : tr('conditions.toggle.more');
      toggleBtn.style.display = '';
    } else if (toggleBtn) {
      toggleBtn.style.display = 'none';
      chipsContainer.style.maxHeight = '';
    }
  });

  localStorage.setItem('tagdb_active_conditions', JSON.stringify([...activeConditions]));
}

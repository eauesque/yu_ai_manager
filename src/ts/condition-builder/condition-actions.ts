import * as state from './state';
import * as menuCore from './menu-core';
import { getMode } from '../search-results/results/grouping-utils';
import { triggerInstant } from '../search-results/search/live';
import { getServerPlatform } from '../shared/runtime-state/server-info-state';

const GROUPED_ALLOWED: Record<string, boolean> = { period: true, sort: true, inFolder: true, orTags: true };

export function addCondition(key: string): void {
  const groupMode = getMode();
  if (groupMode === 'folder' || groupMode === 'zip') {
    if (key === 'tagCase') {
      const platform = getServerPlatform();
      if (!platform || platform === 'Windows') return;
    } else if (!GROUPED_ALLOWED[key]) {
      return;
    }
  }
  // For toggle conditions, auto-enable the hidden checkbox on add
  const cond = state.CONDITIONS[key];
  if (cond?.type === 'toggle' && cond.target) {
    const hidden = document.getElementById(cond.target) as HTMLInputElement | null;
    if (hidden && !hidden.checked) hidden.checked = true;
  }
  state.activateCondition(key);
  menuCore.renderConditionMenu();
  menuCore.announceA11yStatus(window.tr('a11y.condition_added', { label: state.conditionLabel(state.CONDITIONS[key]) || key }));
  menuCore.closeConditionMenu({ restoreFocus: false });
  requestAnimationFrame(() => {
    const targetField = document.querySelector<HTMLElement>(`.condition-field[data-key="${key}"] input, .condition-field[data-key="${key}"] select, .condition-field[data-key="${key}"] textarea`);
    if (targetField) targetField.focus();
  });
  triggerInstant();
}

export function removeCondition(key: string): void {
  if (key === 'sort') return;
  state.resetConditionField(key);
  const set = state.getActiveSet();
  if (set) set.delete(key);
  state.renderActiveConditions();
  menuCore.renderConditionMenu();
  menuCore.announceA11yStatus(window.tr('a11y.condition_removed', { label: state.conditionLabel(state.CONDITIONS[key]) || key }));
  triggerInstant();
}

export function clearAllConditions(): void {
  const set = state.getActiveSet();
  if (!set) return;
  for (const key of set) {
    state.resetConditionField(key);
  }
  set.clear();
  set.add('sort');
  state.renderActiveConditions();
  menuCore.renderConditionMenu();
  triggerInstant();
}

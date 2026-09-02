import { CONDITIONS, PERIOD_PRESETS } from './config';
import type { ConditionDef } from './config';
import { renderActiveConditions as renderActiveConditionsImpl } from './render';
import { renderConditionMenu } from './menu-core';
import { setSearchFromTs } from '../shared/runtime-state/search-period-state';

export function conditionLabel(cond: ConditionDef | undefined): string {
  return window.tr(cond?.labelKey || '', cond?.label || '');
}

export function conditionPlaceholder(cond: ConditionDef | undefined): string {
  return window.tr(cond?.placeholderKey || '', cond?.placeholder || '');
}

let activeConditions = new Set<string>();

function resetConditionField(key: string): void {
  const cond = CONDITIONS[key];
  if (!cond) return;

  if (cond.type === 'period') {
    const targets = cond.targets || ['fromDate', 'toDate'];
    targets.forEach((t) => {
      const el = document.getElementById(t) as HTMLInputElement | null;
      if (el) el.value = '';
    });
    setSearchFromTs(null);
  } else if (cond.type === 'resolution') {
    (cond.targets || []).forEach((t) => {
      const el = document.getElementById(t) as HTMLInputElement | null;
      if (el) el.value = '';
    });
  } else if (cond.type === 'toggle') {
    const el = document.getElementById(cond.target!) as HTMLInputElement | null;
    if (el) el.checked = false;
  } else if (cond.type === 'select') {
    const el = document.getElementById(cond.target!) as HTMLSelectElement | null;
    if (el) el.value = el.options[0]?.value || '';
    if (cond.target === 'fileFormat') {
      const exts = document.getElementById('formatExts') as HTMLInputElement | null;
      if (exts) exts.value = '';
    }
  } else {
    const el = document.getElementById(cond.target!) as HTMLInputElement | null;
    if (el) el.value = '';
  }
}

export function renderActiveConditions(): void {
  renderActiveConditionsImpl({
    activeConditions,
    CONDITIONS,
    PERIOD_PRESETS,
    conditionLabel: conditionLabel as (c: ConditionDef) => string,
    conditionPlaceholder: conditionPlaceholder as (c: ConditionDef) => string,
  });
}

export function hasCondition(key: string): boolean {
  return activeConditions.has(key);
}

export function activateCondition(key: string): void {
  if (!key || activeConditions.has(key)) return;
  activeConditions.add(key);
  renderActiveConditions();
  renderConditionMenu();
}

export function getActiveConditions(): string[] {
  return Array.from(activeConditions);
}

export function setActiveConditions(keys: string[]): void {
  activeConditions = new Set(Array.isArray(keys) ? keys : []);
  activeConditions.delete('limit');  // migrate old 'limit' key
  renderActiveConditions();
  renderConditionMenu();
}

export function getActiveSet(): Set<string> {
  return activeConditions;
}

export { CONDITIONS, PERIOD_PRESETS, resetConditionField };

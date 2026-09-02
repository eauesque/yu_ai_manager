import { triggerInstant } from '../search-results/search/live';
import { setSearchFromTs } from '../shared/runtime-state/search-period-state';
import { getConditionBuilderApi, getRuntimeInitApi } from '../shared/browser-apis';

export function setPeriodPreset(days: number, type: string, hours: number): void {
  const runtimeInitApi = getRuntimeInitApi();
  const conditionBuilderApi = getConditionBuilderApi();
  const today = new Date();
  let from: string, to: string;

  setSearchFromTs(null);

  if (type === 'lastMonth') {
    const d = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    from = d.toISOString().split('T')[0];
    const lastDay = new Date(today.getFullYear(), today.getMonth(), 0);
    to = lastDay.toISOString().split('T')[0];
  } else if (type === 'yesterday') {
    const y = new Date(today.getTime() - 86400000);
    from = y.toISOString().split('T')[0];
    to = y.toISOString().split('T')[0];
  } else if (hours) {
    const tsFrom = Math.floor((today.getTime() - hours * 3600000) / 1000);
    setSearchFromTs(String(tsFrom));
    from = new Date(today.getTime() - hours * 3600000).toISOString().split('T')[0];
    to = today.toISOString().split('T')[0];
  } else {
    from = new Date(today.getTime() - days * 86400000).toISOString().split('T')[0];
    to = today.toISOString().split('T')[0];
  }

  (document.getElementById('fromDate') as HTMLInputElement).value = from;
  (document.getElementById('toDate') as HTMLInputElement).value = to;
  runtimeInitApi.saveSearchState();
  conditionBuilderApi.renderActiveConditions();
  triggerInstant();
}

export function showCustomPeriod(): void {
  const el = document.getElementById('customPeriodFields');
  if (el) el.style.display = 'flex';
}

export function setResolutionPreset(minW: number, maxW: number, minH: number, maxH: number): void {
  const runtimeInitApi = getRuntimeInitApi();
  const conditionBuilderApi = getConditionBuilderApi();
  (document.getElementById('minWidth') as HTMLInputElement).value = minW ? String(minW) : '';
  (document.getElementById('maxWidth') as HTMLInputElement).value = maxW ? String(maxW) : '';
  (document.getElementById('minHeight') as HTMLInputElement).value = minH ? String(minH) : '';
  (document.getElementById('maxHeight') as HTMLInputElement).value = maxH ? String(maxH) : '';
  conditionBuilderApi.renderActiveConditions();
  runtimeInitApi.saveSearchState();
  triggerInstant();
}

export function toggleAccordion(id: string): void {
  const content = document.getElementById('accordion-content-' + id);
  const icon = document.getElementById('accordion-icon-' + id);
  if (!content || !icon) return;

  if (content.style.display === 'none') {
    content.style.display = 'block';
    icon.textContent = '▼';
    content.querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select').forEach(el => {
      el.disabled = false;
      el.style.opacity = '';
    });
  } else {
    content.style.display = 'none';
    icon.textContent = '▶';
    content.querySelectorAll<HTMLInputElement | HTMLSelectElement>('input, select').forEach(el => {
      el.disabled = true;
      el.value = '';
      el.style.opacity = '0.5';
    });
  }
}

export function toggleAdvancedSearch(): void {
  toggleAccordion('advanced');
}

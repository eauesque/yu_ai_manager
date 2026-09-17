/**
 * Search state persistence — clear helpers.
 */

import { saveSearchState } from './core';
import { getNavApi } from '../../shared/browser-apis';

function _undoClear(el: HTMLInputElement | HTMLSelectElement | null): void {
  if (!el) return;
  el.focus();
  if ('select' in el) (el as HTMLInputElement).select();
  document.execCommand('insertText', false, '');
}

export function clearInput(inputId: string): void {
  const el = document.getElementById(inputId) as HTMLInputElement | null;
  if (!el) return;
  _undoClear(el);
  saveSearchState();
}

export function clearAllInputs(): void {
  _undoClear(document.getElementById('tagQuery') as HTMLInputElement | null);
  _undoClear(document.getElementById('artist') as HTMLInputElement | null);
  _undoClear(document.getElementById('fromDate') as HTMLInputElement | null);
  _undoClear(document.getElementById('toDate') as HTMLInputElement | null);
  _undoClear(document.getElementById('inPrompt') as HTMLInputElement | null);
  _undoClear(document.getElementById('checkpointFilter') as HTMLInputElement | null);
  _undoClear(document.getElementById('inNegative') as HTMLInputElement | null);
  _undoClear(document.getElementById('inCharPositive') as HTMLInputElement | null);
  _undoClear(document.getElementById('inCharNegative') as HTMLInputElement | null);
  _undoClear(document.getElementById('inPath') as HTMLInputElement | null);
  _undoClear(document.getElementById('orTags') as HTMLInputElement | null);
  _undoClear(document.getElementById('minWidth') as HTMLInputElement | null);
  _undoClear(document.getElementById('maxWidth') as HTMLInputElement | null);
  _undoClear(document.getElementById('minHeight') as HTMLInputElement | null);
  _undoClear(document.getElementById('maxHeight') as HTMLInputElement | null);

  const fileFormat = document.getElementById('fileFormat') as HTMLSelectElement | null;
  if (fileFormat) fileFormat.value = 'all';
  const formatExts = document.getElementById('formatExts') as HTMLInputElement | null;
  if (formatExts) formatExts.value = '';
  document.querySelectorAll<HTMLInputElement>('input[data-format-ext]').forEach((el) => {
    el.checked = false;
  });
  const modelFilter = document.getElementById('modelFilter') as HTMLSelectElement | null;
  if (modelFilter) modelFilter.value = 'all';
  const wdModelFilter = document.getElementById('wdModelFilter') as HTMLSelectElement | null;
  if (wdModelFilter) wdModelFilter.value = '';
  const sortBy = document.getElementById('sortBy') as HTMLSelectElement | null;
  if (sortBy) sortBy.value = 'date_new';

  const inPromptRegex = document.getElementById('inPromptRegex') as HTMLInputElement | null;
  if (inPromptRegex) inPromptRegex.checked = false;
  const tagRegex = document.getElementById('tagRegex') as HTMLInputElement | null;
  if (tagRegex) tagRegex.checked = false;
  const tagCase = document.getElementById('tagCaseSensitive') as HTMLInputElement | null;
  if (tagCase) tagCase.checked = false;
  const regexToggle = document.getElementById('regexToggle') as HTMLInputElement | null;
  if (regexToggle) regexToggle.checked = false;

  const adv = document.getElementById('advancedConditions');
  if (adv) adv.style.display = 'none';

  saveSearchState();
  document.getElementById('tagQuery')?.focus();
  getNavApi().showToast(window.tr('toast.conditions_cleared'));
}

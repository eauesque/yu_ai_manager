/**
 * Search state persistence — autosave hooks.
 */

import { saveSearchState } from './core';
import { renderActiveConditions } from '../../condition-builder/state';

export function setupAutoSave(): void {
  let _saveTimer: ReturnType<typeof setTimeout> | null = null;
  const save = (): void => {
    if (_saveTimer) clearTimeout(_saveTimer);
    _saveTimer = setTimeout(() => { _saveTimer = null; saveSearchState(); }, 300);
  };
  const inputs = [
    'tagQuery',
    'artist',
    'fromDate',
    'toDate',
    'fileFormat',
    'formatExts',
    'modelFilter',
    'wdModelFilter',
    'checkpointFilter',
    'sortBy',
    'limit',
    'inPrompt',
    'inNegative',
    'inCharPositive',
    'inCharNegative',
    'inPath',
    'orTags',
    'minWidth',
    'maxWidth',
    'minHeight',
    'maxHeight',
  ];

  inputs.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('input', save);
    el.addEventListener('change', save);
    if (id === 'limit') {
      el.addEventListener('change', () => {
        renderActiveConditions();
      });
    }
  });

  ['inPromptRegex', 'tagRegex', 'tagCaseSensitive'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', save);
  });
}

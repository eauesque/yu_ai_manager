/**
 * Search state persistence — core save/restore operations.
 */

import { readStateFromDom, applyStateToDom } from './fields';
import { getConditionBuilderApi } from '../../shared/browser-apis';

export const SEARCH_STATE_KEY = 'tagdb_search_state';
export const SEARCH_COMMITTED_KEY = 'tagdb_search_committed';

// Cache the last-written JSON to skip redundant localStorage writes
let _lastWritten = '';

export function saveSearchState(): void {
  const conditionBuilderApi = getConditionBuilderApi();
  const state = readStateFromDom();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (state as any).advancedOpen = document.getElementById('accordion-content-advanced')?.style.display !== 'none';
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (state as any).activeConditions = conditionBuilderApi.getActiveConditions();

  try {
    const json = JSON.stringify(state);
    if (json === _lastWritten) return;
    _lastWritten = json;
    localStorage.setItem(SEARCH_STATE_KEY, json);
  } catch (e) {
    console.warn('Failed to save search state:', e);
  }
}

export function restoreSearchState(): boolean {
  const conditionBuilderApi = getConditionBuilderApi();
  try {
    const saved = localStorage.getItem(SEARCH_STATE_KEY);
    if (!saved) return false;

    const state = JSON.parse(saved);
    applyStateToDom(state);

    if (Array.isArray(state.activeConditions)) {
      conditionBuilderApi.setActiveConditions(state.activeConditions);
    }

    if (state.advancedOpen) {
      const advContent = document.getElementById('accordion-content-advanced');
      const advIcon = document.getElementById('accordion-icon-advanced');
      if (advContent) {
        advContent.style.display = 'block';
        if (advIcon) advIcon.textContent = '\u25BC';
        advContent.querySelectorAll('input, select').forEach((el) => {
          (el as HTMLInputElement | HTMLSelectElement).disabled = false;
          (el as HTMLElement).style.opacity = '';
        });
      }
      if (state.checkpointFilter) {
        const el = document.getElementById('checkpointFilter') as HTMLInputElement | null;
        if (el) el.value = state.checkpointFilter;
      }
    }

    return true;
  } catch (e) {
    console.warn('Failed to restore search state:', e);
    return false;
  }
}

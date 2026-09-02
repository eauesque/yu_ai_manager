/**
 * Search state persistence — field mapping helpers.
 * Reads/writes search form state from/to DOM elements.
 */

const VALUE_FIELDS: string[] = [
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

const CHECKBOX_FIELDS: string[] = ['inPromptRegex', 'tagRegex', 'tagCaseSensitive', 'aiAnalyzed', 'hasTags', 'hasAnnotation', 'hasSweep'];

export interface SearchFieldState {
  [key: string]: string | boolean;
}

export function readStateFromDom(): SearchFieldState {
  const state: SearchFieldState = {};
  VALUE_FIELDS.forEach((id) => {
    const el = document.getElementById(id) as HTMLInputElement | HTMLSelectElement | null;
    state[id] = el ? el.value : '';
  });
  CHECKBOX_FIELDS.forEach((id) => {
    const el = document.getElementById(id) as HTMLInputElement | null;
    state[id] = !!(el && el.checked);
  });
  return state;
}

export function applyStateToDom(state: SearchFieldState): void {
  VALUE_FIELDS.forEach((id) => {
    if (!state[id]) return;
    const el = document.getElementById(id) as HTMLInputElement | HTMLSelectElement | null;
    if (el) el.value = state[id] as string;
  });

  CHECKBOX_FIELDS.forEach((id) => {
    if (state[id] === undefined) return;
    const el = document.getElementById(id) as HTMLInputElement | null;
    if (el) el.checked = !!state[id];
  });
}

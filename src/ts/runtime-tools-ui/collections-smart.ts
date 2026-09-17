/**
 * collections-smart.ts -- Smart collections (saved searches) and UNION
 * multi-collection search. Split from collections-sidebar.ts.
 */

import { buildSearchParams, getSearchContext } from '../search-results/search/runner-context';
import {
  type CollectionRecord,
  _t,
  getListEl,
  getUnionBtn,
  getClearUnionBtn,
  setUnionBtn,
  setClearUnionBtn,
} from './collections-state';
import { loadSidebarCollections } from './collections-sidebar';
import { getRuntimeToolsUiHooks } from './hooks';
import { getAppApi, getUnionSearchApi } from '../shared/browser-apis';
import {
  clearUnionCheckedIds,
  getUnionCheckedCount,
  setUnionChecked,
} from '../shared/runtime-state/union-search-state';

// --- UNION multi-check ---
export function onUnionCheckChange(collId: number, checked: boolean): void {
  setUnionChecked(collId, checked);
  updateUnionBtnVisibility();
}

export function updateUnionBtnVisibility(): void {
  const count = getUnionCheckedCount();
  const unionBtn = getUnionBtn();
  const clearUnionBtn = getClearUnionBtn();
  if (unionBtn) unionBtn.style.display = count >= 2 ? '' : 'none';
  if (clearUnionBtn) clearUnionBtn.style.display = count >= 1 ? '' : 'none';
}

export function clearUnionChecks(): void {
  clearUnionCheckedIds();
  // Uncheck all checkboxes in sidebar
  const listEl = getListEl();
  if (listEl) {
    listEl.querySelectorAll<HTMLInputElement>('.cs-union-check').forEach((cb) => {
      cb.checked = false;
    });
  }
  updateUnionBtnVisibility();
}

/**
 * Create the UNION search button container element and register the
 * created buttons in shared state. Returns the container div for
 * insertion into the DOM by the caller.
 */
export function createUnionButtons(): HTMLDivElement {
  const btnContainer = document.createElement('div');
  btnContainer.className = 'cs-union-btns';

  const unionBtn = document.createElement('button');
  unionBtn.type = 'button';
  unionBtn.className = 'cs-union-btn';
  unionBtn.textContent = _t('collections.union_search', 'UNION Search');
  unionBtn.style.display = 'none';
  unionBtn.addEventListener('click', () => {
    void getUnionSearchApi().runUnionSearch();
  });
  btnContainer.appendChild(unionBtn);
  setUnionBtn(unionBtn);

  const clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.className = 'cs-union-clear-btn';
  clearBtn.textContent = _t('collections.union_clear', 'Clear');
  clearBtn.style.display = 'none';
  clearBtn.addEventListener('click', clearUnionChecks);
  btnContainer.appendChild(clearBtn);
  setClearUnionBtn(clearBtn);

  return btnContainer;
}

// --- Apply smart collection (restore saved query) ---
export function applySmartCollection(coll: CollectionRecord): void {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let params: Record<string, any>;
  try { params = JSON.parse(coll.query_json || '{}'); } catch (_e) { return; }

  // Map of query_json key -> form element ID
  const fieldMap: Record<string, string> = {
    q: 'tagQuery', artist: 'artist',
    from: 'fromDate', to: 'toDate',
    in_prompt: 'inPrompt', in_negative: 'inNegative',
    in_char_positive: 'inCharPositive', in_char_negative: 'inCharNegative',
    in_path: 'inPath',
    format: 'fileFormat', format_exts: 'formatExts',
    model_filter: 'modelFilter', checkpoint: 'checkpointFilter',
    sort: 'sortBy', limit: 'limit',
    min_width: 'minWidth', max_width: 'maxWidth',
    min_height: 'minHeight', max_height: 'maxHeight',
    or_tags: 'orTags',
  };

  // Reset collection filter so search runs without collection_id
  const collSel = document.getElementById('collectionFilter') as HTMLSelectElement | null;
  if (collSel) collSel.value = '';

  // Apply saved values to form fields
  Object.keys(fieldMap).forEach((key) => {
    const el = document.getElementById(fieldMap[key]) as HTMLInputElement | null;
    if (el) el.value = params[key] || '';
  });

  // Checkboxes
  const favEl = document.getElementById('favOnly') as HTMLInputElement | null;
  if (favEl) favEl.checked = params.fav_only === 'true';
  const caseEl = document.getElementById('tagCaseSensitive') as HTMLInputElement | null;
  if (caseEl) caseEl.checked = params.tag_case === 'true';

  // Regex toggle
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  if (params.tag_regex === 'true' && typeof (window as any)._regexEnabled !== 'undefined') {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any)._regexEnabled = true;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } else if (typeof (window as any)._regexEnabled !== 'undefined') {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any)._regexEnabled = false;
  }

  // Update active state in sidebar
  const listEl = getListEl();
  if (listEl) {
    const items = listEl.querySelectorAll('.cs-item');
    items.forEach((item) => { item.classList.remove('active'); });
    const target = listEl.querySelector('.cs-item[data-id="' + coll.id + '"]');
    if (target) target.classList.add('active');
  }

  // Run search
  getRuntimeToolsUiHooks().runSearch();
}

// --- Save current search as smart collection ---
function _getCurrentSearchParams(): Record<string, string> | null {
  if (
    typeof buildSearchParams !== 'function'
  ) {
    return null;
  }
  const ctx = getSearchContext();
  const params: URLSearchParams = buildSearchParams(ctx);
  // Remove transient params
  params.delete('offset');
  params.delete('collection_id');
  // Convert to plain object
  const obj: Record<string, string> = {};
  params.forEach((v: string, k: string) => { if (v) obj[k] = v; });
  return obj;
}

function _isSearchEmpty(params: Record<string, string> | null): boolean {
  if (!params) return true;
  const meaningfulKeys = [
    'q', 'artist', 'from', 'to', 'in_prompt', 'in_negative',
    'in_char_positive', 'in_char_negative', 'in_path', 'or_tags',
    'min_width', 'max_width', 'min_height', 'max_height',
  ];
  return !meaningfulKeys.some((k) => params[k]);
}

export async function saveCurrentSearch(): Promise<void> {
  const params = _getCurrentSearchParams();
  if (_isSearchEmpty(params)) {
    alert(_t('collections.save_search_empty', 'No search filters to save.'));
    return;
  }
  const name = prompt(_t('collections.save_search_name', 'Name for this smart collection:'));
  if (!name || !name.trim()) return;

  try {
    const response = await getAppApi().apiFetch('/api/collections', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim(), query_json: JSON.stringify(params) }),
    });
    if (!response.ok) return;
    loadSidebarCollections();
    getRuntimeToolsUiHooks().loadCollectionFilter();
  } catch (e) {
    console.error('saveCurrentSearch failed:', e);
  }
}

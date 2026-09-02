/**
 * union-search — Multi-collection UNION search.
 * Sends POST /api/search-union with checked collection IDs,
 * then renders merged results via existing handleSearchSuccess().
 */

import { handleSearchSuccess } from '../search-results/search/runner-results';
import { beginLoading, endLoading } from '../search-results/search/runner-context';
import { showSearchState, setResultsCountI18n, clearResultsCount } from '../search-results/search/state';
import { searchPager } from '../search-results/search/pagination';
import { getAppApi } from '../shared/browser-apis';
import { getUnionCheckedIds } from '../shared/runtime-state/union-search-state';
import { installWindowApi } from '../shared/window-api';

export async function runUnionSearch(): Promise<void> {
  const ids = getUnionCheckedIds();
  if (ids.length < 2) return;

  const sortEl = document.getElementById('sortBy') as HTMLSelectElement | null;
  const limitEl = document.getElementById('limit') as HTMLInputElement | null;
  const sort = sortEl?.value || 'date';
  const limit = parseInt(limitEl?.value || '200', 10) || 200;

  const loadingEls = beginLoading();

  try {
    const response = await getAppApi().apiFetch('/api/search-union', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ collection_ids: ids, sort, limit, offset: 0 }),
    });

    if (!response.ok) {
      let errMsg = `HTTP ${response.status}`;
      try {
        const errData = await response.json();
        errMsg = errData.error || errData.message || errMsg;
      } catch (_) { /* ignore */ }
      endLoading(loadingEls);
      showSearchState('error', errMsg);
      clearResultsCount();
      return;
    }

    const data = await response.json();
    endLoading(loadingEls);

    if (data.status === 'error') {
      showSearchState('error', data.message || 'UNION search failed');
      clearResultsCount();
      return;
    }

    if (!data.results || data.results.length === 0) {
      showSearchState('empty', null, true);
      setResultsCountI18n('search.count.zero');
      return;
    }

    const context = { queryInput: '', useRegex: false, tagCaseSensitive: false, inPromptValue: '' };
    handleSearchSuccess(data, context, new URLSearchParams());

    // Update pager for UNION results
    const totalCount: number = data.total_count || data.results.length;
    searchPager.setTotalCount(totalCount);
    setResultsCountI18n('search.count.normal', { count: totalCount }, ' (UNION)');
  } catch (error: unknown) {
    console.error('UNION search failed:', error);
    endLoading(loadingEls);
    showSearchState('error', error instanceof Error ? error.message : String(error));
    clearResultsCount();
  }
}

// Expose to window for sidebar button
installWindowApi('unionSearchApi', {
  runUnionSearch,
});

import {
  getSearchContext,
  ensureRegexConfirm,
  buildSearchParams,
  beginLoading,
  endLoading,
} from './runner-context';
import { handleSearchSuccess, handleFallbackSearch } from './runner-results';
import { showSearchState, setResultsCountI18n, clearResultsCount } from './state';
import { vsDeactivate } from '../results/virtual-scroll-bridge';
import { setLibraryQuery } from '../../runtime-pre/ui-state';
import { searchPager } from './pagination';
import { getAppApi } from '../../shared/browser-apis';
import { createPagePerfTracker } from '../../shared/page-perf';

/**
 * AbortController for the current search request.
 * When a new search starts, the previous request is cancelled
 * to prevent stale results from overwriting fresh ones and
 * to free up server resources on large databases.
 */
let _currentAbort: AbortController | null = null;
const _perf = createPagePerfTracker('search-actions');

export async function runSearch(e?: Event): Promise<void> {
  if (e) e.preventDefault();
  const { apiFetch, tr } = getAppApi();
  _perf.mark('search_request_start');

  const context = getSearchContext();
  if (!ensureRegexConfirm(context)) return;

  // Cancel any in-flight search request
  if (_currentAbort) {
    _currentAbort.abort();
    _currentAbort = null;
  }

  const params = buildSearchParams(context);
  searchPager.beginSearch(params);
  setLibraryQuery(params.toString());

  const loadingEls = beginLoading();
  const abort = new AbortController();
  _currentAbort = abort;

  try {
    const response = await apiFetch('/api/search?' + params, {
      signal: abort.signal,
    });
    _perf.mark('search_response_received');

    // If this request was superseded, discard silently but clean up UI
    if (abort.signal.aborted) {
      endLoading(loadingEls);
      return;
    }

    if (!response.ok) {
      let errMsg = `HTTP ${response.status}`;
      try {
        const errData = await response.json();
        errMsg = errData.message || errMsg;
      } catch (_) { /* ignore */ }
      endLoading(loadingEls);
      showSearchState('error', errMsg);
      clearResultsCount();
      _perf.mark('search_http_error');
      return;
    }

    const data = await response.json();
    _perf.mark('search_json_ready');
    if (data?.perf && typeof window !== 'undefined') {
      window.__yuPagePerf ||= {};
      window.__yuPagePerf['search-server'] = data.perf;
    }

    // Check again after parsing (another search may have started)
    if (abort.signal.aborted) {
      endLoading(loadingEls);
      return;
    }

    endLoading(loadingEls);

    if (data.status === 'error') {
      showSearchState('error', data.message || tr('search.error.generic'));
      clearResultsCount();
      _perf.mark('search_api_error');
      return;
    }

    const handled = handleSearchSuccess(data, context, params);
    if (handled.handled) {
      _perf.mark('search_success');
      return;
    }

    const fbData = await handleFallbackSearch(params);
    if (fbData) {
      _perf.mark('search_fallback');
      return;
    }

    // Stop the virtual-grid update loop before rendering the empty state.
    // Otherwise its scheduled update() repaints stale cards from the previous
    // (non-empty) search on top of the empty UI -- and clearing via
    // vsDisplayResults([]) would wipe the empty UI itself, because update()
    // calls innerHTML='' when rows===0.
    vsDeactivate();
    showSearchState('empty', null, data.has_conditions);
    setResultsCountI18n('search.count.zero', undefined, handled.regexNote || '');
    _perf.mark('search_empty');
  } catch (error: unknown) {
    // AbortError is expected when search is superseded -- clean up UI
    if (error instanceof DOMException && error.name === 'AbortError') {
      endLoading(loadingEls);
      return;
    }

    console.error('Search failed:', error);
    endLoading(loadingEls);
    const isNetworkError = error instanceof TypeError && (error as TypeError).message.includes('fetch');
    const errMessage = error instanceof Error ? error.message : String(error);
    showSearchState(
      'error',
      isNetworkError
        ? tr('search.error.network')
        : tr('search.error.failed', { message: errMessage }),
    );
    clearResultsCount();
    _perf.mark('search_exception');
  } finally {
    if (_currentAbort === abort) {
      _currentAbort = null;
    }
  }
}

import type { SearchPagerState } from './pagination-state';
import { appendResults } from '../results/render';
import { setResultsCountI18n } from './state';
import { getAppApi, getSearchResultsApi } from '../../shared/browser-apis';

export interface LoadMoreDeps {
  state: SearchPagerState;
  ui: {
    removeLoadMoreSentinel: () => void;
    observeCurrentSentinel: (observer: IntersectionObserver | null) => void;
    setSentinelLoading: (active: boolean) => void;
  };
  regexEnabledGetter: () => boolean;
  regexCompiler: (pattern: string) => { re: RegExp | null; error: string | null };
  regexApplier: (results: unknown[], re: RegExp) => unknown[];
  regexApplierAsync: (results: unknown[], re: RegExp) => Promise<unknown[]>;
  getScrollObserver: () => IntersectionObserver | null;
  showLoadMoreSentinel: () => void;
}

/** Prefetched next-page data, ready for instant display */
interface PrefetchedPage {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
  paramsKey: string;
}

export interface LoadMoreResult {
  loadMore: () => Promise<void>;
  prefetchNext: () => void;
  clearPrefetch: () => void;
}

export function createLoadMoreHandler(deps: LoadMoreDeps): LoadMoreResult {
  const {
    state,
    ui,
    regexEnabledGetter,
    regexCompiler,
    regexApplierAsync,
    getScrollObserver,
    showLoadMoreSentinel,
  } = deps;

  /** Buffer for prefetched next page */
  let _prefetched: PrefetchedPage | null = null;
  let _prefetching = false;

  /** Build search params key for cache matching */
  function _paramsKey(): string {
    const p = state.getParams();
    const cursor = state.getCursor();
    return (p ? p.toString() : '') + '|cursor=' + (cursor || '') + '|off=' + state.getOffset();
  }

  /** Prefetch the next page in background */
  async function _prefetchNext(): Promise<void> {
    if (_prefetching || !state.getHasMore() || !state.getParams()) return;
    _prefetching = true;
    const { apiFetch } = getAppApi();

    const params = new URLSearchParams(state.getParams()!);
    const cursor = state.getCursor();
    if (cursor) {
      params.set('cursor', cursor);
      params.delete('offset');
    } else {
      params.set('offset', String(state.getOffset()));
    }

    const key = _paramsKey();

    try {
      const response = await apiFetch('/api/search?' + params);
      if (!response.ok) return;
      const data = await response.json();
      // Only store if search context hasn't changed
      if (state.getParams() && _paramsKey() === key) {
        _prefetched = { data, paramsKey: key };
      }
    } catch {
      // Prefetch failure is non-critical
    } finally {
      _prefetching = false;
    }
  }

  /** Invalidate prefetch buffer (called on new search) */
  function _clearPrefetch(): void {
    _prefetched = null;
    _prefetching = false;
  }

  async function loadMore(): Promise<void> {
    if (state.isLoading() || !state.getHasMore() || !state.getParams()) return;
    state.setLoading(true);
    ui.setSentinelLoading(true);
    const { apiFetch, tr } = getAppApi();

    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let data: any;

      // Check prefetch buffer first (instant — no network wait)
      const key = _paramsKey();
      if (_prefetched && _prefetched.paramsKey === key) {
        data = _prefetched.data;
        _prefetched = null;
      } else {
        // No prefetch hit — fetch synchronously
        _prefetched = null;
        const params = new URLSearchParams(state.getParams()!);
        const cursor = state.getCursor();
        if (cursor) {
          params.set('cursor', cursor);
          params.delete('offset');
        } else {
          params.set('offset', String(state.getOffset()));
        }

        const response = await apiFetch('/api/search?' + params);
        if (!response.ok) {
          return;
        }
        data = await response.json();
      }

      if (!data.results || data.results.length === 0) {
        state.setHasMore(false);
        ui.removeLoadMoreSentinel();
        return;
      }

      let newResults = data.results;
      const inPromptEl = document.getElementById('inPrompt') as HTMLInputElement | null;
      const useRegex = regexEnabledGetter() && !!(inPromptEl?.value);
      if (useRegex) {
        const tagQueryEl = document.getElementById('tagQuery') as HTMLInputElement | null;
        const { re } = regexCompiler(tagQueryEl?.value || '');
        if (re) newResults = await regexApplierAsync(newResults, re);
      }

      ui.removeLoadMoreSentinel();
      appendResults(newResults);
      // Export buffer: accumulate up to EXPORT_MAX so export doesn't need to re-fetch.
      // Calls via runtime bridge (window.searchResultsApi) to avoid circular import:
      // pagination-load-more -> export -> pagination
      getSearchResultsApi().accumExportData?.(newResults);

      state.addOffset(data.results.length);
      state.setHasMore(data.has_more);
      state.setCursor(data.next_cursor || null);
      // Cursor pages return a placeholder total_count when count_pending=true
      // (see search_response.py — server skips COUNT(*) on cursor queries
      // because the total can't change between pages). Don't overwrite the
      // accurate count obtained on page 1.
      if (data.total_count && !data.count_pending) state.setTotalCount(data.total_count);
      const displayTotal = state.getTotalCount() || state.getOffset();
      setResultsCountI18n('search.count.normal', { count: displayTotal }, useRegex ? tr('search.regex_note') : '');

      if (state.getHasMore()) {
        showLoadMoreSentinel();
        ui.observeCurrentSentinel(getScrollObserver());
        // Immediately start prefetching the NEXT page
        // so it's ready before the user scrolls down
        _prefetchNext();
      }
    } catch (err) {
      console.error('loadMore failed:', err);
    } finally {
      state.setLoading(false);
      ui.setSentinelLoading(false);
    }
  }

  return {
    loadMore,
    prefetchNext: () => { _prefetchNext(); },
    clearPrefetch: _clearPrefetch,
  };
}

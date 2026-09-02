import { _regexEnabled, compileUserRegex, applyClientRegexFilter, type SearchResult } from './core';
import { displayResults } from '../results/render';
import { showSearchState, setResultsCountI18n, clearResultsCount } from './state';
import { searchPager } from './pagination';
import { rgState } from '../results/grouping-utils';
import { addCondition } from '../../condition-builder/condition-actions';
import { runSearch } from './runner-core';
import { getAppApi, getRuntimeInitApi, getSearchResultsApi } from '../../shared/browser-apis';
import { createPagePerfTracker } from '../../shared/page-perf';
import {
  makeSearchCountKey,
  maybeWarmFirstResultMetadata,
  maybeWarmGroupedSearch,
  persistSearchState,
  scheduleExactCountRefresh,
  scheduleSearchPostPaint,
} from './runner-results-warm';

interface SearchContext {
  queryInput: string;
  useRegex: boolean;
  tagCaseSensitive: boolean;
  inPromptValue: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ResultRecord = Record<string, any>;

interface SearchData {
  results: ResultRecord[];
  total_count?: number;
  count_pending?: boolean;
  has_more: boolean;
  has_conditions?: boolean;
  path_search_active?: boolean;
  next_cursor?: string | null;
}

interface HandleResult {
  handled: boolean;
  empty?: boolean;
  regexNote?: string;
}

const _perf = createPagePerfTracker('search-actions');
let _lastGroupedWarmKey = '';

export async function handleFallbackSearch(params: URLSearchParams): Promise<SearchData | null> {
  const appApi = getAppApi();
  const searchResultsApi = getSearchResultsApi();
  const tagQueryEl = document.getElementById('tagQuery') as HTMLInputElement | null;
  const mainQuery = tagQueryEl?.value.trim() || '';
  if (!mainQuery || params.get('_fallback')) return null;

  const fbParams = new URLSearchParams(params);
  fbParams.set('q', '');
  fbParams.set('in_prompt', mainQuery);
  fbParams.set('tag_regex', 'false');
  fbParams.set('in_prompt_regex', 'false');
  fbParams.set('_fallback', '1');
  fbParams.set('offset', '0');

  const fbResponse = await appApi.apiFetch('/api/search?' + fbParams);
  if (!fbResponse.ok) return null;

  const fbData = await fbResponse.json();
  if (!fbData.results || fbData.results.length === 0) return null;

  displayResults(fbData.results);
  _perf.mark('results_painted');
  searchResultsApi.setExportData(fbData.results);
  const fbTotal: number = fbData.total_count || fbData.results.length;
  setResultsCountI18n('search.count.prompt_match', { count: fbTotal });
  searchPager.beginSearch(fbParams);
  searchPager.setTotalCount(fbTotal);
  searchPager.setOffset(fbData.results.length);
  searchPager.setHasMore(fbData.has_more);
  searchPager.setCursor(fbData.next_cursor || null);
  scheduleSearchPostPaint(() => {
    _perf.markOnce('post_paint_work_started');
    searchPager.setupScrollObserver();
    if (fbData.has_more) {
      searchPager.showLoadMoreSentinel();
      searchPager.prefetchNext();
    }
  }, 900);
  scheduleSearchPostPaint(() => {
    _lastGroupedWarmKey = maybeWarmGroupedSearch(fbParams, _lastGroupedWarmKey);
  }, 240);
  scheduleSearchPostPaint(() => {
    maybeWarmFirstResultMetadata(fbData.results);
  }, 320);
  if (fbData.count_pending) {
    scheduleExactCountRefresh(fbParams, makeSearchCountKey(fbParams), 'search.count.prompt_match');
  }
  return fbData;
}

function showPathSearchTip(query: string): void {
  const tip = document.getElementById('searchPathTip');
  if (!tip) return;
  const _t = typeof window.tr === 'function' ? window.tr : (_k: string, f?: string) => f || '';
  const { escapeHtml } = getAppApi();
  tip.innerHTML = '<span>' + escapeHtml(_t('search.path_tip.message',
    'Searching both tag names and file/folder names. For precise results, use "Add condition" \u2192 "Folder".'))
    + '</span>'
    + '<button type="button" class="spt-btn" id="sptMoveBtn">'
    + escapeHtml(_t('search.path_tip.move_btn', '\ud83d\udcc2 Move to folder search'))
    + '</button>';
  tip.style.display = '';
  document.getElementById('sptMoveBtn')?.addEventListener('click', () => {
    moveQueryToFolderCondition(query);
  });
}

function hidePathSearchTip(): void {
  const tip = document.getElementById('searchPathTip');
  if (tip) tip.style.display = 'none';
}

function moveQueryToFolderCondition(query: string): void {
  if (addCondition) {
    addCondition('inFolder');
  }
  const inPath = document.getElementById('inPath') as HTMLInputElement | null;
  if (inPath) inPath.value = query;
  const tagQuery = document.getElementById('tagQuery') as HTMLInputElement | null;
  if (tagQuery) tagQuery.value = '';
  hidePathSearchTip();
  runSearch();
}

export function handleSearchSuccess(data: SearchData, context: SearchContext, params: URLSearchParams): HandleResult {
  const appApi = getAppApi();
  const runtimeInitApi = getRuntimeInitApi();
  const searchResultsApi = getSearchResultsApi();
  let finalResults = data.results;
  let regexNote = '';

  if (_regexEnabled && context.inPromptValue) {
    const tagQueryEl = document.getElementById('tagQuery') as HTMLInputElement | null;
    const { re, error } = compileUserRegex(tagQueryEl?.value || '');
    if (error) {
      showSearchState('error', appApi.tr('search.error.regex', { error }));
      clearResultsCount();
      return { handled: true };
    }
    finalResults = applyClientRegexFilter(data.results as SearchResult[], re) as ResultRecord[];
    regexNote = appApi.tr('search.regex_note');
  }

  if (finalResults.length === 0) {
    hidePathSearchTip();
    return { handled: false, empty: true, regexNote };
  }

  displayResults(finalResults);
  _perf.mark('results_painted');
  searchResultsApi.setExportData(finalResults);
  // Cursor-paginated requests defer the COUNT(*) on the server to save ~500ms.
  // The total count cannot have changed between pages of the same search, so
  // we keep whatever the pager already has from page 1 instead of overwriting
  // it with the server's placeholder.
  const isCursorPage = params.has('cursor') || (params.get('offset') || '0') !== '0';
  if (!(isCursorPage && data.count_pending)) {
    const totalCount = data.total_count || finalResults.length;
    searchPager.setTotalCount(totalCount);
    setResultsCountI18n('search.count.normal', { count: totalCount }, regexNote);
  }
  // Reset saved file count so grouped view picks up the fresh value
  rgState.savedFileCount = null;

  const tagQueryEl = document.getElementById('tagQuery') as HTMLInputElement | null;
  const mainQuery = tagQueryEl ? tagQueryEl.value.trim() : '';
  if (data.path_search_active && mainQuery && finalResults.length > 0) {
    showPathSearchTip(mainQuery);
  } else {
    hidePathSearchTip();
  }

  searchPager.setOffset(data.results.length);
  searchPager.setHasMore(data.has_more);
  searchPager.setCursor(data.next_cursor || null);
  scheduleSearchPostPaint(() => {
    _perf.markOnce('post_paint_work_started');
    searchPager.setupScrollObserver();
    if (data.has_more) {
      searchPager.showLoadMoreSentinel();
      searchPager.prefetchNext();
    }
  }, 900);
  scheduleSearchPostPaint(() => {
    _lastGroupedWarmKey = maybeWarmGroupedSearch(params, _lastGroupedWarmKey);
  }, 240);
  scheduleSearchPostPaint(() => {
    maybeWarmFirstResultMetadata(finalResults);
  }, 320);
  // Skip the count refresh on cursor pages — running the same count_sql twice
  // wastes DB I/O and the count is already known from page 1.
  if (data.count_pending && !isCursorPage) {
    scheduleExactCountRefresh(params, makeSearchCountKey(params), 'search.count.normal', regexNote);
  }

  const savedScrollY = sessionStorage.getItem('scrollY');
  if (savedScrollY) {
    const scrollVal = parseInt(savedScrollY, 10);
    if (scrollVal > 100) {
      requestAnimationFrame(() => {
        window.scrollTo(0, scrollVal);
      });
    }
    // Always remove even if scrollY is small (leaving it causes false isPageReturn detection on next load)
    sessionStorage.removeItem('scrollY');
  } else if (window.innerWidth <= 768) {
    // Mobile new search: scroll past search criteria area to results
    requestAnimationFrame(() => {
      const anchor = document.getElementById('resultsCount');
      if (anchor) anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  persistSearchState();

  return { handled: true };
}

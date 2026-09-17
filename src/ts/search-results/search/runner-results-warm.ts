import { searchPager } from './pagination';
import { getAppApi, getRuntimeInitApi, getSearchResultsApi } from '../../shared/browser-apis';
import { setResultsCountI18n } from './state';
import { warmMetadata } from '../../detail-modal/runtime/metadata-prefetch';

export function scheduleAfterPaint(task: () => void): void {
  requestAnimationFrame(() => {
    requestAnimationFrame(task);
  });
}

export function scheduleVisibleIdle(task: () => void, timeout = 1200): void {
  const run = (): void => {
    if (document.hidden) return;
    task();
  };
  scheduleAfterPaint(() => {
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(run, { timeout });
      return;
    }
    setTimeout(run, 180);
  });
}

export function scheduleSearchPostPaint(task: () => void, timeout = 1200): void {
  scheduleVisibleIdle(task, timeout);
}

export function makeGroupedWarmKey(params: URLSearchParams): string {
  const normalized = new URLSearchParams(params);
  ['offset', 'limit', 'cursor', 'sort', '_fallback'].forEach((key) => normalized.delete(key));
  return Array.from(normalized.entries())
    .sort(([ak, av], [bk, bv]) => ak.localeCompare(bk) || av.localeCompare(bv))
    .map(([k, v]) => `${k}=${v}`)
    .join('&');
}

export function makeSearchCountKey(params: URLSearchParams): string {
  const normalized = new URLSearchParams(params);
  ['offset', 'limit', 'cursor', 'sort', 'defer_count', 'perf', '_fallback'].forEach((key) => normalized.delete(key));
  return Array.from(normalized.entries())
    .sort(([ak, av], [bk, bv]) => ak.localeCompare(bk) || av.localeCompare(bv))
    .map(([k, v]) => `${k}=${v}`)
    .join('&');
}

export function maybeWarmGroupedSearch(params: URLSearchParams, lastKey: string): string {
  const warmKey = makeGroupedWarmKey(params);
  if (!warmKey || warmKey === lastKey) return lastKey;
  const warmParams = new URLSearchParams(params);
  warmParams.delete('offset');
  warmParams.delete('cursor');
  fetch(getAppApi().apiUrl('/api/search-grouped/warm?' + warmParams), {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  }).catch(() => {});
  return warmKey;
}

export function maybeWarmFirstResultMetadata(results: Array<Record<string, unknown>>): void {
  const firstId = Number(results?.[0]?.id || 0);
  if (firstId > 0) warmMetadata(firstId);
}

export function scheduleExactCountRefresh(params: URLSearchParams, countKey: string, countLabelKey: string, suffix = ''): void {
  const countParams = new URLSearchParams(params);
  ['offset', 'cursor', 'limit', 'defer_count'].forEach((key) => countParams.delete(key));
  scheduleSearchPostPaint(() => {
    fetch(getAppApi().apiUrl('/api/search-count?' + countParams), { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then((r) => r.ok ? r.json() : null)
      .then((data: { total_count?: number } | null) => {
        if (!data || !Number.isFinite(data.total_count)) return;
        const current = searchPager.getParams();
        if (!current || makeSearchCountKey(current) !== countKey) return;
        searchPager.setTotalCount(Number(data.total_count) || 0);
        setResultsCountI18n(countLabelKey, { count: Number(data.total_count) || 0 }, suffix);
      })
      .catch(() => {});
  }, 420);
}

export function persistSearchState(): void {
  const runtimeInitApi = getRuntimeInitApi();
  if (!runtimeInitApi.saveSearchState) return;
  scheduleSearchPostPaint(() => {
    runtimeInitApi.saveSearchState?.();
    try {
      const cur = localStorage.getItem('tagdb_search_state') || '';
      if (cur !== localStorage.getItem('tagdb_search_committed')) {
        localStorage.setItem('tagdb_search_committed', cur);
      }
    } catch {
      // ignore
    }
  }, 1500);
}

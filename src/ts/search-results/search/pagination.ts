import { createSearchPagerState } from './pagination-state';
import {
  showLoadMoreSentinel as showLoadMoreSentinelImpl,
  setupScrollObserver as setupScrollObserverImpl,
  removeLoadMoreSentinel,
  observeCurrentSentinel,
  setSentinelLoading,
} from './pagination-ui';
import { createLoadMoreHandler } from './pagination-load-more';

const state = createSearchPagerState();

let scrollObserver: IntersectionObserver | null = null;
let regexEnabledGetter: () => boolean = () => false;
let regexCompiler: (pattern: string) => { re: RegExp | null; error: string | null } = () => ({ re: null, error: null });
let regexApplier: (results: unknown[], re: RegExp) => unknown[] = (results) => results;
let regexApplierAsync: ((results: unknown[], re: RegExp) => Promise<unknown[]>) | null = null;

function configure(opts: {
  isRegexEnabled?: () => boolean;
  compileRegex?: (pattern: string) => { re: RegExp | null; error: string | null };
  applyRegexFilter?: (results: unknown[], re: RegExp) => unknown[];
  applyRegexFilterAsync?: (results: unknown[], re: RegExp) => Promise<unknown[]>;
} = {}): void {
  if (typeof opts.isRegexEnabled === 'function') regexEnabledGetter = opts.isRegexEnabled;
  if (typeof opts.compileRegex === 'function') regexCompiler = opts.compileRegex;
  if (typeof opts.applyRegexFilter === 'function') regexApplier = opts.applyRegexFilter;
  if (typeof opts.applyRegexFilterAsync === 'function') regexApplierAsync = opts.applyRegexFilterAsync;
}

function beginSearch(params: URLSearchParams | null): void {
  state.beginSearch(params);
  _handler.clearPrefetch();
  // Drop any leftover load-more sentinel from the previous search. Without
  // this, an empty (or no-more) result keeps the prior search's spinner
  // visible because nothing else clears it on the empty path.
  removeLoadMoreSentinel();
}

function setOffset(v: number): void {
  state.setOffset(v);
}

function setHasMore(v: boolean): void {
  state.setHasMore(v);
}

function getHasMore(): boolean {
  return state.getHasMore();
}

function isLoading(): boolean {
  return state.isLoading();
}

function showLoadMoreSentinel(): void {
  showLoadMoreSentinelImpl();
}

function setupScrollObserver(): void {
  scrollObserver = setupScrollObserverImpl(scrollObserver, state, _handler.loadMore);
}

function teardownScrollObserver(): void {
  if (scrollObserver) {
    scrollObserver.disconnect();
    scrollObserver = null;
  }
  removeLoadMoreSentinel();
}

const _handler = createLoadMoreHandler({
  state,
  ui: { removeLoadMoreSentinel, observeCurrentSentinel, setSentinelLoading },
  regexEnabledGetter: () => regexEnabledGetter(),
  regexCompiler: (q: string) => regexCompiler(q),
  regexApplier: (results: unknown[], re: RegExp) => regexApplier(results, re),
  regexApplierAsync: (results: unknown[], re: RegExp) =>
    regexApplierAsync ? regexApplierAsync(results, re) : Promise.resolve(regexApplier(results, re)),
  getScrollObserver: () => scrollObserver,
  showLoadMoreSentinel,
});

function setTotalCount(v: number): void {
  state.setTotalCount(v);
}

export const searchPager = {
  configure,
  beginSearch,
  setOffset,
  setHasMore,
  getHasMore,
  isLoading,
  showLoadMoreSentinel,
  setupScrollObserver,
  teardownScrollObserver,
  loadMore: _handler.loadMore,
  prefetchNext: _handler.prefetchNext,
  setTotalCount,
  setCursor: (v: string | null): void => { state.setCursor(v); },
  getParams: (): URLSearchParams | null => state.getParams(),
  getTotalCount: (): number => state.getTotalCount(),
};

export function modalDetailHasMore(): boolean {
  return !!state.getHasMore();
}

export function modalDetailIsLoading(): boolean {
  return !!state.isLoading();
}

export function modalDetailLoadMore(): Promise<void> {
  return _handler.loadMore();
}

window.addEventListener('pagehide', teardownScrollObserver);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) teardownScrollObserver();
});

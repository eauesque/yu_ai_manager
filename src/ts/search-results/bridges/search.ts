import { searchPager, modalDetailHasMore, modalDetailIsLoading, modalDetailLoadMore } from '../search/pagination';
import { loadStats, setSearchMode, onRegexToggleChange } from '../search/core';
import { showSearchState, showPartialWarning, MAX_DOM_CARDS } from '../search/state';
import { runSearch as _origRunSearch } from '../search/runner-core';
import * as live from '../search/live';

let _semanticModulePromise: Promise<typeof import('../../semantic-search')> | null = null;

function _loadSemanticSearch() {
  if (!_semanticModulePromise) {
    _semanticModulePromise = import('../../semantic-search');
  }
  return _semanticModulePromise;
}

/** Wrapper that intercepts search for semantic mode. */
async function runSearch(e?: Event): Promise<void> {
  if (e) e.preventDefault();
  const handled = await _loadSemanticSearch().then((mod) => mod.trySemanticSearch()).catch(() => false);
  if (handled) return;
  return _origRunSearch(e);
}

function onSemanticToggleChange(): void {
  void _loadSemanticSearch().then((mod) => mod.onSemanticToggleChange()).catch(() => {});
}

export function createSearchResultsSearchBridgeApi() {
  return {
    searchPager,
    modalDetailHasMore,
    modalDetailIsLoading,
    modalDetailLoadMore,
    setSearchMode,
    onRegexToggleChange,
    onSemanticToggleChange,
    loadStats,
    showSearchState,
    showPartialWarning,
    maxDomCards: MAX_DOM_CARDS,
    runSearch,
    toggleLiveSearch: live.toggleLiveSearch,
  };
}

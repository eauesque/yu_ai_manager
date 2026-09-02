// Search
import './search/pagination-state';
import './search/pagination-ui';
import './search/pagination-load-more';
import { searchPager, modalDetailHasMore, modalDetailIsLoading, modalDetailLoadMore } from './search/pagination';
import {
  loadStats, setSearchMode, onRegexToggleChange, initSearchCore,
} from './search/core';
import { showSearchState, showPartialWarning, MAX_DOM_CARDS, setResultsCountI18n, clearResultsCount } from './search/state';
import { runSearch } from './search/runner-core';
import * as live from './search/live';

// Results
import {
  getResultCards, estimateCardsPerRow, focusResultCardByIndex,
  setupResultCardA11y, ensureSingleTabstopOnResultCards, announceResultCardStatus,
} from './results/a11y';
import { initNavButtonsOnDemand } from './results/nav';
import './results/render-card';
import { getMode, setMode } from './results/grouping-utils';
import { installWindowApi } from '../shared/window-api';
import { createSearchResultsBridgeApi } from './bridges/index';
import { setRuntimeResultsGrouping } from '../shared/runtime-state/results-grouping-state';
import { createPagePerfTracker } from '../shared/page-perf';

const _perf = createPagePerfTracker('search-results');
let _liveSearchInitialized = false;

const searchResultsApi = installWindowApi('searchResultsApi', createSearchResultsBridgeApi(), {
  modalDetailHasMore: 'modalDetailHasMore',
  modalDetailIsLoading: 'modalDetailIsLoading',
  modalDetailLoadMore: 'modalDetailLoadMore',
  setSearchMode: 'setSearchMode',
  onRegexToggleChange: 'onRegexToggleChange',
  loadStats: 'loadStats',
  showSearchState: 'showSearchState',
  showPartialWarning: 'showPartialWarning',
  MAX_DOM_CARDS,
  toggleLiveSearch: 'toggleLiveSearch',
  setupResultCardA11y: 'setupResultCardA11y',
  ensureSingleTabstopOnResultCards: 'ensureSingleTabstopOnResultCards',
  announceResultCardStatus: 'announceResultCardStatus',
  _appendResults: 'appendResults',
  updateExportCsvVisibility: 'updateExportCsvVisibility',
  updateExportCsvLabel: 'updateExportCsvLabel',
  exportResultsCsv: 'exportResultsCsv',
  exportResultsRecipeJson: 'exportResultsRecipeJson',
  setCsvLimit: 'setCsvLimit',
  showCsvLimitDropdown: 'showCsvLimitDropdown',
});

setRuntimeResultsGrouping(searchResultsApi.runtimeResultsGrouping);

let _groupingModulePromise: Promise<typeof import('./results/grouping')> | null = null;

function _loadGrouping() {
  if (!_groupingModulePromise) {
    _groupingModulePromise = import('./results/grouping');
  }
  return _groupingModulePromise;
}

function _renderGroupingBootstrap(): void {
  const root = document.getElementById('resultsGroupControls');
  if (!root || root.dataset.bootstrapReady === '1') return;
  root.dataset.bootstrapReady = '1';
  const tr = typeof window.tr === 'function' ? window.tr : ((_k: string, f?: string) => f || '');
  root.innerHTML =
    '<button type="button" class="rg-btn active" data-mode="all">' + tr('grouping.btn_files', 'Files') + '</button>' +
    '<button type="button" class="rg-btn" data-mode="folder">' + tr('grouping.btn_folders', 'Folders') + '</button>' +
    '<button type="button" class="rg-btn" data-mode="zip">' + tr('grouping.btn_archive', 'Archive') + '</button>' +
    '<button type="button" class="rg-btn rg-btn-refresh" id="rgRefreshBtn" title="' + tr('grouping.rebuild', 'Rebuild groups') + '">\u21BB</button>';

  root.addEventListener('click', (e: Event) => {
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>('[data-mode]');
    if (!btn || btn.disabled) return;
    const mode = btn.dataset.mode || 'all';
    if (mode === 'all') {
      setMode('all');
      root.querySelectorAll<HTMLButtonElement>('[data-mode]').forEach((node) => {
        node.classList.toggle('active', node === btn);
      });
      return;
    }
    setMode(mode);
    _perf.mark('grouping_requested');
    void _loadGrouping().then((mod) => {
      searchResultsApi.runtimeResultsGrouping = {
        applyToCurrentResults: mod.applyToCurrentResults,
        getOrderedGroups: mod.getOrderedGroups,
        getAdjacentGroupIds: mod.getAdjacentGroupIds,
      };
      setRuntimeResultsGrouping(searchResultsApi.runtimeResultsGrouping);
      mod.applyToCurrentResults();
      _perf.markOnce('grouping_ready');
    }).catch(() => {});
  });
}

function _scheduleVisibleIdle(task: () => void, timeout = 2500): void {
  const run = (): void => {
    if (document.hidden) return;
    task();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      if ('requestIdleCallback' in window) {
        window.requestIdleCallback(run, { timeout });
      } else {
        setTimeout(run, 1200);
      }
    }, { once: true });
    return;
  }

  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(run, { timeout });
    return;
  }

  setTimeout(run, 1200);
}

function _scheduleIdleGroupingLoad(): void {
  if (getMode() === 'all') return;
  const run = (): void => {
    if (document.hidden) return;
    void _loadGrouping().then((mod) => {
      searchResultsApi.runtimeResultsGrouping = {
        applyToCurrentResults: mod.applyToCurrentResults,
        getOrderedGroups: mod.getOrderedGroups,
        getAdjacentGroupIds: mod.getAdjacentGroupIds,
      };
      setRuntimeResultsGrouping(searchResultsApi.runtimeResultsGrouping);
      _perf.markOnce('grouping_ready');
    }).catch(() => {});
  };

  _scheduleVisibleIdle(run);
}

function _bootstrapLiveSearch(): void {
  if (_liveSearchInitialized) return;
  _liveSearchInitialized = true;
  live.initLiveSearch();
  _perf.markOnce('live_ready');
}

function _installLiveSearchBootstrap(): void {
  const bind = (el: HTMLElement | null, eventName: string): void => {
    if (!el) return;
    el.addEventListener(eventName, _bootstrapLiveSearch, { once: true, passive: true });
  };

  bind(document.getElementById('tagQuery'), 'focus');
  bind(document.getElementById('tagQuery'), 'pointerdown');
  bind(document.getElementById('regexToggle'), 'change');
  bind(document.getElementById('conditionFields'), 'pointerdown');
}

/* ── Init ── */
initSearchCore();
_perf.markOnce('module_ready');
_renderGroupingBootstrap();
_installLiveSearchBootstrap();
_scheduleVisibleIdle(() => {
  initNavButtonsOnDemand(() => {
    _perf.markOnce('nav_ready');
  });
});
_scheduleIdleGroupingLoad();

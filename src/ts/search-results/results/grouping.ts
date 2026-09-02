/**
 * results/grouping.ts
 *
 * Main grouping entry point: UI setup, mode switching,
 * applyToCurrentResults(), cross-group navigation.
 *
 * Sub-modules:
 *   grouping-cards.ts  — container card DOM operations + member cache
 *   grouping-search.ts — server-side grouped search + render
 */

import { rgState as S, MODES, getMode, setMode, type OrderedGroup } from './grouping-utils';
import { setGroupButtonsDisabled, startBackgroundPreload, rebuildGroups } from './grouping-preload';
import { renderConditionMenu } from '../../condition-builder/menu-core';
import { getViewerScope, setScopeResultIds } from '../../runtime-pre/ui-state';
import { searchPager } from '../search/pagination';
import { restoreCard, type ContainerCard, type ContainerGroupInfo } from './grouping-cards';
import { fetchAndApplyGroupedResults, cancelGroupedSearch } from './grouping-search';
import { vsDeactivate, isVirtualScrollActive, vsGetAllIds } from './virtual-scroll-bridge';
import { getAppApi } from '../../shared/browser-apis';

// Re-export everything external consumers need
export { restoreCard, replaceWithContainerCard, onContainerClick, getMemberCache, setMemberCacheEntry, clearMemberCache } from './grouping-cards';
export type { ContainerGroupInfo, ContainerCard } from './grouping-cards';
export { fetchAndApplyGroupedResults, cancelGroupedSearch } from './grouping-search';
export type { GroupedSearchGroup, GroupedSearchData } from './grouping-search';

declare const window: Window & {
  tr: (key: string, fallback?: string) => string;
  apiUrl: (path: string) => string;
  showDetail?: (id: number, opts: Record<string, unknown>) => void;
  updateExportCsvVisibility?: () => void;
  runtimeResultsGrouping?: {
    applyToCurrentResults?: () => number[];
  };
  runtimeResultsRenderCard: {
    buildContainerCardInnerHtml: (groupInfo: ContainerGroupInfo) => string;
  };
};

/* ---- UI setup ---- */

function _scheduleAfterPaint(task: () => void): void {
  requestAnimationFrame(() => {
    requestAnimationFrame(task);
  });
}

function _scheduleVisibleIdle(task: () => void, timeout = 900): void {
  const run = (): void => {
    if (document.hidden) return;
    task();
  };

  _scheduleAfterPaint(() => {
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(run, { timeout });
      return;
    }
    setTimeout(run, 120);
  });
}

function _ensureUi(): void {
  const root = document.getElementById('resultsGroupControls');
  if (!root || root.dataset.ready === '1') return;
  root.dataset.ready = '1';
  const _t = typeof window.tr === 'function' ? window.tr : function (_k: string, f?: string) { return f || ''; };
  root.innerHTML =
    '<button type="button" class="rg-btn" data-mode="all">' + _t('grouping.btn_files', 'Files') + '</button>' +
    '<button type="button" class="rg-btn" data-mode="folder">' + _t('grouping.btn_folders', 'Folders') + '</button>' +
    '<button type="button" class="rg-btn" data-mode="zip">' + _t('grouping.btn_archive', 'Archive') + '</button>' +
    '<button type="button" class="rg-btn rg-btn-refresh" id="rgRefreshBtn" title="' + _t('grouping.rebuild', 'Rebuild groups') + '">\u21BB</button>';
  root.addEventListener('click', function (e) {
    const btn = (e.target as HTMLElement).closest<HTMLButtonElement>('[data-mode]');
    if (!btn || btn.disabled) return;
    setMode(btn.dataset.mode!);
    applyToCurrentResults();
    // Re-render condition menu if open so greyed-out state updates in real-time
    _scheduleVisibleIdle(() => {
      renderConditionMenu();
    }, 1200);
  });
  const refreshBtn = document.getElementById('rgRefreshBtn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      rebuildGroups();
    });
  }
}

function _refreshButtonLabels(): void {
  const root = document.getElementById('resultsGroupControls');
  if (!root || root.dataset.ready !== '1') return;
  const _t = typeof window.tr === 'function' ? window.tr : function (_k: string, f?: string) { return f || ''; };
  const map: Record<string, string> = { all: 'grouping.btn_files', folder: 'grouping.btn_folders', zip: 'grouping.btn_archive' };
  const fallbacks: Record<string, string> = { all: 'Files', folder: 'Folders', zip: 'Archive' };
  root.querySelectorAll<HTMLButtonElement>('[data-mode]').forEach(function (btn) {
    const m = btn.dataset.mode!;
    if (map[m]) btn.textContent = _t(map[m], fallbacks[m]);
  });
}

function _updateUi(
  mode: string,
  visibleCount: number,
  totalCount: number,
  totalGroups?: number,
  limited?: boolean,
): void {
  const root = document.getElementById('resultsGroupControls');
  if (root) {
    root.querySelectorAll<HTMLButtonElement>('[data-mode]').forEach(function (btn) {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
  }
  const summary = document.getElementById('resultsGroupSummary');
  if (!summary) return;
  if (mode === MODES.all) {
    summary.style.display = 'none';
    summary.textContent = '';
    // Restore file-tab result count (saved by search runner)
    if (S.savedFileCount != null) {
      getAppApi().setResultsCount(S.savedFileCount);
    }
    return;
  }
  summary.style.display = '';
  const _t = typeof window.tr === 'function' ? window.tr : function (_k: string, f?: string) { return f || ''; };
  const label = mode === MODES.folder
    ? _t('grouping.summary_folders', 'Folders: {visible} ({total} files)')
    : _t('grouping.summary_archives', 'Archives: {visible} ({total} files)');
  const resolvedTotalGroups = totalGroups || visibleCount;
  if (limited && resolvedTotalGroups > visibleCount) {
    const limitedLabel = mode === MODES.folder
      ? _t('grouping.summary_folders_limited', 'Folders: {visible} shown / {groups} total ({total} files)')
      : _t('grouping.summary_archives_limited', 'Archives: {visible} shown / {groups} total ({total} files)');
    summary.textContent = limitedLabel
      .replace('{visible}', String(visibleCount))
      .replace('{groups}', String(resolvedTotalGroups))
      .replace('{total}', String(totalCount));
  } else {
    summary.textContent = label
      .replace('{visible}', String(visibleCount))
      .replace('{total}', String(totalCount));
  }

  // Update resultsCount to reflect grouped tab count
  // Save original file count for restore when switching back to "all"
  const el = document.getElementById('resultsCount');
  if (el && S.savedFileCount == null) {
    S.savedFileCount = el.textContent;
  }
  const countLabel = limited && resolvedTotalGroups > visibleCount
    ? (
      mode === MODES.folder
        ? _t('grouping.count_folders_limited', '{count} / {total} folders shown')
        : _t('grouping.count_archives_limited', '{count} / {total} archives shown')
    )
      .replace('{count}', String(visibleCount))
      .replace('{total}', String(resolvedTotalGroups))
    : (
      mode === MODES.folder
        ? _t('grouping.count_folders', '{count} folders found')
        : _t('grouping.count_archives', '{count} archives found')
    ).replace('{count}', String(visibleCount));
  getAppApi().setResultsCount(countLabel);
}

/* ---- Main entry point ---- */

export function applyToCurrentResults(): number[] {
  _ensureUi();
  _refreshButtonLabels();
  const mode = getMode();
  const container = document.getElementById('results');
  if (!container) return [];
  const cards = Array.from(container.querySelectorAll<HTMLElement>('.result-card')) as ContainerCard[];

  // Update CSV export button visibility on mode switch
  if (typeof window.updateExportCsvVisibility === 'function') {
    window.updateExportCsvVisibility();
  }

  if (mode !== MODES.all) {
    // Stop virtual scroll in group mode (incompatible with direct DOM manipulation)
    vsDeactivate();
    // Use server-side grouped search for correct counts
    fetchAndApplyGroupedResults(mode, _updateUi);

    // Kick off background preload after the grouped view has settled.
    if (!S.preloadStarted && (cards.length > 0 || isVirtualScrollActive())) {
      _scheduleVisibleIdle(() => {
        startBackgroundPreload();
      }, 1800);
    }
    return [];
  }

  // ---- "all" mode: restore all cards ----
  cancelGroupedSearch();

  // When virtual scroll is active, get all IDs from DataStore
  const vsIds = isVirtualScrollActive() ? vsGetAllIds() : [];

  const visibleIds: number[] = [];
  cards.forEach(function (card) {
    restoreCard(card);
    // Remove orphan cards dynamically created by grouped view
    // (they have no real content after restore)
    if (!card.innerHTML.trim()) {
      card.remove();
      return;
    }
    card.style.display = '';
    const id = Number(card.dataset.id);
    if (Number.isFinite(id)) visibleIds.push(id);
  });
  S.orderedGroups = [];
  S.resultOrderGroups = [];

  // When virtual scroll is active, use all IDs from DataStore
  const allIds = vsIds.length > 0 ? vsIds : visibleIds;
  _updateUi(mode, allIds.length, allIds.length);
  const viewerScope = getViewerScope() || 'result_set';
  if (viewerScope === 'result_set') setScopeResultIds('result_set', allIds);

  // Restore infinite scroll in "all" mode
  if (searchPager.getHasMore()) {
    _scheduleVisibleIdle(() => {
      searchPager.showLoadMoreSentinel();
      searchPager.setupScrollObserver();
    }, 1200);
  }

  // Kick off background preload once
  if (!S.preloadStarted && cards.length > 0) {
    _scheduleVisibleIdle(() => {
      startBackgroundPreload();
    }, 1800);
  }

  return visibleIds;
}

/* ---- Cross-group navigation ---- */

export function getOrderedGroups(): OrderedGroup[] {
  return S.orderedGroups.slice();
}

function _activeGroupList(): OrderedGroup[] {
  const order = localStorage.getItem('containerNavOrder');
  return order === 'result' ? S.resultOrderGroups : S.orderedGroups;
}

export function getAdjacentGroupIds(currentIds: number[], delta: number): number[] | null {
  const list = _activeGroupList();
  if (!list.length || !currentIds || !currentIds.length) return null;

  const currentSet: Record<number, boolean> = {};
  for (let i = 0; i < currentIds.length; i++) {
    currentSet[currentIds[i]] = true;
  }

  let matchIdx = -1;
  for (let j = 0; j < list.length; j++) {
    const gIds = list[j].ids;
    if (gIds.length === currentIds.length && currentSet[gIds[0]]) {
      matchIdx = j;
      break;
    }
  }
  if (matchIdx < 0) return null;

  const adjIdx = matchIdx + (delta > 0 ? 1 : -1);
  if (adjIdx < 0 || adjIdx >= list.length) return null;
  return list[adjIdx].ids.slice();
}

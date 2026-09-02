/**
 * results/grouping-search.ts
 *
 * Server-side grouped search: build search params from current form,
 * fetch grouped results, render container cards.
 */

import { searchPager } from '../search/pagination';
import { getSearchContext, buildSearchParams } from '../search/runner-context';
import {
  clearMemberCache,
  type ContainerGroupInfo,
} from './grouping-cards';
import { vsDeactivate } from './virtual-scroll-bridge';
import { getAppApi } from '../../shared/browser-apis';
import { createPagePerfTracker } from '../../shared/page-perf';
import { buildClientGroupedResults } from './grouping-search-client';
import { isPerfEnabled, scheduleAfterPaint, scheduleIdle } from './grouping-search-scheduler';
import { renderGroupedResults } from './grouping-search-render';

export interface GroupedSearchGroup {
  type: 'zip' | 'folder';
  key: string;
  label: string;
  count: number;
  memberIds?: number[];
  reps?: number[];
}

export interface GroupedSearchData {
  status?: string;
  message?: string;
  groups?: GroupedSearchGroup[];
  total_files?: number;
  total_groups?: number;
  returned_groups?: number;
  limited?: boolean;
  perf?: Record<string, number>;
}

/* ---- Abort handle for in-flight grouped search ---- */

let _groupedSearchAbort: { cancelled: boolean } | null = null;
const _perf = createPagePerfTracker('grouping-action');

function _scheduleAfterPaint(task: () => void): void {
  scheduleAfterPaint(task);
}

function _scheduleIdle(task: () => void, timeout = 120): void {
  scheduleIdle(task, timeout);
}

function _isPerfEnabled(): boolean {
  return isPerfEnabled();
}

export function cancelGroupedSearch(): void {
  if (_groupedSearchAbort) {
    _groupedSearchAbort.cancelled = true;
    _groupedSearchAbort = null;
  }
  // Ensure grayed-out state is cleared on cancel
  const container = document.getElementById('results');
  if (container) container.classList.remove('is-loading');
}

/**
 * Build search params from current form state, matching the normal search flow.
 * Reuses runtimeSearchRunnerContext.buildSearchParams if available.
 */
function _buildCurrentSearchParams(): URLSearchParams {
  const ctx = getSearchContext();
  return buildSearchParams(ctx);
}

function _buildClientGroupedResults(mode: string, container: HTMLElement | null): GroupedSearchData | null {
  return buildClientGroupedResults(mode, container);
}

/**
 * Fetch grouped results from the server and render container cards.
 * This replaces the old DOM-filtering approach with a full server-side
 * grouped search that considers ALL matching results, not just the
 * first page loaded in the DOM.
 */
export function fetchAndApplyGroupedResults(
  mode: string,
  updateUi: (
    mode: string,
    visibleCount: number,
    totalCount: number,
    totalGroups?: number,
    limited?: boolean,
  ) => void,
): void {
  if (_groupedSearchAbort) {
    _groupedSearchAbort.cancelled = true;
  }
  const handle = { cancelled: false };
  _groupedSearchAbort = handle;
  clearMemberCache();  // Clear stale cache on new grouped search

  const params = _buildCurrentSearchParams();
  params.set('group_mode', mode);
  // Remove pagination params -- server groups all results
  params.delete('offset');
  params.delete('limit');
  if (_isPerfEnabled()) {
    params.set('perf', '1');
  }

  const url = getAppApi().apiUrl('/api/search-grouped?' + params);
  _perf.mark('grouping_fetch_start');

  // Ensure virtual scroll is stopped if still active (clear padding, etc.)
  vsDeactivate();

  // Show loading state
  const container = document.getElementById('results');
  if (container) {
    container.classList.add('is-loading');
    // Clear virtual scroll padding remnants
    container.style.paddingTop = '';
    container.style.paddingBottom = '';
  }

  const clientData = _buildClientGroupedResults(mode, container);
  if (clientData) {
    _perf.mark('grouping_response_received');
    _perf.mark('grouping_json_ready');
    if (typeof window !== 'undefined') {
      window.__yuPagePerf ||= {};
      window.__yuPagePerf['grouping-server'] = clientData.perf || { client_fast_path: 1, total_ms: 0 };
    }
    _perf.mark('grouping_render_start');
    _renderGroupedResults(clientData, mode, container, updateUi, handle);
    return;
  }

  fetch(url)
    .then(function (res) {
      _perf.mark('grouping_response_received');
      return res.json();
    })
    .then(function (data: GroupedSearchData) {
      _perf.mark('grouping_json_ready');
      if (data.perf && typeof window !== 'undefined') {
        window.__yuPagePerf ||= {};
        window.__yuPagePerf['grouping-server'] = data.perf;
      }
      if (handle.cancelled) {
        // Clear loading state even if cancelled
        if (container) container.classList.remove('is-loading');
        return;
      }
      if (data.status === 'error') {
        if (container) container.classList.remove('is-loading');
        console.warn('search-grouped error:', data.message);
        return;
      }

      _perf.mark('grouping_render_start');
      _renderGroupedResults(data, mode, container, updateUi, handle);
    })
    .catch(function (err) {
      // Always clear loading state on error
      if (container) container.classList.remove('is-loading');
      if (handle.cancelled) return;
      console.warn('search-grouped fetch failed:', err);
    });
}

function _renderGroupedResults(
  data: GroupedSearchData,
  mode: string,
  container: HTMLElement | null,
  updateUi: (
    mode: string,
    visibleCount: number,
    totalCount: number,
    totalGroups?: number,
    limited?: boolean,
  ) => void,
  handle: { cancelled: boolean },
): void {
  renderGroupedResults(data, mode, container, updateUi, handle, _perf);
}

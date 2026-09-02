/**
 * system/checkpoints-init.ts — Load checkpoint datalist and window.load init.
 * Converted from runtime-checkpoints-init.js
 */

import { loadServerInfo } from './server-info';
import { markCopyableExamples } from '../regex/intro';
import { getAppApi, getSearchResultsApi } from '../../shared/browser-apis';

export async function loadCheckpoints(): Promise<void> {
  try {
    const { apiFetch, tr } = getAppApi();
    const response = await apiFetch('/api/checkpoints', { silent: true });
    const data = await response.json();

    const datalist = document.getElementById('checkpointList');
    if (!datalist) return;

    datalist.innerHTML = '';

    for (const cp of data.checkpoints as Array<{ name: string; count: number }>) {
      const option = document.createElement('option');
      option.value = cp.name;
      option.textContent = tr('checkpoint.option_count', { name: cp.name, count: cp.count });
      datalist.appendChild(option);
    }
  } catch (error) {
    console.error('Failed to load checkpoints:', error);
  }
}

/**
 * Wraps the window.load init logic that was in the original script.
 * Should be called once from the bundle entry point.
 */
export function initCheckpoints(): void {
  function _onLoad(): void {
    markCopyableExamples();

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (typeof (window as any).maybeLaunchBossModeFromQuery === 'function') {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).maybeLaunchBossModeFromQuery();
    }

    loadCheckpoints().catch((e: Error) => console.warn('[init] checkpoints:', e.message));
    loadServerInfo().catch((e: Error) => console.warn('[init] serverInfo:', e.message));
  }

  // If called after window.load (e.g. via requestIdleCallback), run immediately
  if (document.readyState === 'complete') {
    _onLoad();
  } else {
    window.addEventListener('load', _onLoad);
  }

  const searchForm = document.getElementById('searchForm');
  if (searchForm) {
    // window.search is set later due to chunk splitting, so instead of
    // capturing the function reference directly, do a dynamic lookup at event time
    searchForm.addEventListener('submit', function (e: Event) {
      const { runSearch } = getSearchResultsApi();
      if (runSearch) {
        runSearch(e);
      } else {
        e.preventDefault();
        console.warn('[initCheckpoints] searchResultsApi.runSearch not available at submit time');
      }
    });
  }
}

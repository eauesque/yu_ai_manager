/**
 * results/grouping-preload-core.ts
 *
 * Groups index fetch, button state management, and force rebuild.
 */

import { getAppApi, getNavApi } from '../../shared/browser-apis';
import { rgState as S, dbg } from './grouping-utils';
import { getRuntimeResultsGrouping } from '../../shared/runtime-state/results-grouping-state';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

/* -- Button state -- */

export function setGroupButtonsDisabled(disabled: boolean): void {
  const root = document.getElementById('resultsGroupControls');
  if (!root) return;
  root.querySelectorAll<HTMLButtonElement>('[data-mode]').forEach(function (btn) {
    if (btn.dataset.mode === 'all') return;
    btn.disabled = disabled;
    btn.classList.toggle('rg-btn-disabled', disabled);
  });
}

/**
 * Enable folder/ZIP buttons when groups-index is ready.
 * Server-side group search works with groups-index alone,
 * so we don't wait for thumbnail preload to complete.
 */
export function enableButtonsIfReady(): void {
  if (!S.serverGroupsFetched) return;
  setGroupButtonsDisabled(false);
}

/* -- Groups index fetch -- */

export function fetchGroupsIndex(): Promise<void> {
  if (S.serverGroupsFetched) return Promise.resolve();
  if (S.serverGroupsFetching) return S.fetchGroupsPromise || Promise.resolve();
  S.serverGroupsFetching = true;

  // Use in-memory cache if available (no sessionStorage parse needed)
  if (S.serverGroups) {
    S.serverGroupsFetched = true;
    S.serverGroupsFetching = false;
    enableButtonsIfReady();
    return Promise.resolve();
  }

  // sessionStorage has high parse overhead for large JSON,
  // so only store a simple flag and always fetch actual data from server
  // (in-page S.serverGroups in-memory cache is sufficient)
  const url = getAppApi().apiUrl('/api/groups-index');

  S.fetchGroupsPromise = fetch(url)
    .then(function (res) { return res.json(); })
    .then(function (data) {
      S.serverGroups = data;
      S.serverGroupsFetched = true;
      S.serverGroupsFetching = false;
      S.fetchGroupsPromise = null;
      dbg('fetchGroupsIndex: fetched from server',
        'folders:', Object.keys(data.folders || {}).length,
        'zips:', Object.keys(data.zips || {}).length);
      enableButtonsIfReady();
    })
    .catch(function (err) {
      console.warn('groups-index fetch failed:', err);
      S.serverGroupsFetching = false;
      S.fetchGroupsPromise = null;
      // Enable buttons even on fetch failure (file display still works)
      setGroupButtonsDisabled(false);
    });
  return S.fetchGroupsPromise;
}

/* -- Force rebuild -- */

export function rebuildGroups(): void {
  const btn = document.getElementById('rgRefreshBtn') as HTMLButtonElement | null;
  if (btn) { btn.disabled = true; btn.classList.add('rg-btn-spinning'); }

  // Clear client-side caches
  try {
    sessionStorage.removeItem('groupsIndex');
    sessionStorage.removeItem('thumbPreloadDone');
  } catch (_e) { /* ignore */ }

  // Reset internal state
  S.serverGroups = null;
  S.serverGroupsFetched = false;
  S.serverGroupsFetching = false;
  S.fetchGroupsPromise = null;
  S.preloadStarted = false;
  S.preloadRunning = false;
  S.preloadDone = false;
  S.rebuildInProgress = true;
  setGroupButtonsDisabled(true);

  const url = getAppApi().apiUrl('/api/tools/rebuild-groups');

  fetch(url, { method: 'POST', headers: XHR_HEADERS })
    .then(function (res) { return res.json(); })
    .then(function (data: { folders?: number; zips?: number }) {
      const _t = typeof window.tr === 'function' ? window.tr : function (_k: string, f?: string) { return f || ''; };
      const msg = _t('grouping.rebuilt', 'Groups rebuilt: {folders} folders, {zips} ZIP')
        .replace('{folders}', String(data.folders || 0))
        .replace('{zips}', String(data.zips || 0));
      getNavApi().showToast(msg);

      // 1) Fetch fresh groups-index and wait for it
      return fetchGroupsIndex();
    })
    .then(function () {
      // 2) Apply grouping to current results (groups-index is now ready)
      getRuntimeResultsGrouping()?.applyToCurrentResults();

      // 3) Start background thumbnail preload (non-blocking)
      // Dynamic import to avoid circular dependency (thumbs imports from core)
      if (!S.preloadStarted) {
        import('./grouping-preload-thumbs').then(function (mod) {
          mod.startBackgroundPreload();
        });
      }
    })
    .catch(function (err) {
      console.warn('rebuild-groups failed:', err);
      getNavApi().showToast('Rebuild failed', true);
    })
    .finally(function () {
      S.rebuildInProgress = false;
      if (btn) { btn.disabled = false; btn.classList.remove('rg-btn-spinning'); }
    });
}

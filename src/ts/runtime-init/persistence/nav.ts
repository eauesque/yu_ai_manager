/**
 * Search state bootstrap and global API wiring.
 * Converts the IIFE from runtime-persistence-nav.js to an init function.
 */

import { restoreSearchState, SEARCH_STATE_KEY, SEARCH_COMMITTED_KEY } from './core';
import { getAppApi, getSearchResultsApi } from '../../shared/browser-apis';
import { getServerBootState } from '../../shared/runtime-state/server-info-state';
import {
  isPageReturn,
  setStartupAutoSearch,
} from '../../shared/runtime-state/navigation-state';
import { scheduleVisibleIdle as _scheduleIdle } from '../../shared/idle';

let _autosavePromise: Promise<typeof import('./autosave')> | null = null;

function _loadAutosave() {
  if (!_autosavePromise) {
    _autosavePromise = import('./autosave');
  }
  return _autosavePromise;
}


function _waitForBootReady(cb: () => void): void {
  if (getServerBootState() === 'ready') { cb(); return; }
  // Also trigger on DOMContentLoaded / window.load as fallback signals
  let fired = false;
  const fire = (): void => {
    if (fired) return;
    fired = true;
    cb();
  };
  let attempts = 0;
  const iv = setInterval(function () {
    attempts++;
    if (getServerBootState() === 'ready' || attempts > 20) {
      clearInterval(iv);
      fire();
    }
  }, 500);
  // Fallback: fire on window.load if boot state never arrives
  window.addEventListener('load', function () {
    // Give loadServerInfo a moment to set boot state, then fire if still pending
    setTimeout(fire, 800);
  });
}

/**
 * Initialize search persistence: restore state, run auto-search, wire autosave.
 * Call once during page initialization.
 */
export function initPersistenceNav(): void {
  const { getStartupMode, escapeHtml, tr } = getAppApi();
  const { runSearch } = getSearchResultsApi();
  const mode = getStartupMode();
  const pageReturn = isPageReturn();

  if (mode === 'clear') {
    localStorage.removeItem(SEARCH_STATE_KEY);
    localStorage.removeItem(SEARCH_COMMITTED_KEY);
  } else if (pageReturn) {
    const committed = localStorage.getItem(SEARCH_COMMITTED_KEY);
    const current = localStorage.getItem(SEARCH_STATE_KEY);
    if (committed) {
      localStorage.setItem(SEARCH_STATE_KEY, committed);
    }
    restoreSearchState();
    console.log('Search state restored for page return (committed=' + !!committed + ')');
    _waitForBootReady(function () { runSearch(); });

    if (committed && current && current !== committed) {
      try {
        const cs = JSON.parse(current);
        if (cs.tagQuery !== undefined) {
          const q = document.getElementById('tagQuery') as HTMLInputElement | null;
          if (q) q.value = cs.tagQuery;
        }
        localStorage.setItem(SEARCH_STATE_KEY, current);
      } catch (_ex) { /* ignore parse errors */ }
    }
  } else {
    const restored = restoreSearchState();
    if (restored) {
      console.log(`Search state restored (mode: ${mode})`);
    }
    if (mode === 'restore') {
      const results = document.getElementById('results');
      if (results) {
        results.innerHTML =
          `<div style="text-align:center;color:#888;padding:40px;font-size:14px;">${escapeHtml(tr('search.state.start_prompt'))}</div>`;
      }
    } else {
      // mode === 'auto' or default: auto-run search after boot
      _waitForBootReady(function () {
        runSearch();
      });
    }
  }

  _scheduleIdle(() => _loadAutosave().then((mod) => {
    mod.setupAutoSave();
  }));
  setStartupAutoSearch(mode === 'auto');

}

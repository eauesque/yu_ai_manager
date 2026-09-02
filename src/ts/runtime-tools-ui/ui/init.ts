/**
 * ui/init.ts — UI initialization: theme, autocomplete, deep-link check.
 * Merged from runtime-ui-init.js + runtime-ui-autocomplete.js
 */

import { initThemeToggle } from './theme';
import { loadStats, renderCachedStats } from '../../search-results/search/core';
import { getRuntimeToolsUiHooks } from '../hooks';
import { getAppApi } from '../../shared/browser-apis';
import { setIsPageReturn } from '../../shared/runtime-state/navigation-state';
import { createPagePerfTracker } from '../../shared/page-perf';
import { scheduleDelayedVisibleIdle } from '../../shared/idle';

const _perf = createPagePerfTracker('search-home');

let _autocompletePromise: Promise<typeof import('./autocomplete-core')> | null = null;

function _loadAutocompleteCore() {
  if (!_autocompletePromise) {
    _autocompletePromise = import('./autocomplete-core');
  }
  return _autocompletePromise;
}


export function initTagAutocomplete(): void {
  const input = document.getElementById('tagQuery') as HTMLInputElement | null;
  if (!input || input.dataset.suggestBootstrapBound) return;
  input.dataset.suggestBootstrapBound = '1';

  const ensureAutocomplete = (): void => {
    void _loadAutocompleteCore().then((mod) => {
      mod.bindAutocomplete(input);
      _perf.markOnce('autocomplete_ready');
    }).catch(() => {});
  };

  input.addEventListener('focus', ensureAutocomplete, { once: true });
  input.addEventListener('pointerdown', ensureAutocomplete, { once: true });
}

export function initUiCore(): void {
  initThemeToggle();
  try {
    initTagAutocomplete();
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    console.warn('[init] tagAutocomplete:', message);
  }
  if (renderCachedStats()) {
    _perf.markOnce('stats_cached');
  }
  scheduleDelayedVisibleIdle(() => loadStats().catch((e: Error) => {
    console.warn('[init] stats:', e.message);
  }).finally(() => {
    _perf.markOnce('stats_ready');
  }));

  const startupMode = getAppApi().getStartupMode();
  const isPageReturn = sessionStorage.getItem('scrollY') !== null;
  console.log(`[init] startupMode=${startupMode}, isPageReturn=${isPageReturn}`);
  setIsPageReturn(isPageReturn);

  // Deep link check
  (function checkDeepLink(): void {
    const params = new URLSearchParams(window.location.search);
    const openId = params.get('open');
    if (openId) {
      const openModal = (): void => {
        setTimeout(() => getRuntimeToolsUiHooks().showDetail(parseInt(openId, 10)), 300);
        _perf.markOnce('deeplink_open');
      };
      if (document.readyState === 'complete') openModal();
      else window.addEventListener('load', openModal);
    }
  })();

  _perf.markOnce('ui_ready');
}

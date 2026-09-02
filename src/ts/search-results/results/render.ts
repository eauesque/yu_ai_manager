/**
 * results/render.ts
 *
 * Result list rendering: append / display results, prompt toggle, copy prompt.
 *
 * Converted from runtime-results-render.js (bare globals -> named exports).
 */

import { setupResultCardA11y } from './a11y';
import {
  buildResultCardInnerHtml,
  applyResultCardData,
  bindResultCardInteractions,
  buildExpandedPromptHtml,
  buildCollapsedPromptHtml,
} from './render-card';
import { MAX_DOM_CARDS } from '../search/state';
import { vsDisplayResults, vsAppendResults, vsGetAllIds } from './virtual-scroll-bridge';
import { safeViewTransition } from '../../shared/view-transition';
import { getAppApi, getDetailModalApi, getNavApi, getRuntimeToolsApi, getSearchResultsApi } from '../../shared/browser-apis';
import { getRuntimeResultsGrouping } from '../../shared/runtime-state/results-grouping-state';
import { getMode } from './grouping-utils';
import { appendScopeResultIds, setScopeResultIds } from '../../runtime-pre/ui-state';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ResultRecord = Record<string, any>;

function _scheduleAfterPaint(task: () => void): void {
  requestAnimationFrame(() => {
    requestAnimationFrame(task);
  });
}

function _scheduleFavoritesSync(ids: number[]): void {
  if (ids.length === 0) return;
  const { checkFavorites } = getSearchResultsApi();
  _scheduleAfterPaint(() => {
    checkFavorites(ids);
  });
}

export function appendResults(results: ResultRecord[]): number[] {
  // When virtual scroll is active, append to data store and return
  if (vsAppendResults(results)) {
    const ids = results.map((r) => r.id as number).filter((id) => typeof id === 'number');
    // Sync appended IDs for modal navigation
    appendScopeResultIds('result_set', ids);
    if (ids.length > 0) {
      _scheduleFavoritesSync(ids);
    }
    return [];
  }

  const container = document.getElementById('results');
  if (!container) return [];

  const baseIndex = container.querySelectorAll('.result-card').length;
  const fragment = document.createDocumentFragment();
  results.forEach((result, i) => {
    const card = document.createElement('div');
    card.className = 'result-card';
    card.style.setProperty('--i', String(baseIndex + i));
    card.innerHTML = buildResultCardInnerHtml(result);
    applyResultCardData(card, result);
    bindResultCardInteractions(card);
    fragment.appendChild(card);
  });
  container.appendChild(fragment);

  setupResultCardA11y();
  getAppApi().updateKeyboardGuideVisibility();

  const allCards = container.querySelectorAll('.result-card');
  if (allCards.length > MAX_DOM_CARDS) {
    const excess = allCards.length - MAX_DOM_CARDS;
    for (let i = 0; i < excess; i++) allCards[i].remove();
    setupResultCardA11y();
  }
  getAppApi().updateKeyboardGuideVisibility();
  // 280K optimization: skip applyToCurrentResults when group mode is active
  // (group display is handled separately by fetchAndApplyGroupedResults)
  const groupMode = getMode();
  const visibleIds = groupMode === 'all'
    ? (getRuntimeResultsGrouping()?.applyToCurrentResults() || [])
    : [];

  const ids = results.map((r) => r.id as number).filter((id) => typeof id === 'number');
  // Sync appended IDs for modal navigation (mirrors the vs branch).
  appendScopeResultIds('result_set', ids);
  if (ids.length > 0) {
    _scheduleFavoritesSync(ids);
  }
  return visibleIds;
}

export function displayResults(results: ResultRecord[]): void {
  // When virtual scroll is active, set data in store and delegate rendering to VirtualGrid
  if (vsDisplayResults(results)) {
    // Initialize group button UI even during virtual scroll
    getRuntimeResultsGrouping()?.applyToCurrentResults();
    getAppApi().updateKeyboardGuideVisibility();
    const ids = (results || []).map((r) => r.id as number).filter((id) => typeof id === 'number');
    // Sync all IDs for modal navigation
    setScopeResultIds('result_set', ids);
    if (ids.length > 0) {
      _scheduleFavoritesSync(ids);
    }
    return;
  }

  const container = document.getElementById('results');
  if (!container) return;

  const doUpdate = () => {
    container.innerHTML = '';
    if (!results || results.length === 0) {
      getRuntimeResultsGrouping()?.applyToCurrentResults();
      getAppApi().updateKeyboardGuideVisibility();
      return;
    }

    const fragment = document.createDocumentFragment();
    results.forEach((result, i) => {
      const card = document.createElement('div');
      card.className = 'result-card';
      card.style.setProperty('--i', String(i));
      card.innerHTML = buildResultCardInnerHtml(result);
      applyResultCardData(card, result);
      bindResultCardInteractions(card);
      fragment.appendChild(card);
    });
    container.appendChild(fragment);

    setupResultCardA11y();
    // 280K optimization: skip full DOM scan when group mode is active
    const gMode = getMode();
    if (gMode === 'all') {
      getRuntimeResultsGrouping()?.applyToCurrentResults();
    }
    getAppApi().updateKeyboardGuideVisibility();

    const ids = results.map((r) => r.id as number).filter((id) => typeof id === 'number');
    // Sync IDs for modal navigation (mirrors the virtual-scroll branch above).
    // Without this the prev/next arrows are stuck disabled when a search renders
    // through this flat-DOM path — e.g. on page-return restore with vs disabled.
    setScopeResultIds('result_set', ids);
    if (ids.length > 0) {
      _scheduleFavoritesSync(ids);
    }
  };

  safeViewTransition(doUpdate);

  // NOTE: Thumbnail warmup POST was removed. The batch fetcher
  // (`thumbnail-batch.ts`) already serializes thumbnail generation
  // server-side via the per-archive lock in `serve_thumbnail`, and an
  // additional warmup daemon thread caused 1-2s GUI stutters every
  // time results were rendered. See v4.119.16 in CHANGELOG.
}

export function togglePrompt(id: number, evt?: Event): void {
  const el = document.getElementById(`prompt-${id}`);
  if (!el) return;
  const card = el.closest('.result-card') as HTMLElement | null;
  const toggleEl = card?.querySelector<HTMLElement>(`[data-prompt-toggle="${id}"]`) || el;
  const chev = toggleEl.querySelector('.prompt-chev');

  const setState = (expanded: boolean): void => {
    toggleEl.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    if (chev) chev.textContent = expanded ? '\u25BE' : '\u25B8';
  };

  if (el.classList.contains('collapsed')) {
    el.classList.remove('collapsed');
    el.innerHTML = buildExpandedPromptHtml(
      card?.dataset?.positive || '',
      card?.dataset?.negative || ''
    );
    setState(true);
  } else {
    el.classList.add('collapsed');
    el.innerHTML = buildCollapsedPromptHtml(card?.dataset?.positive || '');
    setState(false);
  }
}

export function copyPrompt(id: number, type: string, evt?: Event): void {
  const { tr } = getAppApi();
  const { showToast } = getNavApi();
  const { copyToClipboard } = getDetailModalApi();
  const { notifyCopy } = getRuntimeToolsApi();
  const card = document.querySelector(`#prompt-${id}`)?.closest('.result-card') as HTMLElement | null;
  const text = type === 'positive' ? card?.dataset.positive || '' : card?.dataset.negative || '';
  const btn = (evt as MouseEvent | undefined)?.currentTarget as HTMLElement | null | undefined;
  copyToClipboard(text).then((ok: boolean) => {
    notifyCopy(btn, ok);
    showToast(ok ? tr('toast.copy_done_strong') : tr('toast.copy_failed'), !ok);
  });
}

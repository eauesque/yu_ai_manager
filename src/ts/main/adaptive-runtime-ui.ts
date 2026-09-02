/**
 * Adaptive runtime UI — keyboard guide, loading tips, results counter.
 * Converted from static/js/main/main-adaptive-runtime-ui.js
 */

import { state } from './adaptive-runtime-state';
import { escapeHtml } from './api-utils';
import { isVirtualScrollActive, vsGetAllIds } from '../search-results/results/virtual-scroll-bridge';
import { getFloatingGridApi, getSearchResultsApi } from '../shared/browser-apis';

let loadingTipTimer: ReturnType<typeof setInterval> | null = null;

export function setResultsCount(text: string): void {
  const el = document.getElementById('resultsCount');
  if (el) el.textContent = text || '';
}

export function renderResultKeyboardGuide(): void {
  const el = document.getElementById('resultKeyboardGuide');
  if (!el) return;
  el.innerHTML = `
    <span>
      <strong>${escapeHtml(state.tr('keyboard.guide.results_label', 'Result'))}:</strong>
      <kbd>\u2190</kbd><kbd>\u2192</kbd><kbd>\u2191</kbd><kbd>\u2193</kbd><kbd>PgUp</kbd><kbd>PgDn</kbd> ${escapeHtml(state.tr('keyboard.guide.move', 'move'))}
      / <kbd>Enter</kbd> ${escapeHtml(state.tr('keyboard.guide.open', 'open'))}
      / <kbd>C</kbd> ${escapeHtml(state.tr('keyboard.guide.copy', 'copy'))}
      / <kbd>M</kbd> ${escapeHtml(state.tr('keyboard.guide.menu', 'menu'))}
      / <kbd>Esc</kbd> ${escapeHtml(state.tr('keyboard.guide.to_search', 'search'))}
    </span>
    <button type="button" class="kg-help" data-action="keyboardApi.showKeyboardHelp">\uD83D\uDCD6</button>
  `;
}

export function updateKeyboardGuideVisibility(): void {
  const modal = document.getElementById('modal');
  const modalActive = !!(modal && modal.classList.contains('active'));
  const cards = getSearchResultsApi().getResultCards();
  // When virtual scroll is active, DOM card count is low so also check the DataStore
  const hasResults = cards.length > 0 || (isVirtualScrollActive() && vsGetAllIds().length > 0);
  const resultGuide = document.getElementById('resultKeyboardGuide');
  const showResultGuide = !modalActive && hasResults;
  if (resultGuide) {
    resultGuide.style.display = showResultGuide ? 'inline-flex' : 'none';
    if (showResultGuide) {
      resultGuide.removeAttribute('aria-hidden');
      resultGuide.removeAttribute('inert');
    } else {
      resultGuide.setAttribute('aria-hidden', 'true');
      resultGuide.setAttribute('inert', '');
    }
  }
  const modalGuide = document.getElementById('modalKeyboardGuide');
  if (modalGuide) {
    const kbGloballyHidden = localStorage.getItem('modalKbGuideHidden') === '1';
    const kbDismissed = sessionStorage.getItem('kbGuideDismissed') === '1';
    const showModalGuide = modalActive && !kbGloballyHidden && !kbDismissed;
    modalGuide.style.display = showModalGuide ? 'block' : 'none';
  }

  const floatingGridApi = getFloatingGridApi();
  if (showResultGuide && floatingGridApi.isPanelOpen()) {
    floatingGridApi.closePanel();
  }
}

export function pickAdaptiveMessage(catalog: Record<string, string[]>, slot: string = 'default'): string {
  const t = state.getTimeBucket();
  const s = state.getSeasonBucket();
  const d = state.getDayTypeBucket();
  const e = state.getMonthEventBucket();
  const pool: string[] = ([] as string[])
    .concat(catalog.common || [])
    .concat(catalog[t] || [])
    .concat(catalog[s] || [])
    .concat(catalog[d] || [])
    .concat(catalog[e] || []);
  if (!pool.length) return '';

  let candidates = pool;
  const last = state.lastMessageBySlot[slot];
  if (last && pool.length > 1) {
    const filtered = pool.filter((m) => m !== last);
    if (filtered.length > 0) candidates = filtered;
  }

  const picked = candidates[Math.floor(Math.random() * candidates.length)];
  state.lastMessageBySlot[slot] = picked;
  return picked;
}

export function startLoadingTips(): void {
  const el = document.getElementById('loadingTip');
  if (!el) return;
  const pick = () => pickAdaptiveMessage(state.getAdaptiveCatalog('loading'), 'loading');
  el.textContent = pick();
  if (loadingTipTimer) clearInterval(loadingTipTimer);
  loadingTipTimer = setInterval(() => {
    el.textContent = pick();
  }, 1800);
}

export function stopLoadingTips(): void {
  if (loadingTipTimer) clearInterval(loadingTipTimer);
  loadingTipTimer = null;
}

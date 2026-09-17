import { getAppApi } from '../../shared/browser-apis';
import { getServerFileCount } from '../../shared/runtime-state/server-info-state';

export const MAX_DOM_CARDS = 2000;

/* ── i18n refresh tracking ── */
let _lastStateType: string | null = null;
let _lastStateMessage: string | null | undefined = null;
let _lastStateHasConditions: boolean | undefined;

let _lastCountSpec: { key: string; params?: Record<string, unknown> | undefined; suffix?: string | undefined } | null = null;

function formatCountParams(params?: Record<string, unknown>): Record<string, unknown> | undefined {
  if (!params) return params;
  const out: Record<string, unknown> = { ...params };
  // Apply locale-aware thousand separators to the canonical count key.
  if (typeof out.count === 'number' && Number.isFinite(out.count)) {
    try {
      out.count = (out.count as number).toLocaleString();
    } catch {
      out.count = String(out.count);
    }
  }
  return out;
}

export function setResultsCountI18n(key: string, params?: Record<string, unknown>, suffix?: string): void {
  _lastCountSpec = { key, params, suffix };
  getAppApi().setResultsCount(window.tr(key, formatCountParams(params)) + (suffix || ''));
}

export function clearResultsCount(): void {
  _lastCountSpec = null;
  getAppApi().setResultsCount('');
}

export function refreshSearchStateI18n(): void {
  if (_lastStateType === null) return;
  if (_lastStateType === 'error') return;
  showSearchState(_lastStateType, _lastStateMessage, _lastStateHasConditions);
  if (_lastCountSpec) {
    const { key, params, suffix } = _lastCountSpec;
    getAppApi().setResultsCount(window.tr(key, formatCountParams(params)) + (suffix || ''));
  }
}

export function showSearchState(type: string, message?: string | null, hasConditions?: boolean): void {
  _lastStateType = type;
  _lastStateMessage = message;
  _lastStateHasConditions = hasConditions;
  const container = document.getElementById('results');
  if (!container) return;

  const appApi = getAppApi();
  const { escapeHtml } = appApi;

  if (type === 'error') {
    container.innerHTML = `
      <div class="search-state search-state-error">
        <span class="search-state-icon">\u26a0\ufe0f</span>
        <div class="search-state-title">${escapeHtml(window.tr('search.state.error_title'))}</div>
        <div class="search-state-message">${escapeHtml(message || window.tr('search.state.unknown_error'))}</div>
      </div>`;
    appApi.updateKeyboardGuideVisibility();
    return;
  }

  // Empty database: guide new users to Settings
  if (getServerFileCount() === 0) {
    container.innerHTML = `
      <div class="search-state">
        <span class="search-state-icon">\uD83D\uDCC2</span>
        <div class="search-state-title">${escapeHtml(window.tr('search.state.empty_db_title'))}</div>
        <div class="search-state-message">${escapeHtml(window.tr('search.state.empty_db_message'))}</div>
        <div class="search-state-hint">
          \u2022 ${escapeHtml(window.tr('search.state.empty_db_hint1'))}<br>
          \u2022 ${escapeHtml(window.tr('search.state.empty_db_hint2'))}<br>
          \u2022 ${escapeHtml(window.tr('search.state.empty_db_hint3'))}
        </div>
        <div style="margin-top:16px">
          <a href="/settings" class="search-state-settings-link">${escapeHtml(window.tr('search.state.empty_db_settings_link'))}</a>
        </div>
      </div>`;
    appApi.updateKeyboardGuideVisibility();
    return;
  }

  if (hasConditions) {
    // When the active filter is a collection, the generic search hints
    // (tag spelling / period filter / regex) are not actionable -- the user
    // simply hasn't added items to that collection yet (or the smart query
    // matched nothing). Render a collection-specific empty state instead.
    const collSel = document.getElementById('collectionFilter') as HTMLSelectElement | null;
    const collValue = collSel?.value || '';
    const inCollection = collValue !== '' && collValue !== '0';
    if (inCollection) {
      const tagQuery = (document.getElementById('tagQuery') as HTMLInputElement | null)?.value || '';
      const hasOtherFilters = tagQuery.trim().length > 0;
      const msgKey = hasOtherFilters
        ? 'search.state.collection_empty_filtered_message'
        : 'search.state.collection_empty_message';
      const wrap = document.createElement('div');
      wrap.className = 'search-state';
      const icon = document.createElement('span');
      icon.className = 'search-state-icon';
      icon.textContent = '\ud83d\udcc1';
      const title = document.createElement('div');
      title.className = 'search-state-title';
      title.textContent = window.tr('search.state.collection_empty_title');
      const msg = document.createElement('div');
      msg.className = 'search-state-message';
      msg.textContent = window.tr(msgKey);
      wrap.appendChild(icon);
      wrap.appendChild(title);
      wrap.appendChild(msg);
      container.replaceChildren(wrap);
      appApi.updateKeyboardGuideVisibility();
      return;
    }
    const { pickAdaptiveMessage, getAdaptiveCatalog } = appApi;
    const cheer = pickAdaptiveMessage(getAdaptiveCatalog('empty'), 'empty');
    container.innerHTML = `
      <div class="search-state">
        <span class="search-state-icon">\ud83d\udd0d</span>
        <div class="search-state-title">${escapeHtml(window.tr('search.state.empty_title'))}</div>
        <div class="search-state-message">${escapeHtml(cheer)}</div>
        <div class="search-state-hint">
          <strong>${escapeHtml(window.tr('search.state.hint_label'))}</strong><br>
          \u2022 ${escapeHtml(window.tr('search.state.hint1'))}<br>
          \u2022 ${escapeHtml(window.tr('search.state.hint2'))}<br>
          \u2022 ${escapeHtml(window.tr('search.state.hint3'))}<br>
          \u2022 ${escapeHtml(window.tr('search.state.hint4'))}
        </div>
      </div>`;
  } else {
    container.innerHTML = `
      <div class="search-state">
        <span class="search-state-icon">\ud83d\udcc2</span>
        <div class="search-state-title">${escapeHtml(window.tr('search.state.first_title'))}</div>
        <div class="search-state-message">${escapeHtml(window.tr('search.state.first_message'))}</div>
        <div class="search-state-hint">
          <strong>${escapeHtml(window.tr('search.state.examples_label'))}</strong><br>
          \u2022 ${escapeHtml(window.tr('search.state.example1'))}<br>
          \u2022 ${escapeHtml(window.tr('search.state.example2'))}<br>
          \u2022 ${escapeHtml(window.tr('search.state.example3'))}<br>
          \u2022 ${escapeHtml(window.tr('search.state.example4'))}
        </div>
      </div>`;
  }
  appApi.updateKeyboardGuideVisibility();
}

export function showPartialWarning(_total: number, limit: number): void {
  const container = document.getElementById('results');
  if (!container) return;
  const existing = container.querySelector('.search-state-partial');
  if (existing) existing.remove();
  const warning = document.createElement('div');
  warning.className = 'search-state-partial';
  warning.textContent = window.tr('search.partial_warning', { limit });
  container.prepend(warning);
}

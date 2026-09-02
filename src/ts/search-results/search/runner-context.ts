import { getAppApi } from '../../shared/browser-apis';
import { _regexEnabled } from './core';
import { isVirtualScrollActive } from '../results/virtual-scroll-bridge';
import { getSearchFromTs } from '../../shared/runtime-state/search-period-state';

function _isVirtualScrollActive(): boolean {
  try {
    return isVirtualScrollActive();
  } catch {
    return false;
  }
}

interface SearchContext {
  queryInput: string;
  useRegex: boolean;
  tagCaseSensitive: boolean;
  inPromptValue: string;
}

function _isPerfEnabled(): boolean {
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get('perf') === '1') return true;
    return localStorage.getItem('yu_page_perf') === '1';
  } catch {
    return false;
  }
}

interface LoadingEls {
  resultsEl: HTMLElement;
  loadingEl: HTMLElement;
}

export function getSearchContext(): SearchContext {
  const tagQuery = document.getElementById('tagQuery') as HTMLInputElement | null;
  const queryInput = tagQuery?.value || '';
  const useRegex = _regexEnabled;
  const tagCaseSensitive = (document.getElementById('tagCaseSensitive') as HTMLInputElement | null)?.checked || false;

  return {
    queryInput,
    useRegex,
    tagCaseSensitive,
    inPromptValue: (document.getElementById('inPrompt') as HTMLInputElement | null)?.value || '',
  };
}

export function ensureRegexConfirm(context: SearchContext): boolean {
  const tagRegex = context.useRegex;
  const inPromptRegex = context.useRegex && !!context.inPromptValue;

  if (!tagRegex && !inPromptRegex) return true;

  const limitEl = document.getElementById('limit') as HTMLInputElement | null;
  const limitValue = parseInt(limitEl?.value || '0', 10);
  if (limitValue > 1000) {
    return confirm(window.tr('search.regex_warn_confirm'));
  }
  return true;
}

export function buildSearchParams(context: SearchContext): URLSearchParams {
  const tagRegex = context.useRegex;
  const inPromptRegex = context.useRegex && !!context.inPromptValue;

  const inNegativeEl = document.getElementById('inNegative') as HTMLInputElement | null;
  const inCharNegativeEl = document.getElementById('inCharNegative') as HTMLInputElement | null;
  const inCharPositiveEl = document.getElementById('inCharPositive') as HTMLInputElement | null;
  const checkpointEl = document.getElementById('checkpointFilter') as HTMLInputElement | null;

  const params = new URLSearchParams({
    q: context.queryInput,
    artist: (document.getElementById('artist') as HTMLInputElement)?.value || '',
    from: (document.getElementById('fromDate') as HTMLInputElement)?.value || '',
    to: (document.getElementById('toDate') as HTMLInputElement)?.value || '',
    in_prompt: context.inPromptValue,
    in_negative: inNegativeEl?.disabled ? '' : inNegativeEl?.value || '',
    in_char_negative: inCharNegativeEl?.disabled ? '' : inCharNegativeEl?.value || '',
    in_char_positive: inCharPositiveEl?.disabled ? '' : inCharPositiveEl?.value || '',
    in_path: '',
    format: (document.getElementById('fileFormat') as HTMLSelectElement)?.value || '',
    format_exts: (document.getElementById('formatExts') as HTMLInputElement)?.value || '',
    model_filter: (document.getElementById('modelFilter') as HTMLSelectElement)?.value || '',
    wd_model: (document.getElementById('wdModelFilter') as HTMLSelectElement)?.value || '',
    checkpoint: checkpointEl?.disabled ? '' : checkpointEl?.value || '',
    sort: (document.getElementById('sortBy') as HTMLSelectElement)?.value || '',
    limit: (document.getElementById('limit') as HTMLInputElement)?.value || '',
    in_prompt_regex: inPromptRegex ? 'true' : 'false',
    tag_regex: tagRegex ? 'true' : 'false',
    tag_case: context.tagCaseSensitive ? 'true' : 'false',
    min_width: (document.getElementById('minWidth') as HTMLInputElement)?.value || '',
    max_width: (document.getElementById('maxWidth') as HTMLInputElement)?.value || '',
    min_height: (document.getElementById('minHeight') as HTMLInputElement)?.value || '',
    max_height: (document.getElementById('maxHeight') as HTMLInputElement)?.value || '',
    or_tags: (document.getElementById('orTags') as HTMLInputElement)?.value || '',
    fav_only: (document.getElementById('favOnly') as HTMLInputElement)?.checked ? 'true' : 'false',
    ai_analyzed: (document.getElementById('aiAnalyzed') as HTMLInputElement)?.checked ? 'true' : 'false',
    has_tags: (document.getElementById('hasTags') as HTMLInputElement)?.checked ? 'true' : 'false',
    has_annotation: (document.getElementById('hasAnnotation') as HTMLInputElement)?.checked ? 'true' : 'false',
    has_sweep: (document.getElementById('hasSweep') as HTMLInputElement)?.checked ? 'true' : 'false',
    collection_id: (() => {
      const sel = document.getElementById('collectionFilter') as HTMLSelectElement | null;
      if (!sel || !sel.value) return '0';
      if (sel.value === 'all') return '-1';
      return sel.value;
    })(),
  });

  const chipInPath = (document.getElementById('inPath') as HTMLInputElement)?.value || '';
  if (chipInPath) params.set('in_path', chipInPath);

  const searchFromTs = getSearchFromTs();
  if (searchFromTs) {
    params.set('from_ts', searchFromTs);
    params.delete('from');
  }

  if (_isPerfEnabled()) {
    params.set('perf', '1');
  }
  params.set('defer_count', '1');

  params.set('offset', '0');
  return params;
}

function insertSkeletons(container: HTMLElement): void {
  const style = getComputedStyle(container);
  const minSize = parseInt(style.getPropertyValue('--grid-min-size')) || 300;
  const cols = Math.max(1, Math.floor(container.clientWidth / minSize));
  const count = Math.min(cols * 2, 12);
  const frag = document.createDocumentFragment();
  for (let i = 0; i < count; i++) {
    const card = document.createElement('div');
    card.className = 'result-card skeleton-card';
    card.setAttribute('aria-hidden', 'true');
    card.innerHTML = `<div class="skeleton-image"></div>
      <div class="result-info" style="padding:15px;display:flex;flex-direction:column;gap:8px;">
        <div class="skeleton-line skeleton-line-short"></div>
        <div class="skeleton-line skeleton-line-medium"></div>
        <div class="skeleton-line skeleton-line-short"></div>
      </div>`;
    frag.appendChild(card);
  }
  container.innerHTML = '';
  container.appendChild(frag);
}

export function beginLoading(): LoadingEls {
  const resultsEl = document.getElementById('results')!;
  const loadingEl = document.getElementById('loading')!;
  loadingEl.style.display = 'block';
  // Don't insert skeletons when virtual scroll is active.
  // If insertSkeletons empties container.innerHTML, VG's scroll handler runs update
  // with stale data, causing rowHeight to be calculated from incorrectly-sized skeleton
  // cards, which shifts the visible range and may prevent search results from displaying.
  if (!_isVirtualScrollActive()) {
    insertSkeletons(resultsEl);
  }
  resultsEl.setAttribute('aria-busy', 'true');
  getAppApi().startLoadingTips();
  return { resultsEl, loadingEl };
}

export function endLoading(loadingEls: LoadingEls): void {
  loadingEls.loadingEl.style.display = 'none';
  loadingEls.resultsEl.classList.remove('is-loading');
  loadingEls.resultsEl.setAttribute('aria-busy', 'false');
  getAppApi().stopLoadingTips();
}

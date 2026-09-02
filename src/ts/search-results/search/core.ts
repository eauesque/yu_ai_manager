import { searchPager } from './pagination';
import { refreshSearchStateI18n } from './state';
import { regexFilterAsync } from '../../workers/worker-client';
import type { FilterItem } from '../../workers/worker-protocol';
import { getAppApi } from '../../shared/browser-apis';
import { getCachedServerInfo } from '../../shared/runtime-state/server-info-state';

export let _regexEnabled: boolean = localStorage.getItem('regexEnabled') === 'true';

let _searchMode = 'tag';

function renderStats(
  statsEl: HTMLElement,
  fileCount: number,
  tagCount: number,
  sources?: Record<string, number>,
): void {
  const { tr } = getAppApi();
  while (statsEl.firstChild) statsEl.removeChild(statsEl.firstChild);

  const fileSpan = document.createElement('span');
  const fileLabel = sources
    ? tr('stats.ai_image_count', 'AI画像')
    : tr('stats.file_count_label', 'ファイル');
  fileSpan.textContent = `\ud83d\udcc1 ${fileCount.toLocaleString()} ${fileLabel}`;
  statsEl.appendChild(fileSpan);

  const tagSpan = document.createElement('span');
  tagSpan.textContent = `\ud83c\udff7\ufe0f ${tagCount.toLocaleString()} ${tr('stats.tag_count_label', 'タグ')}`;
  statsEl.appendChild(tagSpan);

  if (sources) {
    const pngCount = Object.entries(sources).filter(([k]) => k.endsWith('_png')).reduce((s, [, v]) => s + v, 0);
    const webpCount = Object.entries(sources).filter(([k]) => k.endsWith('_webp')).reduce((s, [, v]) => s + v, 0);
    const srcSpan = document.createElement('span');
    srcSpan.textContent = `\ud83d\udcca PNG: ${pngCount.toLocaleString()}, WebP: ${webpCount.toLocaleString()}`;
    statsEl.appendChild(srcSpan);
  }

  statsEl.classList.remove('header-info-loading');
  statsEl.classList.add('header-info-loaded');
  statsEl.style.opacity = '';
}

export function renderCachedStats(): boolean {
  const statsEl = document.getElementById('stats');
  if (!statsEl) return false;
  const cached = getCachedServerInfo();
  if (!cached || typeof cached.file_count !== 'number') return false;
  renderStats(statsEl, cached.file_count, cached.tag_count as number);
  return true;
}

export async function loadStats(): Promise<void> {
  const { apiFetch, escapeHtml, tr } = getAppApi();
  const statsEl = document.getElementById('stats');
  if (!statsEl) return;

  // If server-info cache is available, show file_count/tag_count early
  const cached = getCachedServerInfo();
  renderCachedStats();

  try {
    const response = await apiFetch('/api/stats');
    const data = await response.json();
    renderStats(statsEl, data.file_count, data.tag_count, data.sources);
  } catch (error) {
    console.error('Failed to load stats:', error);
    // Don't overwrite if already displayed from cache
    if (!cached || typeof cached.file_count !== 'number') {
      statsEl.innerHTML = `<span style="color:var(--muted,#999);">${escapeHtml(tr('stats.load_failed'))}</span>`;
      statsEl.style.opacity = '';
    }
  }
}

export function compileUserRegex(pattern: string): { re: RegExp | null; error: string | null } {
  const p = (pattern || '').trim();
  if (!p) return { re: null, error: null };

  let body = p;
  let flags = 'i';
  if (p.startsWith('/') && p.lastIndexOf('/') > 0) {
    const last = p.lastIndexOf('/');
    body = p.slice(1, last);
    const f = p.slice(last + 1);
    if (/^[gimsuy]*$/.test(f)) flags = f || 'i';
  }

  try {
    return { re: new RegExp(body, flags), error: null };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'invalid regex';
    return { re: null, error: msg };
  }
}

export interface SearchResult {
  positive?: string;
  negative?: string;
  artist?: string;
  path?: string;
  [key: string]: unknown;
}

export function applyClientRegexFilter(results: SearchResult[], regex: RegExp | null): SearchResult[] {
  if (!regex) return results;
  return (results || []).filter((r) => {
    const pos = r.positive || '';
    const neg = r.negative || '';
    const artist = r.artist || '';
    const path = r.path || '';
    const hay = pos + '\n' + neg + '\n' + artist + '\n' + path;
    return regex.test(hay);
  });
}

export function applyClientRegexFilterAsync(
  results: SearchResult[],
  regex: RegExp | null,
): Promise<SearchResult[]> {
  if (!regex) return Promise.resolve(results);
  return regexFilterAsync(
    results as FilterItem[],
    regex,
    applyClientRegexFilter as (items: FilterItem[], re: RegExp) => FilterItem[],
  ) as Promise<SearchResult[]>;
}

function _placeholderText(): string {
  const { tr } = getAppApi();
  const key = _regexEnabled ? 'search.placeholder.regex' : 'search.placeholder.plain';
  const val = tr(key);
  // tr-shim returns key itself when runtime not loaded yet; skip update in that case
  return (val && val !== key) ? val : '';
}

export function setSearchMode(_mode: string): void {
  _searchMode = 'tag';
  const ph = _placeholderText();
  const tagQuery = document.getElementById('tagQuery') as HTMLInputElement | null;
  if (ph && tagQuery) tagQuery.placeholder = ph;
}

export function onRegexToggleChange(): void {
  const cb = document.getElementById('regexToggle') as HTMLInputElement | null;
  _regexEnabled = cb?.checked || false;
  localStorage.setItem('regexEnabled', String(_regexEnabled));
  const tagRegex = document.getElementById('tagRegex') as HTMLInputElement | null;
  const inPromptRegex = document.getElementById('inPromptRegex') as HTMLInputElement | null;
  if (tagRegex) tagRegex.checked = _regexEnabled;
  if (inPromptRegex) inPromptRegex.checked = _regexEnabled;
  const ph = _placeholderText();
  const tagQuery = document.getElementById('tagQuery') as HTMLInputElement | null;
  if (ph && tagQuery) tagQuery.placeholder = ph;
}

export function initSearchCore(): void {
  setSearchMode(_searchMode);
  const cb = document.getElementById('regexToggle') as HTMLInputElement | null;
  if (cb) cb.checked = _regexEnabled;
  onRegexToggleChange();
  // Re-apply placeholder and search state once i18n runtime loads
  document.addEventListener('i18n:changed', () => {
    const ph = _placeholderText();
    const tagQuery = document.getElementById('tagQuery') as HTMLInputElement | null;
    if (ph && tagQuery) tagQuery.placeholder = ph;
    refreshSearchStateI18n();
  });

  if (typeof searchPager.configure === 'function') {
    searchPager.configure({
      isRegexEnabled: () => _regexEnabled,
      compileRegex: compileUserRegex,
      applyRegexFilter: applyClientRegexFilter as (results: unknown[], re: RegExp) => unknown[],
      applyRegexFilterAsync: applyClientRegexFilterAsync as (results: unknown[], re: RegExp) => Promise<unknown[]>,
    });
  }
}

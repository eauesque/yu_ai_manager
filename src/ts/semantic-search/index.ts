/**
 * Semantic search toggle and handler for the search page.
 *
 * Shows/hides the semantic search pill based on backend availability,
 * intercepts search form submit when semantic mode is active.
 */

import { getSearchResultsApi } from '../shared/browser-apis';

let _semanticEnabled = false;
let _semanticAvailable = false;

/** Check backend availability and show/hide the toggle pill. */
async function checkSemanticAvailability(): Promise<void> {
  try {
    const res = await fetch('/ext/hailo-semantic/api/status');
    if (!res.ok) return;
    const data = await res.json();
    // Any image encoder backend (Hailo, ONNX, CoreML) is sufficient.
    // Python/Rust runtime now reports backends as an array; older payloads used flags.
    const backends = Array.isArray(data.backends) ? data.backends : [];
    const anyBackend = Boolean(
      data.any_backend_available
      || data.hailo_available
      || backends.some((b: { available?: boolean }) => b?.available),
    );
    const textOk = data.text_encoder?.available !== false;
    _semanticAvailable = anyBackend && textOk;

    const pill = document.getElementById('semanticPill');
    if (!pill) return;

    // Show the pill whenever a backend + text encoder exist,
    // even if indexing is incomplete (user should know it exists)
    if (anyBackend && textOk) {
      pill.style.display = 'flex';
      // Gray out + explain when no index has been built yet
      const hasIndex = (data.indexed_count || 0) > 0;
      if (hasIndex) {
        pill.classList.remove('semantic-unindexed');
        pill.title = pill.dataset.i18nTitle || 'Semantic Search (CLIP)';
      } else {
        pill.classList.add('semantic-unindexed');
        pill.title = 'セマンティック検索 — Tools でインデックスを構築してください';
      }
      // Add index coverage badge
      const indexed = data.indexed_count || 0;
      const unindexed = data.unindexed_count || 0;
      const total = indexed + unindexed;
      if (total > 0) {
        const pct = Math.round((indexed / total) * 100);
        let badge = pill.querySelector('.semantic-badge') as HTMLElement | null;
        if (!badge) {
          badge = document.createElement('span');
          badge.className = 'semantic-badge';
          pill.appendChild(badge);
        }
        badge.textContent = pct < 100 ? `${pct}%` : '';
        badge.style.display = pct < 100 ? '' : 'none';
        if (pct < 100) {
          badge.title = `${indexed.toLocaleString()} / ${total.toLocaleString()} indexed`;
        }
      }
    } else {
      pill.style.display = 'none';
    }
  } catch {
    // Extension not loaded or unavailable
  }
}

/** Toggle handler for semantic search checkbox. */
export function onSemanticToggleChange(): void {
  const cb = document.getElementById('semanticToggle') as HTMLInputElement | null;
  _semanticEnabled = cb?.checked || false;

  const tagQuery = document.getElementById('tagQuery') as HTMLInputElement | null;
  if (tagQuery) {
    tagQuery.placeholder = _semanticEnabled
      ? 'e.g. blue sky, girl smiling, night city...'
      : '';
  }

  // Show/hide mode badge
  let modeBadge = document.getElementById('searchModeBadge');
  if (_semanticEnabled) {
    if (!modeBadge) {
      modeBadge = document.createElement('div');
      modeBadge.id = 'searchModeBadge';
      modeBadge.style.cssText =
        'display:inline-flex;align-items:center;gap:4px;font-size:11px;padding:2px 8px;border-radius:10px;background:rgba(139,92,246,0.15);border:1px solid rgba(139,92,246,0.4);color:rgb(167,139,250);margin-top:4px;';
      const panel = document.querySelector('.search-panel');
      if (panel) panel.insertBefore(modeBadge, panel.firstChild);
    }
    const label = (typeof window !== 'undefined' && typeof (window as unknown as Record<string, unknown>).tr === 'function')
      ? ((window as unknown as Record<string, unknown>).tr as (k: string, f: string) => string)('semantic_search.mode_active', '🧠 セマンティック検索モード — 自然言語で検索中')
      : '🧠 セマンティック検索モード — 自然言語で検索中';
    modeBadge.textContent = label;
    modeBadge.style.display = 'inline-flex';
  } else if (modeBadge) {
    modeBadge.style.display = 'none';
  }
}

/** Collect non-default filter values from the search form for semantic search. */
function collectFilterParams(): string {
  const parts: string[] = [];

  const fmt = (document.getElementById('fileFormat') as HTMLSelectElement)?.value || '';
  if (fmt && fmt !== 'all') {
    parts.push(`format=${encodeURIComponent(fmt)}`);
    const fmtExts = (document.getElementById('formatExts') as HTMLInputElement)?.value || '';
    if (fmtExts) parts.push(`format_exts=${encodeURIComponent(fmtExts)}`);
  }

  const from = (document.getElementById('fromDate') as HTMLInputElement)?.value || '';
  if (from) parts.push(`from=${encodeURIComponent(from)}`);

  const to = (document.getElementById('toDate') as HTMLInputElement)?.value || '';
  if (to) parts.push(`to=${encodeURIComponent(to)}`);

  const model = (document.getElementById('modelFilter') as HTMLSelectElement)?.value || '';
  if (model && model !== 'all') parts.push(`model_filter=${encodeURIComponent(model)}`);

  for (const id of ['minWidth', 'maxWidth', 'minHeight', 'maxHeight']) {
    const val = (document.getElementById(id) as HTMLInputElement)?.value || '';
    if (val) {
      // Convert camelCase to snake_case (minWidth -> min_width)
      const key = id.replace(/[A-Z]/g, c => '_' + c.toLowerCase());
      parts.push(`${key}=${encodeURIComponent(val)}`);
    }
  }

  const inPath = (document.getElementById('inPath') as HTMLInputElement)?.value || '';
  if (inPath) parts.push(`in_path=${encodeURIComponent(inPath)}`);

  const favOnly = (document.getElementById('favOnly') as HTMLInputElement)?.checked;
  if (favOnly) parts.push('fav_only=true');

  return parts.length > 0 ? '&' + parts.join('&') : '';
}

/** Run semantic search instead of tag search. */
async function runSemanticSearch(): Promise<boolean> {
  if (!_semanticEnabled || !_semanticAvailable) return false;

  const tagQuery = document.getElementById('tagQuery') as HTMLInputElement | null;
  const q = tagQuery?.value?.trim();
  if (!q) return false;

  const resultsEl = document.getElementById('results');
  const stateEl = document.getElementById('searchState');

  // Show loading state (keep old results visible during fetch)
  if (stateEl) {
    stateEl.style.display = '';
    const msg = document.createElement('div');
    msg.className = 'search-state-message';
    msg.textContent = 'Searching...';
    stateEl.replaceChildren(msg);
  }

  try {
    // Build URL with filter parameters from the search form
    const filterParams = collectFilterParams();
    const searchUrl = `/ext/hailo-semantic/api/search?q=${encodeURIComponent(q)}&limit=200${filterParams}`;
    const res = await fetch(searchUrl, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ message: `HTTP ${res.status}` }));
      if (stateEl) {
        stateEl.innerHTML = `<div class="search-state-message">${escapeHtml(err.message || 'Search failed')}</div>`;
      }
      return true;
    }

    const data = await res.json();

    if (!data.results || data.results.length === 0) {
      if (stateEl) {
        stateEl.innerHTML = '<div class="search-state-message">No semantic matches found</div>';
      }
      return true;
    }

    // Hide state message and clear old results just before rendering new ones
    if (stateEl) stateEl.style.display = 'none';
    if (resultsEl) resultsEl.textContent = '';

    // Show result count immediately
    const countEl = document.getElementById('resultsCount');
    if (countEl) {
      let info = `${data.results.length} semantic results`;
      if (data.timing) {
        info += ` (encode: ${data.timing.encode_ms}ms, search: ${data.timing.search_ms}ms)`;
      }
      countEl.textContent = info;
      countEl.style.display = '';
    }

    // Display results using existing grid
    displaySemanticResults(data.results, data.timing);
    return true;
  } catch (err) {
    if (stateEl) {
      stateEl.innerHTML = '<div class="search-state-message">Semantic search failed</div>';
    }
    return true;
  }
}

function escapeHtml(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

/** Display semantic search results in the existing grid. */
function displaySemanticResults(results: Array<{file_id: number; score: number; path: string}>, timing?: {encode_ms: number; search_ms: number}): void {
  const searchResultsApi = getSearchResultsApi();

  // Reset pagination state so infinite scroll doesn't load regular search results
  const pager = searchResultsApi.searchPager;
  if (pager) {
    pager.beginSearch(null);   // Clear search params
    pager.setHasMore(false);   // No more pages for semantic results
    pager.teardownScrollObserver?.();  // Remove scroll sentinel
  }

  // Convert semantic results to the format expected by displayResults
  const converted = results.map(r => ({
    id: r.file_id,
    path: r.path,
    semantic_score: r.score,
    positive: `Score: ${(r.score * 100).toFixed(1)}%`,
    negative: '',
    meta_source: 'semantic',
  }));

  searchResultsApi.displayResults?.(converted, converted.length);

  // Update results count
  const countEl = document.getElementById('resultsCount');
  if (countEl) {
    let info = `${results.length} semantic results`;
    if (timing) {
      info += ` (encode: ${timing.encode_ms}ms, search: ${timing.search_ms}ms)`;
    }
    countEl.textContent = info;
    countEl.style.display = '';
  }
}

/**
 * Try semantic search if enabled and available.
 * Called by the search bridge wrapper to intercept normal search.
 * Returns true if semantic search handled the query.
 */
export async function trySemanticSearch(): Promise<boolean> {
  if (!_semanticEnabled || !_semanticAvailable) return false;
  return runSemanticSearch();
}

// --- Init (deferred to avoid blocking initial page load) ---
setTimeout(checkSemanticAvailability, 3000);

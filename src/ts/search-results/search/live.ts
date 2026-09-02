import { runSearch } from './runner-core';
import { getAppApi, getNavApi } from '../../shared/browser-apis';

/* -- state -- */
let _typingTimer: ReturnType<typeof setTimeout> | null = null;
let _instantTimer: ReturnType<typeof setTimeout> | null = null;
let _searching = false;
let _queued = false;

/**
 * Typing debounce (ms).
 * Extended to 800ms for large databases (150K+ files) where queries
 * can take 200-500ms. At 400ms, intermediate keystrokes fire queries
 * that pile up and block the server.
 */
const TYPING_DEBOUNCE_MS = 800;

/** Select/checkbox debounce (ms) */
const INSTANT_DEBOUNCE_MS = 250;

/**
 * Minimum query length for auto-search.
 * Single-character queries on 150K files are expensive and rarely useful.
 * User can still press Enter to search with shorter queries.
 */
const MIN_AUTO_SEARCH_LEN = 2;

/* -- helpers -- */

export function isEnabled(): boolean {
  return localStorage.getItem('liveSearchEnabled') !== '0';
}

/** Run search with mutual-exclusion guard */
async function _doSearch(): Promise<void> {
  if (_searching) {
    _queued = true;
    return;
  }
  _searching = true;
  try {
    await runSearch();
  } catch (e) {
    console.warn('[live-search] error:', e);
  } finally {
    _searching = false;
    if (_queued) {
      _queued = false;
      _doSearch();
    }
  }
}

/** Validate regex syntax before firing live search */
function _regexValid(): boolean {
  const toggle = document.getElementById('regexToggle') as HTMLInputElement | null;
  if (!toggle || !toggle.checked) return true;
  const q = document.getElementById('tagQuery') as HTMLInputElement | null;
  if (!q || !q.value.trim()) return true;
  try {
    const tags = q.value.split(',');
    for (let i = 0; i < tags.length; i++) {
      const t = tags[i].trim().replace(/^-/, '');
      if (t) new RegExp(t);
    }
    return true;
  } catch (_e) {
    return false;
  }
}

/** Check if the main query is long enough for auto-search */
function _queryLongEnough(): boolean {
  const q = document.getElementById('tagQuery') as HTMLInputElement | null;
  const val = q?.value.trim() || '';
  // Empty query = show all (always OK)
  if (val === '') return true;
  return val.length >= MIN_AUTO_SEARCH_LEN;
}

/** Text input debounce */
export function triggerTyping(): void {
  if (!isEnabled()) return;
  if (_typingTimer) clearTimeout(_typingTimer);
  if (_instantTimer) clearTimeout(_instantTimer);
  _typingTimer = setTimeout(() => {
    _typingTimer = null;
    if (_queryLongEnough() && _regexValid()) _doSearch();
  }, TYPING_DEBOUNCE_MS);
}

/** Select / checkbox / toggle debounce */
export function triggerInstant(): void {
  if (!isEnabled()) return;
  if (_typingTimer) clearTimeout(_typingTimer);
  if (_instantTimer) clearTimeout(_instantTimer);
  _instantTimer = setTimeout(() => {
    _instantTimer = null;
    if (_regexValid()) _doSearch();
  }, INSTANT_DEBOUNCE_MS);
}

/* -- toggle UI -- */

function _updatePillUI(): void {
  const pill = document.getElementById('liveSearchPill');
  if (!pill) return;
  const cb = pill.querySelector('input[type="checkbox"]') as HTMLInputElement | null;
  if (cb) cb.checked = isEnabled();
}

export function toggleLiveSearch(): void {
  const on = !isEnabled();
  localStorage.setItem('liveSearchEnabled', on ? '1' : '0');
  _updatePillUI();
  const msg = on
    ? getAppApi().tr('search.live.toast_on', 'Live search: ON')
    : getAppApi().tr('search.live.toast_off', 'Live search: OFF');
  getNavApi().showToast(msg, 1500 as unknown as boolean);
}

/* -- condition fields event delegation -- */

function _initConditionFieldWatcher(): void {
  const container = document.getElementById('conditionFields');
  if (!container) return;

  container.addEventListener('input', (e: Event) => {
    const target = e.target as HTMLElement;
    const tag = target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') {
      const type = (target as HTMLInputElement).type;
      if (type === 'text' || type === 'number' || type === 'search' || type === 'date' || tag === 'TEXTAREA') {
        triggerTyping();
      }
    }
  });

  container.addEventListener('change', (e: Event) => {
    const target = e.target as HTMLElement;
    const tag = target.tagName;
    if (tag === 'SELECT') {
      triggerInstant();
    } else if (tag === 'INPUT') {
      const type = (target as HTMLInputElement).type;
      if (type === 'checkbox' || type === 'radio' || type === 'date') {
        triggerInstant();
      }
    }
  });
}

/* -- init -- */

export function initLiveSearch(): void {
  _updatePillUI();

  // #tagQuery input event
  const tagQuery = document.getElementById('tagQuery');
  if (tagQuery) {
    tagQuery.addEventListener('input', () => {
      triggerTyping();
    });
  }

  // #regexToggle change event
  const regexToggle = document.getElementById('regexToggle');
  if (regexToggle) {
    regexToggle.addEventListener('change', () => {
      triggerInstant();
    });
  }

  // Condition field event delegation
  _initConditionFieldWatcher();
}

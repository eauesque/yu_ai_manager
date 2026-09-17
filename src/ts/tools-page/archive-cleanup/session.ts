/**
 * archive-cleanup/session.ts -- sessionStorage persistence + beforeunload guard.
 *
 * Scan results and user selections survive accidental page navigation
 * via sessionStorage. A beforeunload warning fires when there are
 * unsaved (non-skip) selections.
 */

import type { LlmResult } from './render';
import {
  _currentPairs,
  _pairActions,
  _llmResults,
  _sortKey,
  _filterKey,
  _page,
  setCurrentPairs,
  setPairActions,
  setLlmResults,
  setSortKey,
  setFilterKey,
  setPage,
} from './state';

// ── SessionStorage keys ─────────────────────────────────────────

const _SS_PAIRS = 'ac_pairs';
const _SS_ACTIONS = 'ac_actions';
const _SS_STATE = 'ac_state';
const _SS_LLM = 'ac_llm';

// ── Save / Clear / Restore ──────────────────────────────────────

export function _saveSession(): void {
  try {
    sessionStorage.setItem(_SS_PAIRS, JSON.stringify(_currentPairs));
    const actObj: Record<string, string> = {};
    _pairActions.forEach((v, k) => { actObj[String(k)] = v; });
    sessionStorage.setItem(_SS_ACTIONS, JSON.stringify(actObj));
    sessionStorage.setItem(_SS_STATE, JSON.stringify({
      sortKey: _sortKey, filterKey: _filterKey, page: _page,
    }));
    const llmObj: Record<string, LlmResult> = {};
    _llmResults.forEach((v, k) => { llmObj[String(k)] = v; });
    sessionStorage.setItem(_SS_LLM, JSON.stringify(llmObj));
  } catch { /* quota exceeded -- ignore */ }
}

export function _clearSession(): void {
  sessionStorage.removeItem(_SS_PAIRS);
  sessionStorage.removeItem(_SS_ACTIONS);
  sessionStorage.removeItem(_SS_STATE);
  sessionStorage.removeItem(_SS_LLM);
}

export function _restoreSession(): boolean {
  try {
    const raw = sessionStorage.getItem(_SS_PAIRS);
    if (!raw) return false;
    const pairs = JSON.parse(raw);
    if (!Array.isArray(pairs) || pairs.length === 0) return false;

    setCurrentPairs(pairs);

    const actRaw = sessionStorage.getItem(_SS_ACTIONS);
    if (actRaw) {
      const actObj: Record<string, string> = JSON.parse(actRaw);
      const m = new Map<number, string>();
      for (const [k, v] of Object.entries(actObj)) {
        m.set(Number(k), v);
      }
      setPairActions(m);
    }

    const stRaw = sessionStorage.getItem(_SS_STATE);
    if (stRaw) {
      const st = JSON.parse(stRaw);
      setSortKey(st.sortKey || 'rate_desc');
      setFilterKey(st.filterKey || 'all');
      setPage(st.page || 1);
    }

    const llmRaw = sessionStorage.getItem(_SS_LLM);
    if (llmRaw) {
      const llmObj: Record<string, LlmResult> = JSON.parse(llmRaw);
      const m = new Map<number, LlmResult>();
      for (const [k, v] of Object.entries(llmObj)) {
        m.set(Number(k), v);
      }
      setLlmResults(m);
    }
    return true;
  } catch {
    return false;
  }
}

// ── Beforeunload guard ──────────────────────────────────────────

function _hasNonSkipActions(): boolean {
  for (const v of _pairActions.values()) {
    if (v !== 'skip') return true;
  }
  return false;
}

function _onBeforeUnload(e: BeforeUnloadEvent): void {
  if (_currentPairs.length > 0 && _hasNonSkipActions()) {
    e.preventDefault();
  }
}

export function _installGuard(): void {
  window.addEventListener('beforeunload', _onBeforeUnload);
}

export function _removeGuard(): void {
  window.removeEventListener('beforeunload', _onBeforeUnload);
}

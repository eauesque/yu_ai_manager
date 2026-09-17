/**
 * archive-cleanup/state.ts -- shared mutable state + helpers.
 *
 * All modules in archive-cleanup/ import state from here to avoid
 * circular dependencies.
 */

import { getAppApi } from '../../shared/browser-apis';
import type { ArchivePair, LlmResult } from './render';

// ── Module-level mutable state ──────────────────────────────────

export let _currentPairs: ArchivePair[] = [];
export let _pairActions: Map<number, string> = new Map();
export let _llmResults: Map<number, LlmResult> = new Map();
export let _sortKey = 'rate_desc';
export let _filterKey = 'all';
export let _page = 1;

// ── Setters (needed because `export let` bindings are read-only
//    from the importer side) ─────────────────────────────────────

export function setCurrentPairs(v: ArchivePair[]): void { _currentPairs = v; }
export function setPairActions(v: Map<number, string>): void { _pairActions = v; }
export function setLlmResults(v: Map<number, LlmResult>): void { _llmResults = v; }
export function setSortKey(v: string): void { _sortKey = v; }
export function setFilterKey(v: string): void { _filterKey = v; }
export function setPage(v: number): void { _page = v; }

// ── Shared helpers ──────────────────────────────────────────────

export function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback) || fallback;
}

export function _getDisplayRate(p: ArchivePair): number {
  return p.adjusted_match_rate != null ? p.adjusted_match_rate : p.match_rate;
}

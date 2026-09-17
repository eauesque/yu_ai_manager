/**
 * Adaptive runtime i18n — message catalog loading and translation.
 * Converted from static/js/main/main-adaptive-runtime-i18n.js
 */

import { state, AdaptiveMessages } from './adaptive-runtime-state';

function normalizeAdaptiveCatalog(raw: unknown): AdaptiveMessages {
  if (!raw || typeof raw !== 'object') return state.DEFAULT_ADAPTIVE_MESSAGES;
  const src = raw as Record<string, Record<string, unknown[]>>;
  const out: AdaptiveMessages = { loadingTipsByTime: {}, emptySearchCheersByTime: {} };
  for (const rootKey of ['loadingTipsByTime', 'emptySearchCheersByTime'] as const) {
    const bucket = src[rootKey];
    if (!bucket || typeof bucket !== 'object') continue;
    for (const [k, v] of Object.entries(bucket)) {
      if (Array.isArray(v)) out[rootKey][k] = v.filter((x): x is string => typeof x === 'string' && x.trim() !== '');
    }
  }
  if (!Array.isArray(out.loadingTipsByTime.common) || out.loadingTipsByTime.common.length === 0) {
    out.loadingTipsByTime.common = state.DEFAULT_ADAPTIVE_MESSAGES.loadingTipsByTime.common.slice();
  }
  if (!Array.isArray(out.emptySearchCheersByTime.common) || out.emptySearchCheersByTime.common.length === 0) {
    out.emptySearchCheersByTime.common = state.DEFAULT_ADAPTIVE_MESSAGES.emptySearchCheersByTime.common.slice();
  }
  return out;
}

async function loadAdaptiveMessagesForLang(lang: string): Promise<AdaptiveMessages> {
  const url = `/static/i18n/adaptive_messages.${lang}.json?v=${state.ADAPTIVE_MESSAGES_VERSION}`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`adaptive message load failed: ${res.status}`);
  return normalizeAdaptiveCatalog(await res.json());
}

export async function refreshAdaptiveMessages(lang: string): Promise<void> {
  const primary = String(lang || '').toLowerCase().split('-')[0];
  const candidates = Array.from(new Set([primary, 'en', 'ja'].filter(Boolean)));
  for (const c of candidates) {
    try {
      state.adaptiveMessages = await loadAdaptiveMessagesForLang(c);
      return;
    } catch {
      // try next candidate
    }
  }
  state.adaptiveMessages = state.DEFAULT_ADAPTIVE_MESSAGES;
}

export function getAdaptiveCatalog(type: string): Record<string, string[]> {
  if (type === 'loading') return state.adaptiveMessages.loadingTipsByTime || {};
  if (type === 'empty') return state.adaptiveMessages.emptySearchCheersByTime || {};
  return {};
}

function getByPath(obj: Record<string, unknown>, path: string): unknown {
  if (!obj || !path) return undefined;
  // Try flat key first (e.g. "settings_schema.server_pin" as a literal key)
  if (path in obj) return obj[path];
  // Fall back to nested path traversal
  let cur: unknown = obj;
  for (const part of String(path).split('.')) {
    if (!cur || typeof cur !== 'object' || !(part in (cur as Record<string, unknown>))) return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return cur;
}

function interpolate(template: unknown, vars: Record<string, unknown> | null): string {
  if (!vars || typeof vars !== 'object') return String(template ?? '');
  return String(template ?? '').replace(/\{([a-zA-Z0-9_]+)\}/g, (_: string, k: string) => {
    const v = vars[k];
    return v == null ? '' : String(v);
  });
}

export function tr(path: string, a: unknown = null, b: unknown = null): string {
  const v = getByPath(state.uiRuntimeTexts as Record<string, unknown>, path);
  let vars: Record<string, unknown> | null = null;
  if (a && typeof a === 'object' && !Array.isArray(a)) vars = a as Record<string, unknown>;
  else if (b && typeof b === 'object' && !Array.isArray(b)) vars = b as Record<string, unknown>;
  const fallback = typeof a === 'string' ? a : (typeof b === 'string' ? b : null);
  const base = typeof v === 'string' && v ? v : (fallback != null ? fallback : path);
  return interpolate(base, vars);
}

export function trList(path: string, fallback: string[] = []): string[] {
  const v = getByPath(state.uiRuntimeTexts as Record<string, unknown>, path);
  if (Array.isArray(v)) return v.filter((x): x is string => typeof x === 'string' && x.trim() !== '');
  return Array.isArray(fallback) ? fallback : [];
}

async function loadUiRuntimeForLang(lang: string): Promise<Record<string, unknown>> {
  const url = `/static/i18n/ui_runtime.${lang}.json?v=${state.UI_RUNTIME_VERSION}`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`ui runtime load failed: ${res.status}`);
  const json = await res.json();
  return json && typeof json === 'object' ? json : {};
}

export async function refreshUiRuntime(lang: string): Promise<void> {
  const primary = String(lang || '').toLowerCase().split('-')[0];
  const candidates = Array.from(new Set([primary, 'en', 'ja'].filter(Boolean)));
  for (const c of candidates) {
    try {
      state.uiRuntimeTexts = await loadUiRuntimeForLang(c);
      return;
    } catch {
      // try next candidate
    }
  }
  state.uiRuntimeTexts = state.DEFAULT_UI_RUNTIME;
}

// Wire into shared state
state.refreshAdaptiveMessages = refreshAdaptiveMessages;
state.refreshUiRuntime = refreshUiRuntime;
state.getAdaptiveCatalog = getAdaptiveCatalog;
state.tr = tr;
state.trList = trList;

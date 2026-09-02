/**
 * tr-runtime-lite — Lightweight tr() for non-index pages.
 * Loads ui_runtime dict and provides window.tr(path, fallback).
 * Converted from static/js/i18n/tr-runtime-lite.js
 */

import { getTrRuntimeDict, setTrRuntimeDict, setTrRuntimeLoaded } from './runtime-state';

function getByPath(obj: Record<string, unknown>, path: string): unknown {
  if (!obj || !path) return undefined;
  // Try flat key first (e.g. "settings_schema.server_pin" as a literal key)
  if (path in obj) return obj[path];
  // Fall back to nested path traversal
  let cur: unknown = obj;
  const parts = String(path).split('.');
  for (let i = 0; i < parts.length; i++) {
    if (!cur || typeof cur !== 'object' || !(parts[i] in (cur as Record<string, unknown>)))
      return undefined;
    cur = (cur as Record<string, unknown>)[parts[i]];
  }
  return cur;
}

function interpolate(template: unknown, vars: Record<string, unknown> | null): string {
  if (!vars || typeof vars !== 'object') return String(template == null ? '' : template);
  return String(template == null ? '' : template).replace(
    /\{([a-zA-Z0-9_]+)\}/g,
    (_: string, k: string) => {
      const v = vars[k];
      return v == null ? '' : String(v);
    },
  );
}

function tr(path: string, a?: unknown, b?: unknown): string {
  const v = getByPath(getTrRuntimeDict(), path);
  let vars: Record<string, unknown> | null = null;
  if (a && typeof a === 'object' && !Array.isArray(a)) vars = a as Record<string, unknown>;
  else if (b && typeof b === 'object' && !Array.isArray(b)) vars = b as Record<string, unknown>;
  const fallback = typeof a === 'string' ? a : typeof b === 'string' ? b : '';
  // Return found value, else explicit fallback, else empty string.
  // This ensures (tr('key') || 'inline fallback') pattern works correctly.
  const base = typeof v === 'string' && v ? v : fallback;
  return interpolate(base, vars);
}

window.tr = tr;

function detectLang(): string {
  const stored = (localStorage.getItem('lang') || '').trim().toLowerCase();
  if (stored) return stored;
  const nav = String(navigator.language || 'en').toLowerCase();
  if (nav.startsWith('ja')) return 'ja';
  if (nav === 'zh-tw' || nav === 'zh-hant') return 'zh-tw';
  if (nav.startsWith('zh')) return 'zh-cn';
  if (nav.startsWith('ko')) return 'ko';
  return 'en';
}

function loadDict(lang: string): Promise<Record<string, unknown>> {
  const url = '/static/i18n/ui_runtime.' + lang + '.json?v=20260408';
  return fetch(url, { cache: 'no-store' }).then(function (res) {
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  });
}

function markI18nReady(): void {
  document.body?.classList.add('i18n-ready');
}

function init(): void {
  const lang = detectLang();
  loadDict(lang)
    .then(function (data) {
      setTrRuntimeDict(data && typeof data === 'object' ? data : {});
      setTrRuntimeLoaded(true);
      document.dispatchEvent(new CustomEvent('tr-runtime:ready', { detail: { lang: lang } }));
      markI18nReady();
    })
    .catch(function () {
      markI18nReady();
      if (lang !== 'en') {
        loadDict('en')
          .then(function (data) {
            setTrRuntimeDict(data && typeof data === 'object' ? data : {});
            setTrRuntimeLoaded(true);
            document.dispatchEvent(
              new CustomEvent('tr-runtime:ready', { detail: { lang: 'en' } }),
            );
          })
          .catch(function () {});
      }
    });
}

init();

/**
 * i18n core shared — language detection, dictionary loading, DOM translation.
 * Converted from static/js/i18n/i18n-core-shared.js
 */

import { setI18nDictionary } from './runtime-state';

export const DEFAULT_LANG: string = (() => {
  const nav = (navigator.language || '').toLowerCase();
  if (nav.startsWith('ja')) return 'ja';
  if (nav === 'zh-tw' || nav === 'zh-hant') return 'zh-tw';
  if (nav.startsWith('zh')) return 'zh-cn';
  if (nav.startsWith('ko')) return 'ko';
  return 'en';
})();

function getSupportedLangs(): string[] {
  const sel = document.getElementById('langSelect') as HTMLSelectElement | null;
  if (!sel) return ['en', 'ja'];
  const vals = Array.from(sel.options || [])
    .map((o) => (o && o.value ? String(o.value).toLowerCase() : ''))
    .filter(Boolean);
  return Array.from(new Set(vals.length ? vals : ['en', 'ja']));
}

export function normalizeLang(lang: string | null): string {
  const supported = getSupportedLangs();
  const fallback = supported.includes(DEFAULT_LANG) ? DEFAULT_LANG : supported[0] || 'en';

  if (!lang) return fallback;
  const lowered = String(lang).toLowerCase();
  const primary = lowered.split('-')[0];
  if (supported.includes(lowered)) return lowered;
  if (supported.includes(primary)) return primary;
  if (primary === 'jp' && supported.includes('ja')) return 'ja';
  return fallback;
}

export async function loadDict(lang: string): Promise<Record<string, string>> {
  const url = `/static/i18n/${lang}.json?v=20260408`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`i18n load failed: ${res.status}`);
  return await res.json();
}

// Platform-aware modifier label: "Ctrl/Cmd" in source strings is rewritten to the
// host-appropriate token so hint text doesn't show both on every OS. Detection uses
// userAgentData.platform when available (Chromium), falling back to legacy navigator.platform.
function platformModifierLabel(): string {
  const uaData = (navigator as unknown as { userAgentData?: { platform?: string } }).userAgentData;
  const platform = (uaData?.platform || navigator.platform || '').toLowerCase();
  const ua = (navigator.userAgent || '').toLowerCase();
  const isMac = platform.includes('mac') || ua.includes('mac os');
  return isMac ? 'Cmd' : 'Ctrl';
}

function dictGet(dict: Record<string, string>, key: string): string {
  if (!dict || !key) return '';
  if (Object.prototype.hasOwnProperty.call(dict, key)) {
    return String(dict[key]).replace(/Ctrl\/Cmd/g, platformModifierLabel());
  }
  return '';
}

export function applyTranslations(dict: Record<string, string>, lang: string): void {
  document.documentElement.setAttribute('lang', lang);
  setI18nDictionary(lang, dict);
  // Reveal body after translations are applied to prevent FOUC
  document.body.classList.add('i18n-ready');

  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const key = el.getAttribute('data-i18n');
    const val = dictGet(dict, key || '');
    if (val) el.textContent = val;
  });

  const attrMap: [string, string][] = [
    ['data-i18n-title', 'title'],
    ['data-i18n-aria-label', 'aria-label'],
    ['data-i18n-placeholder', 'placeholder'],
    ['data-i18n-label', 'label'],
  ];
  for (const [dataAttr, realAttr] of attrMap) {
    document.querySelectorAll(`[${dataAttr}]`).forEach((el) => {
      const key = el.getAttribute(dataAttr);
      const val = dictGet(dict, key || '');
      if (val) el.setAttribute(realAttr, val);
    });
  }

  const sel = document.getElementById('langSelect') as HTMLSelectElement | null;
  if (sel) sel.value = lang;

  document.dispatchEvent(
    new CustomEvent('i18n:changed', {
      detail: { lang, dict },
    })
  );
}

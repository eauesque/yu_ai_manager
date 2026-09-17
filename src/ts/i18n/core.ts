/**
 * i18n core — setLang / initLangSelect.
 * Converted from static/js/i18n/i18n-core.js
 */

import { normalizeLang, loadDict, applyTranslations } from './core-shared';

export async function setLang(lang: string): Promise<void> {
  const normalized = normalizeLang(lang);
  localStorage.setItem('lang', normalized);

  try {
    const dict = await loadDict(normalized);
    applyTranslations(dict, normalized);
    return;
  } catch (e) {
    console.warn('i18n: failed to load lang ' + normalized + ', falling back to EN:', e);
  }

  try {
    if (normalized !== 'en') {
      const dict = await loadDict('en');
      applyTranslations(dict, 'en');
      localStorage.setItem('lang', 'en');
      return;
    }
  } catch (e2) {
    console.warn('i18n: all dictionaries failed, using defaults:', e2);
  }

  document.documentElement.setAttribute('lang', normalized);
}

export function initLangSelect(): void {
  const sel = document.getElementById('langSelect') as HTMLSelectElement | null;
  if (!sel) return;
  sel.addEventListener('change', async () => {
    const next = normalizeLang(sel.value);
    await setLang(next);
  });
}

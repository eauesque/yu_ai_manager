/**
 * i18n auto-init — DOMContentLoaded bootstrap.
 * Converted from static/js/i18n/i18n.js
 */

import { normalizeLang, DEFAULT_LANG } from './core-shared';
import { setLang, initLangSelect } from './core';

document.addEventListener('DOMContentLoaded', async () => {
  // Fallback: reveal body if i18n takes > 800ms (network slow or JS error)
  const foucTimer = setTimeout(() => document.body.classList.add('i18n-ready'), 800);
  initLangSelect();
  const stored = localStorage.getItem('lang');
  const initial = normalizeLang(stored || navigator.language || DEFAULT_LANG);
  await setLang(initial);
  clearTimeout(foucTimer);
});

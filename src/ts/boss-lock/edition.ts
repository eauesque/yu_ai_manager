/**
 * boss-lock / edition — generate random financial-newspaper editions
 * for "boss mode" camouflage overlay.
 *
 * Re-exports types and data from split modules for backward compatibility.
 */

import { getCurrentLang, pickRandom, pickRandomUnique } from './utils';

// Re-export types and data for external consumers
export type { BossModeEdition, Theme, ThemeBase } from './edition-data';
export {
  BRANDS_JA, BRANDS_EN, BRANDS_ZH, BRANDS_KO,
  BYLINES_JA, BYLINES_EN, BYLINES_ZH, BYLINES_KO,
  BREAKING_JA, BREAKING_EN, BREAKING_ZH, BREAKING_KO,
  SECTIONS, LABELS, TICKERS,
} from './edition-data';
export {
  THEMES_JA, THEMES_EN, THEMES_ZH, THEMES_KO,
  selectLocaleThemes,
} from './edition-themes';

import {
  BRANDS_JA, BRANDS_EN, BRANDS_ZH, BRANDS_KO,
  BYLINES_JA, BYLINES_EN, BYLINES_ZH, BYLINES_KO,
  BREAKING_JA, BREAKING_EN, BREAKING_ZH, BREAKING_KO,
  SECTIONS, LABELS, TICKERS,
} from './edition-data';
import type { BossModeEdition, Theme } from './edition-data';
import { selectLocaleThemes } from './edition-themes';

/* ------------------------------------------------------------------ */
/*  Locale data selector                                               */
/* ------------------------------------------------------------------ */

/** Select locale-specific data pools (brands, bylines, breaking) based on UI language. */
function selectLocaleData(lang: string) {
  const l = String(lang || '').toLowerCase();
  if (l.startsWith('ja')) return { brands: BRANDS_JA, bylines: BYLINES_JA, breaking: BREAKING_JA };
  if (l.startsWith('zh')) return { brands: BRANDS_ZH, bylines: BYLINES_ZH, breaking: BREAKING_ZH };
  if (l.startsWith('ko')) return { brands: BRANDS_KO, bylines: BYLINES_KO, breaking: BREAKING_KO };
  return { brands: BRANDS_EN, bylines: BYLINES_EN, breaking: BREAKING_EN };
}

/* ------------------------------------------------------------------ */
/*  Builder                                                            */
/* ------------------------------------------------------------------ */

/** Build a randomised financial-newspaper edition for the boss-mode overlay. */
export function buildBossModeEdition(): BossModeEdition {
  const lang = getCurrentLang();
  const locale = selectLocaleData(lang);
  const themes = selectLocaleThemes(lang);

  const brands       = locale.brands;
  const bylines      = locale.bylines;
  const breakingTexts = locale.breaking;

  const theme = (pickRandom(themes) || themes[0]) as Theme;

  const quotes = TICKERS.map((k) => {
    const base  = Number((theme.base as unknown as Record<string, number>)[k] || 0);
    const drift = Math.random() * 0.22 - 0.11;
    const v     = base + drift;
    const sign  = v >= 0 ? '+' : '-';
    return `${k}  ${sign}${Math.abs(v).toFixed(2)}%`;
  });

  return {
    brand:        pickRandom(brands) as string,
    sectionLine:  pickRandomUnique(SECTIONS, 5),
    deskLabel:    pickRandom(LABELS) as string,
    byline:       pickRandom(bylines) as string,
    showBreaking: Math.random() < 0.38,
    breakingText: pickRandom(breakingTexts) as string,
    headline:     theme.headline,
    subhead:      theme.subhead,
    stories:      pickRandomUnique(theme.stories || [], 4),
    quotes,
  };
}

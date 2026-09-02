/**
 * Stats page theme toggle — dark/light mode with system preference detection.
 * Converted from static/js/stats/stats-theme.js
 *
 * NOTE: nav/theme.ts already applies the theme (including custom themes)
 * before this runs. This module skips if a custom theme is active.
 */

import { getActiveThemeId } from '../theme-system/storage';

function applyTheme(mode: string): void {
  if (mode === 'atelier-light' || mode === 'atelier-dark') return;
  const dark = mode === 'dark';
  document.body.classList.toggle('dark', dark);
  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = dark ? '\u2600\uFE0F' : '\uD83C\uDF19';
}

function getSystemTheme(): string {
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

export function initStatsThemeToggle(): void {
  // Skip if a custom theme is active — nav.js already applied it
  if (getActiveThemeId()) return;

  const saved = localStorage.getItem('themeMode');
  const mode = saved || getSystemTheme();
  applyTheme(mode);

  if (window.matchMedia) {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (): void => {
      if (!localStorage.getItem('themeMode')) applyTheme(getSystemTheme());
    };
    try {
      mq.addEventListener('change', handler);
    } catch {
      try {
        mq.addListener(handler);
      } catch {
        // ignore
      }
    }
  }
}

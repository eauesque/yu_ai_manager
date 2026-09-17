/**
 * Inspect page theme toggle — simplified dark/light toggle.
 * Converted from static/js/inspect/inspect-theme.js
 *
 * NOTE: nav/theme.ts already applies the theme (including custom themes)
 * before this runs. This module skips if a custom theme is active.
 */

import { getActiveThemeId } from '../theme-system/storage';

function applyTheme(mode: string): void {
  if (mode === 'atelier-light' || mode === 'atelier-dark') return;
  document.body.classList.toggle('dark', mode === 'dark');
  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = mode === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19';
}

export function initInspectTheme(): void {
  // Skip if a custom theme is active — nav.js already applied it
  if (getActiveThemeId()) return;

  const saved = localStorage.getItem('themeMode');
  const mode = saved || (
    window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light'
  );
  applyTheme(mode);
}

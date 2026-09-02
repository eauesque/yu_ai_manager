/**
 * ui/theme.ts — Dark/light theme toggle with system preference detection.
 * Converted from runtime-ui-theme.js
 *
 * NOTE: nav/theme.ts already applies the theme (including custom themes)
 * before this runs. This module only handles the legacy dark/light toggle
 * and skips if a custom theme is already active.
 */

import { getActiveThemeId } from '../../theme-system/storage';

export function applyTheme(mode: string): void {
  // Atelier modes are handled by nav/theme.ts; don't fight it from here.
  if (mode === 'atelier-light' || mode === 'atelier-dark') return;
  const dark = mode === 'dark';
  document.body.classList.toggle('dark', dark);
  const icon = dark ? '\u2600\uFE0F' : '\uD83C\uDF19';
  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = icon;
  const btnNav = document.getElementById('themeToggleNav');
  if (btnNav) btnNav.textContent = icon;
}

export function getSystemTheme(): string {
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

export function initThemeToggle(): void {
  // Skip if a custom theme is active — nav.js already applied it
  if (getActiveThemeId()) return;

  const saved = localStorage.getItem('themeMode');
  const mode = saved || getSystemTheme();
  applyTheme(mode);

  if (!saved && window.matchMedia) {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (): void => applyTheme(getSystemTheme());
    try {
      mq.addEventListener('change', handler);
    } catch {
      // Fallback for older browsers
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (mq as any).addListener(handler);
    }
  }
}

/**
 * Settings page — theme initialization (dark/light toggle).
 * Converted from the theme section of static/js/settings/settings-theme-init.js
 *
 * Extended to support custom theme system.
 */

import { applyTheme, clearCustomTheme, getActiveTheme } from '../theme-system/apply';
import { setActiveThemeId } from '../theme-system/storage';

function applyBaseTheme(mode: string): void {
  if (mode === 'atelier-light' || mode === 'atelier-dark') return;
  const dark = mode === 'dark';
  const icon = dark ? '\u2600\uFE0F' : '\uD83C\uDF19';
  document.body.classList.toggle('dark', dark);
  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = icon;
  const btnNav = document.getElementById('themeToggleNav');
  if (btnNav) btnNav.textContent = icon;
}

export function initTheme(): void {
  // Check for active custom theme first
  const activeTheme = getActiveTheme();
  if (activeTheme) {
    applyTheme(activeTheme);
    return;
  }

  // Fallback to standard dark/light toggle
  const saved = localStorage.getItem('themeMode');
  const systemDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  applyBaseTheme(saved || (systemDark ? 'dark' : 'light'));

  const ids = ['themeToggle', 'themeToggleNav'] as const;
  for (const id of ids) {
    const btn = document.getElementById(id);
    if (!btn || (btn as HTMLElement & { dataset: DOMStringMap }).dataset.bound) continue;
    btn.dataset.bound = '1';
    btn.addEventListener('click', () => {
      // Switching dark/light clears custom theme
      clearCustomTheme();
      setActiveThemeId(null);
      const next = document.body.classList.contains('dark') ? 'light' : 'dark';
      localStorage.setItem('themeMode', next);
      applyBaseTheme(next);
    });
  }
}

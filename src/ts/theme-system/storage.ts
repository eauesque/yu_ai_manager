/**
 * Theme persistence via localStorage.
 */

import type { ThemeData } from './types';

const CUSTOM_THEMES_KEY = 'customThemes';
const ACTIVE_THEME_KEY = 'activeThemeId';

export function loadCustomThemes(): ThemeData[] {
  try {
    const raw = localStorage.getItem(CUSTOM_THEMES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveCustomThemes(themes: ThemeData[]): void {
  localStorage.setItem(CUSTOM_THEMES_KEY, JSON.stringify(themes));
}

export function addCustomTheme(theme: ThemeData): void {
  const themes = loadCustomThemes();
  const idx = themes.findIndex(t => t.id === theme.id);
  if (idx >= 0) {
    themes[idx] = theme;
  } else {
    themes.push(theme);
  }
  saveCustomThemes(themes);
}

export function deleteCustomTheme(id: string): void {
  const themes = loadCustomThemes().filter(t => t.id !== id);
  saveCustomThemes(themes);
  if (getActiveThemeId() === id) {
    setActiveThemeId(null);
  }
}

export function getActiveThemeId(): string | null {
  return localStorage.getItem(ACTIVE_THEME_KEY);
}

export function setActiveThemeId(id: string | null): void {
  if (id) {
    localStorage.setItem(ACTIVE_THEME_KEY, id);
  } else {
    localStorage.removeItem(ACTIVE_THEME_KEY);
  }
}

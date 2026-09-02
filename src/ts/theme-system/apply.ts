/**
 * Theme application engine — sets CSS variables on document.body.
 * body.style (inline) overrides body.dark {} CSS rules by specificity,
 * ensuring preset/custom theme colors propagate to all descendants.
 */

import type { ThemeData } from './types';
import { getPresetById } from './presets';
import { getActiveThemeId, loadCustomThemes } from './storage';

const CSS_VAR_MAP: Record<string, string> = {
  bg: '--bg',
  card: '--card',
  text: '--text',
  muted: '--muted',
  border: '--border',
  accent: '--accent',
  btnBg: '--btn-bg',
  btnText: '--btn-text',
  btnHover: '--btn-hover',
};

/** Derived CSS variables that extensions depend on.
 *  These are auto-computed from the core 9 colors. */
const DERIVED_VARS = [
  '--fg', '--fg-muted', '--bg-card', '--bg-input', '--bg-hover',
  '--accent-bg', '--muted-accessible', '--tooltip-bg', '--tooltip-text',
  '--mark-bg', '--mark-fg', '--success', '--error',
] as const;

export function applyTheme(theme: ThemeData): void {
  const style = document.body.style;
  const colors = theme.colors;

  // Set base dark/light mode
  const isDark = theme.base === 'dark';
  document.body.classList.toggle('dark', isDark);
  document.documentElement.style.setProperty('color-scheme', isDark ? 'dark' : 'light');

  // Remove retro class (custom theme overrides it)
  document.body.classList.remove('theme-retro');

  // Apply color variables
  for (const [key, cssVar] of Object.entries(CSS_VAR_MAP)) {
    const val = (colors as unknown as Record<string, string | undefined>)[key];
    if (val) {
      style.setProperty(cssVar, val);
    }
  }

  // Fallback: btnBg defaults to card, btnText to text, btnHover auto
  if (!colors.btnBg) style.setProperty('--btn-bg', colors.card);
  if (!colors.btnText) style.setProperty('--btn-text', colors.text);
  if (!colors.btnHover) {
    style.setProperty('--btn-hover', isDark
      ? lighten(colors.card, 0.08)
      : darken(colors.card, 0.04));
  }

  // Derived variables — ensure extensions pick up theme colors
  style.setProperty('--fg', colors.text);
  style.setProperty('--fg-muted', colors.muted);
  style.setProperty('--bg-card', colors.card);
  style.setProperty('--bg-input', colors.card);
  style.setProperty('--bg-hover', isDark
    ? lighten(colors.card, 0.06)
    : darken(colors.card, 0.04));
  style.setProperty('--muted-accessible', isDark
    ? lighten(colors.muted, 0.06)
    : darken(colors.muted, 0.08));
  style.setProperty('--accent-bg', hexToRgba(colors.accent, isDark ? 0.15 : 0.10));
  style.setProperty('--tooltip-bg', isDark ? 'rgba(0,0,0,0.92)' : 'rgba(0,0,0,0.85)');
  style.setProperty('--tooltip-text', '#fff');
  style.setProperty('--mark-bg', isDark
    ? 'rgba(250,204,21,0.3)'
    : 'rgba(250,204,21,0.45)');
  style.setProperty('--mark-fg', colors.text);
  style.setProperty('--success', isDark ? '#66bb6a' : '#2e7d32');
  style.setProperty('--error', isDark ? '#ef5350' : '#d32f2f');

  // Effects
  if (theme.effects?.shadow) {
    style.setProperty('--shadow', theme.effects.shadow);
  }
  if (theme.effects?.glow) {
    document.body.classList.add('theme-glow');
  } else {
    document.body.classList.remove('theme-glow');
  }

  // Update toggle button icons
  const icon = isDark ? '\u2600\uFE0F' : '\uD83C\uDF19';
  const btn = document.getElementById('themeToggle');
  if (btn) btn.textContent = icon;
  const btnNav = document.getElementById('themeToggleNav');
  if (btnNav) btnNav.textContent = icon;
}

export function clearCustomTheme(): void {
  const style = document.body.style;
  for (const cssVar of Object.values(CSS_VAR_MAP)) {
    style.removeProperty(cssVar);
  }
  for (const cssVar of DERIVED_VARS) {
    style.removeProperty(cssVar);
  }
  style.removeProperty('--shadow');
  document.documentElement.style.removeProperty('color-scheme');
  document.body.classList.remove('theme-glow');
}

export function getActiveTheme(): ThemeData | null {
  const id = getActiveThemeId();
  if (!id) return null;

  // Check presets first
  const preset = getPresetById(id);
  if (preset) return preset;

  // Check custom themes
  const customs = loadCustomThemes();
  return customs.find(t => t.id === id) || null;
}

/** Simple hex lighten/darken helpers for fallback button hover. */
function parseHex(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  return [
    parseInt(h.substring(0, 2), 16),
    parseInt(h.substring(2, 4), 16),
    parseInt(h.substring(4, 6), 16),
  ];
}

function toHex(r: number, g: number, b: number): string {
  const clamp = (v: number) => Math.max(0, Math.min(255, Math.round(v)));
  return '#' + [r, g, b].map(v => clamp(v).toString(16).padStart(2, '0')).join('');
}

function lighten(hex: string, amount: number): string {
  const [r, g, b] = parseHex(hex);
  return toHex(r + 255 * amount, g + 255 * amount, b + 255 * amount);
}

function darken(hex: string, amount: number): string {
  const [r, g, b] = parseHex(hex);
  return toHex(r - 255 * amount, g - 255 * amount, b - 255 * amount);
}

function hexToRgba(hex: string, alpha: number): string {
  const [r, g, b] = parseHex(hex);
  return `rgba(${r},${g},${b},${alpha})`;
}

/**
 * nav/theme — Dark/light theme toggle with system preference detection.
 *
 * Applies the saved (or system-detected) theme immediately on import,
 * binds both the nav toggle and the legacy header toggle, and listens
 * for OS-level theme changes when no explicit preference is stored.
 *
 * Also restores custom themes (presets/user-defined) from localStorage
 * and loads the custom accent color.
 */

import {
  applyTheme as applyCustomTheme,
  clearCustomTheme,
  getActiveTheme,
} from '../theme-system/apply';
import { setActiveThemeId } from '../theme-system/storage';
import { suppressViewTransitionRejections } from '../shared/view-transition';

/** Return 'dark' or 'light' based on OS preference. */
export function getSystemTheme(): 'dark' | 'light' {
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

/** Recognized base-theme modes (opt-in additive themes). */
export type BaseThemeMode =
  | 'light'
  | 'dark'
  | 'atelier-light'
  | 'atelier-dark';

const ATELIER_CLASSES = ['theme-atelier-light', 'theme-atelier-dark'];

/**
 * Apply a base theme mode and update toggle button icons.
 *
 * Atelier modes (atelier-light / atelier-dark) layer on top of the
 * legacy dark class so existing dark-mode CSS still applies while the
 * theme-atelier-* class adds the Fraunces / Inter / JetBrains Mono
 * tokens from atelier-tokens.css.
 */
export function applyBaseTheme(mode: string): void {
  const dark = mode === 'dark' || mode === 'atelier-dark';
  document.body.classList.toggle('dark', dark);

  // Atelier opt-in classes \u2014 clear both, then set the active one if any.
  for (const c of ATELIER_CLASSES) document.body.classList.remove(c);
  if (mode === 'atelier-light') document.body.classList.add('theme-atelier-light');
  if (mode === 'atelier-dark') document.body.classList.add('theme-atelier-dark');

  const icon = dark ? '\u2600\uFE0F' : '\uD83C\uDF19';
  const navBtn = document.getElementById('themeToggleNav');
  if (navBtn) navBtn.textContent = icon;

  const oldBtn = document.getElementById('themeToggle');
  if (oldBtn) oldBtn.textContent = icon;
}

/**
 * Bind a click handler to a theme toggle button (idempotent).
 * Uses `dataset.bound` to prevent duplicate binding.
 * Switching dark/light clears any active custom theme.
 */
function bindToggleButton(btn: HTMLElement | null): void {
  if (!btn || btn.dataset.bound) return;
  btn.dataset.bound = '1';
  btn.addEventListener('click', (e: MouseEvent) => {
    // Clear custom theme when manually toggling dark/light
    clearCustomTheme();
    setActiveThemeId(null);
    const onAtelier = document.body.classList.contains('theme-atelier-light')
      || document.body.classList.contains('theme-atelier-dark');
    const isDark = document.body.classList.contains('dark');
    let next: string;
    if (onAtelier) {
      next = isDark ? 'atelier-light' : 'atelier-dark';
    } else {
      next = isDark ? 'light' : 'dark';
    }
    localStorage.setItem('themeMode', next);

    if (!document.startViewTransition) {
      applyBaseTheme(next);
      return;
    }

    // Circular reveal from click point
    const x = e.clientX;
    const y = e.clientY;
    const endRadius = Math.hypot(
      Math.max(x, window.innerWidth - x),
      Math.max(y, window.innerHeight - y),
    );

    // Try object form first (Chrome 111+), fall back to callback form
    // (Safari 18+), then direct apply if both fail.
    let transition: ViewTransition;
    try {
      transition = suppressViewTransitionRejections(document.startViewTransition({
        update: () => { applyBaseTheme(next); },
        types: ['theme-change'],
      } as Parameters<typeof document.startViewTransition>[0]));
    } catch {
      try {
        transition = suppressViewTransitionRejections(
          document.startViewTransition(() => { applyBaseTheme(next); }),
        );
      } catch {
        applyBaseTheme(next);
        return;
      }
    }

    // Safety: abort the transition if it stalls (e.g. headless browsers
    // where Web Animation on pseudo-elements may not fire properly).
    const safetyTimer = setTimeout(() => {
      try { transition.skipTransition(); } catch { /* already finished */ }
    }, 600);
    transition.finished.finally(() => clearTimeout(safetyTimer)).catch(() => {});

    transition.ready.then(() => {
      const anim = document.documentElement.animate(
        {
          clipPath: [
            `circle(0px at ${x}px ${y}px)`,
            `circle(${endRadius}px at ${x}px ${y}px)`,
          ],
        },
        {
          duration: 400,
          easing: 'ease-out',
          pseudoElement: '::view-transition-new(root)',
        },
      );
      anim.finished.catch(() => {});
    }).catch(() => {
      // View transition cancelled or unsupported — no-op
    });
  });
}

/** Listen for OS-level theme changes when no explicit preference is stored. */
function listenSystemThemeChange(): void {
  if (localStorage.getItem('themeMode') || !window.matchMedia) return;
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const handler = (): void => {
    // No themeMode saved -> never-customized user, keep them on atelier.
    const sys = getSystemTheme();
    applyBaseTheme(sys === 'dark' ? 'atelier-dark' : 'atelier-light');
  };
  try {
    mq.addEventListener('change', handler);
  } catch {
    try {
      mq.addListener(handler);
    } catch {
      // ignore — very old browsers
    }
  }
}

/** Load custom accent color from localStorage (only when no custom theme is active). */
function loadAccentColor(): void {
  const saved = localStorage.getItem('accentColor');
  if (saved) document.documentElement.style.setProperty('--accent', saved);
}

/** Validate a background image URL (allow http(s) and data:image/ only). */
function isValidBgUrl(url: string): boolean {
  const trimmed = url.trim();
  if (!trimmed) return false;
  if (/^https?:\/\//i.test(trimmed)) return true;
  if (/^data:image\//i.test(trimmed)) return true;
  return false;
}

/** Load custom background image from localStorage and apply to body::before. */
function loadBgImage(): void {
  const url = localStorage.getItem('bgImage') || '';
  const opacity = localStorage.getItem('bgImageOpacity') || '0.1';
  if (url && isValidBgUrl(url)) {
    // Escape characters that could break CSS url()
    const safe = url.replace(/["'()\\]/g, (c) => '\\' + c);
    document.documentElement.style.setProperty('--bg-image', `url("${safe}")`);
    document.documentElement.style.setProperty('--bg-image-opacity', opacity);
    document.body.classList.add('has-bg-image');
  } else {
    document.body.classList.remove('has-bg-image');
    document.documentElement.style.removeProperty('--bg-image');
    document.documentElement.style.removeProperty('--bg-image-opacity');
  }
}

/** Load dock zoom preference and toggle body class. */
function loadDockZoom(): void {
  const off = localStorage.getItem('dockZoomOff') === '1';
  document.body.classList.toggle('no-dock-zoom', off);
}

/** Apply SafeSearch state to the body and toggle button.
 *
 * Modes:
 *   - off: no class
 *   - on: body.safe-search (thumbs blurred, hover unblurs slightly)
 *   - revealed: body.safe-search.safe-search-revealed (temporarily fully visible)
 */
function applySafeSearch(state: 'off' | 'on' | 'revealed'): void {
  const body = document.body;
  body.classList.toggle('safe-search', state !== 'off');
  body.classList.toggle('safe-search-revealed', state === 'revealed');
  const btn = document.getElementById('safeSearchToggleNav');
  if (btn) {
    btn.setAttribute('aria-pressed', state === 'off' ? 'false' : 'true');
    btn.textContent = state === 'revealed' ? '👁️' : '🔞';
  }
}

function getSavedSafeSearch(): 'off' | 'on' | 'revealed' {
  const v = localStorage.getItem('safe_search') || 'off';
  return v === 'on' || v === 'revealed' ? v : 'off';
}

function bindSafeSearchToggle(): void {
  const btn = document.getElementById('safeSearchToggleNav');
  if (!btn || btn.dataset.bound === '1') return;
  btn.dataset.bound = '1';
  btn.addEventListener('click', () => {
    const cur = getSavedSafeSearch();
    // Three-state cycle: off -> on -> revealed -> off
    const next: 'off' | 'on' | 'revealed' =
      cur === 'off' ? 'on' : cur === 'on' ? 'revealed' : 'off';
    localStorage.setItem('safe_search', next);
    applySafeSearch(next);
  });
}

/** Initialize theme subsystem: restore custom theme or dark/light, bind toggles. */
export function initTheme(): void {
  // Check for active custom/preset theme first
  const activeTheme = getActiveTheme();
  if (activeTheme) {
    applyCustomTheme(activeTheme);
  } else {
    // Fallback chain:
    //   1. explicit themeMode in localStorage (returning user)
    //   2. atelier-{light|dark} for never-customized users (new default)
    const stored = localStorage.getItem('themeMode');
    let mode: string;
    if (stored) {
      mode = stored;
    } else {
      const sys = getSystemTheme();
      mode = sys === 'dark' ? 'atelier-dark' : 'atelier-light';
    }
    applyBaseTheme(mode);
    loadAccentColor();
  }

  bindToggleButton(document.getElementById('themeToggleNav'));
  bindToggleButton(document.getElementById('themeToggle'));

  // SafeSearch: restore + bind toggle
  applySafeSearch(getSavedSafeSearch());
  bindSafeSearchToggle();

  listenSystemThemeChange();

  // Background image & dock zoom (localStorage-based, all pages)
  loadBgImage();
  loadDockZoom();
}

/**
 * Settings page — accent color picker, retro mode, container nav, modal keep scroll.
 * Converted from static/js/settings/settings-appearance.js
 */

import { initThemeManager } from '../theme-system/manager-ui';
import { initThemeEditor } from '../theme-system/editor-ui';
import { initThemeQr } from '../theme-system/qr-share';
import { isSoundEnabled, getSoundVolume, setSoundEnabled, setSoundVolume, playSound } from '../sound';

const DEFAULT_LIGHT = '#3b82f6';
const DEFAULT_DARK = '#60a5fa';

function getDefault(): string {
  return document.body.classList.contains('dark') ? DEFAULT_DARK : DEFAULT_LIGHT;
}

function updateNavOrderVisibility(): void {
  const row = document.getElementById('container-nav-order-row');
  if (row) {
    const on = localStorage.getItem('containerNavContinuous') === '1';
    row.style.display = on ? '' : 'none';
  }
}

export function initAppearanceTab(): void {
  const picker = document.getElementById('cfg-accent-color') as HTMLInputElement | null;
  const retro = document.getElementById('cfg-retro-mode') as HTMLInputElement | null;
  if (!picker) return;

  // Load saved accent color
  const saved = localStorage.getItem('accentColor');
  picker.value = saved || getDefault();

  // Dock zoom toggle
  const dockZoom = document.getElementById('cfg-dock-zoom') as HTMLInputElement | null;
  if (dockZoom) {
    dockZoom.checked = localStorage.getItem('dockZoomOff') !== '1';
  }

  // Background image
  const bgInput = document.getElementById('cfg-bg-image') as HTMLInputElement | null;
  if (bgInput) {
    bgInput.value = localStorage.getItem('bgImage') || '';
  }

  // Background opacity slider
  const bgOpacity = document.getElementById('cfg-bg-opacity') as HTMLInputElement | null;
  const bgOpacityLabel = document.getElementById('bg-opacity-value');
  if (bgOpacity) {
    const pct = Math.round(parseFloat(localStorage.getItem('bgImageOpacity') || '0.1') * 100);
    bgOpacity.value = String(pct);
    if (bgOpacityLabel) bgOpacityLabel.textContent = pct + '%';
  }

  // Live preview on change
  picker.addEventListener('input', () => {
    document.documentElement.style.setProperty('--accent', picker.value);
    localStorage.setItem('accentColor', picker.value);
  });

  // Retro mode toggle
  if (retro) {
    retro.checked = localStorage.getItem('theme-retro') === '1';
  }

  // Atelier theme select — reflect current themeMode
  const atelier = document.getElementById('cfg-atelier-theme') as HTMLSelectElement | null;
  if (atelier) {
    const mode = localStorage.getItem('themeMode') || '';
    if (mode === 'atelier-light' || mode === 'atelier-dark') {
      atelier.value = mode;
    } else {
      atelier.value = 'off';
    }
  }

  // Container continuous navigation toggle + order select
  const contNav = document.getElementById('cfg-container-nav-continuous') as HTMLInputElement | null;
  if (contNav) {
    contNav.checked = localStorage.getItem('containerNavContinuous') === '1';
  }

  // Modal default analysis mode toggle (immersive is default, analysis = opt-in)
  const defaultAnalysis = document.getElementById('cfg-modal-default-analysis') as HTMLInputElement | null;
  if (defaultAnalysis) {
    defaultAnalysis.checked = localStorage.getItem('immersiveMode') === '0';
  }

  // Modal keep scroll toggle
  const keepScroll = document.getElementById('cfg-modal-keep-scroll') as HTMLInputElement | null;
  if (keepScroll) {
    keepScroll.checked = localStorage.getItem('modalKeepScroll') === '1';
  }

  // Modal keyboard guide toggle
  const kbGuide = document.getElementById('cfg-modal-kb-guide') as HTMLInputElement | null;
  if (kbGuide) {
    kbGuide.checked = localStorage.getItem('modalKbGuideHidden') !== '1';
  }

  const navOrder = document.getElementById('cfg-container-nav-order') as HTMLSelectElement | null;
  if (navOrder) {
    navOrder.value = localStorage.getItem('containerNavOrder') || 'name';
  }

  updateNavOrderVisibility();

  // Sound effects
  const soundToggle = document.getElementById('cfg-sound-enabled') as HTMLInputElement | null;
  if (soundToggle) soundToggle.checked = isSoundEnabled();
  const soundVolSlider = document.getElementById('cfg-sound-volume') as HTMLInputElement | null;
  const soundVolLabel = document.getElementById('sound-volume-value');
  if (soundVolSlider) {
    const pct = Math.round(getSoundVolume() * 100);
    soundVolSlider.value = String(pct);
    if (soundVolLabel) soundVolLabel.textContent = pct + '%';
  }
  const muteBtn = document.getElementById('soundMuteBtn');
  if (muteBtn) muteBtn.textContent = isSoundEnabled() ? '\uD83D\uDD0A' : '\uD83D\uDD07';

  // Initialize theme system: editor + QR + manager
  initThemeEditor();
  initThemeQr();
  initThemeManager();
}

export function resetAccentColor(): void {
  localStorage.removeItem('accentColor');
  document.documentElement.style.removeProperty('--accent');
  const picker = document.getElementById('cfg-accent-color') as HTMLInputElement | null;
  if (picker) picker.value = getDefault();
}

export function toggleRetroMode(on: boolean): void {
  document.body.classList.toggle('theme-retro', on);
  localStorage.setItem('theme-retro', on ? '1' : '0');
}

/**
 * Apply Atelier theme selection. Live-previews immediately by toggling
 * the body class and persisting to themeMode so it survives reload.
 *
 * Receives the <select> element via data-action-this="1"; reads its
 * `.value`: 'off' | 'atelier-light' | 'atelier-dark'.
 */
export function setAtelierTheme(el: HTMLSelectElement): void {
  const value = el.value;

  // Clear both atelier classes first
  document.body.classList.remove('theme-atelier-light', 'theme-atelier-dark');

  if (value === 'atelier-light') {
    document.body.classList.add('theme-atelier-light');
    document.body.classList.remove('dark');
    localStorage.setItem('themeMode', 'atelier-light');
  } else if (value === 'atelier-dark') {
    document.body.classList.add('theme-atelier-dark');
    document.body.classList.add('dark');
    localStorage.setItem('themeMode', 'atelier-dark');
  } else {
    // Off — fall back to a plain dark/light based on current dark state.
    const isDark = document.body.classList.contains('dark');
    localStorage.setItem('themeMode', isDark ? 'dark' : 'light');
  }
}

export function toggleContainerNavContinuous(on: boolean): void {
  localStorage.setItem('containerNavContinuous', on ? '1' : '0');
  updateNavOrderVisibility();
}

export function setContainerNavOrder(val: string): void {
  localStorage.setItem('containerNavOrder', val === 'result' ? 'result' : 'name');
}

export function toggleModalDefaultAnalysis(on: boolean): void {
  // on = analysis mode default → immersiveMode = '0'
  localStorage.setItem('immersiveMode', on ? '0' : '1');
}

export function toggleModalKeepScroll(on: boolean): void {
  localStorage.setItem('modalKeepScroll', on ? '1' : '0');
}

export function toggleModalKbGuide(on: boolean): void {
  localStorage.setItem('modalKbGuideHidden', on ? '0' : '1');
}

export function toggleDockZoom(on: boolean): void {
  localStorage.setItem('dockZoomOff', on ? '0' : '1');
  document.body.classList.toggle('no-dock-zoom', !on);
}

/** Validate background image URL — allow http(s) and data:image/ only. */
function isValidBgUrl(url: string): boolean {
  const t = url.trim();
  if (!t) return false;
  if (/^https?:\/\//i.test(t)) return true;
  if (/^data:image\//i.test(t)) return true;
  return false;
}

/** Apply background image CSS variables to document. */
function applyBgImage(): void {
  const url = localStorage.getItem('bgImage') || '';
  const opacity = localStorage.getItem('bgImageOpacity') || '0.1';
  if (url && isValidBgUrl(url)) {
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

export function setBgImage(url: string): void {
  const trimmed = url.trim();
  if (trimmed && !isValidBgUrl(trimmed)) return;
  if (trimmed) {
    localStorage.setItem('bgImage', trimmed);
  } else {
    localStorage.removeItem('bgImage');
  }
  applyBgImage();
}

export function clearBgImage(): void {
  localStorage.removeItem('bgImage');
  const input = document.getElementById('cfg-bg-image') as HTMLInputElement | null;
  if (input) input.value = '';
  applyBgImage();
}

export function setBgOpacity(pctStr: string): void {
  const pct = parseInt(pctStr, 10);
  const val = (pct / 100).toFixed(2);
  localStorage.setItem('bgImageOpacity', val);
  document.documentElement.style.setProperty('--bg-image-opacity', val);
  const label = document.getElementById('bg-opacity-value');
  if (label) label.textContent = pct + '%';
}

/* ---- Sound Effects ---- */

export function toggleSoundEnabled(on: boolean): void {
  setSoundEnabled(on);
  const muteBtn = document.getElementById('soundMuteBtn');
  if (muteBtn) muteBtn.textContent = on ? '\uD83D\uDD0A' : '\uD83D\uDD07';
  if (on) playSound('click');
}

export function onSoundVolumeChange(pctStr: string): void {
  const pct = parseInt(pctStr, 10);
  const vol = pct / 100;
  setSoundVolume(vol);
  const label = document.getElementById('sound-volume-value');
  if (label) label.textContent = pct + '%';
}

export function toggleSoundMute(): void {
  const toggle = document.getElementById('cfg-sound-enabled') as HTMLInputElement | null;
  const newState = !isSoundEnabled();
  setSoundEnabled(newState);
  if (toggle) toggle.checked = newState;
  const muteBtn = document.getElementById('soundMuteBtn');
  if (muteBtn) muteBtn.textContent = newState ? '\uD83D\uDD0A' : '\uD83D\uDD07';
  if (newState) playSound('click');
}

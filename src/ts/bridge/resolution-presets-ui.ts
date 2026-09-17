/**
 * Bridge Resolution Presets — UI attach module
 *
 * Wires a <select> + swap button to width/height <input> elements.
 * Dispatches 'input' events on programmatic changes so downstream
 * listeners (hires target, previews, history) pick up the change.
 */

import {
  RESOLUTION_PRESETS,
  findPreset,
  GROUPS,
  type Preset,
  type PresetGroup,
} from './resolution-presets-data';
import { getI18nDictionary } from '../i18n/runtime-state';

/* global window */
declare const window: {
  tr?: (key: string, fallback?: string) => string;
} & Window;

// Bridge pages load tr-runtime-lite which reads from ui_runtime.*.json dicts,
// so window.tr() doesn't know our keys. The main flat i18n dictionary
// (populated by applyTranslations from ja.json / en.json / ...) holds them,
// so consult it first, then fall back to window.tr(), then fallback string.
function tr(key: string, fallback: string): string {
  const flat = getI18nDictionary();
  if (flat && Object.prototype.hasOwnProperty.call(flat, key)) {
    const v = flat[key];
    if (v) return v;
  }
  if (typeof window.tr === 'function') {
    const v = window.tr(key, fallback);
    if (v && v !== key) return v;
  }
  return fallback;
}

export interface AttachConfig {
  selectEl: HTMLSelectElement;
  widthEl: HTMLInputElement;
  heightEl: HTMLInputElement;
  swapBtnEl: HTMLButtonElement;
  i18nPrefix: 'sd_bridge' | 'comfyui_bridge';
  /** Optional: hook invoked after the swap button has applied W↔H values. */
  onSwap?: () => void;
  /** Optional: hook invoked after a preset has applied new W/H values. */
  onPresetApplied?: () => void;
}

function groupLabel(group: PresetGroup, prefix: string): string {
  switch (group) {
    case 'sd15':
      return tr(`${prefix}.preset_group_sd15`, 'SD 1.5');
    case 'sdxl_trained':
      return tr(`${prefix}.preset_group_sdxl_trained`, 'SDXL Trained');
    case 'sdxl_cheatsheet':
      return tr(`${prefix}.preset_group_sdxl_cheatsheet`, 'SDXL Cheat Sheet');
    default: {
      const _exhaustive: never = group;
      return _exhaustive;
    }
  }
}

function populateSelect(selectEl: HTMLSelectElement, prefix: string): void {
  const prevValue = selectEl.value || 'custom';
  selectEl.textContent = '';
  const customOpt = document.createElement('option');
  customOpt.value = 'custom';
  customOpt.textContent = tr(`${prefix}.preset_custom`, 'Custom');
  selectEl.appendChild(customOpt);

  for (const group of GROUPS) {
    const og = document.createElement('optgroup');
    og.label = groupLabel(group, prefix);
    for (const p of RESOLUTION_PRESETS.filter((x) => x.group === group)) {
      const opt = document.createElement('option');
      opt.value = p.key;
      opt.textContent = p.label;
      og.appendChild(opt);
    }
    selectEl.appendChild(og);
  }
  // Preserve previous selection across language-change repopulation.
  selectEl.value = findPreset(prevValue) ? prevValue : 'custom';
}

function applyLabels(
  selectEl: HTMLSelectElement,
  swapBtnEl: HTMLButtonElement,
  prefix: string,
): void {
  selectEl.setAttribute(
    'aria-label',
    tr(`${prefix}.resolution_preset`, 'Resolution Preset'),
  );
  const swapLabel = tr(`${prefix}.swap_dimensions`, 'Swap W/H');
  swapBtnEl.setAttribute('aria-label', swapLabel);
  swapBtnEl.setAttribute('title', swapLabel);
}

function attach(config: AttachConfig): void {
  const { selectEl, widthEl, heightEl, swapBtnEl, i18nPrefix } = config;
  const onSwap = config.onSwap;
  const onPresetApplied = config.onPresetApplied;

  const refresh = () => {
    populateSelect(selectEl, i18nPrefix);
    applyLabels(selectEl, swapBtnEl, i18nPrefix);
  };

  refresh();

  // i18n dict is loaded asynchronously by applyTranslations (core-shared.ts).
  // If our attach() ran before the dict was ready, the first refresh() used
  // English fallbacks. Re-run on every i18n:changed event, which also handles
  // runtime language switching from the nav language picker.
  document.addEventListener('i18n:changed', refresh);

  let applyingPreset = false;

  function applyValues(w: number, h: number, isPreset: boolean): void {
    applyingPreset = true;
    widthEl.value = String(w);
    heightEl.value = String(h);
    // For preset application, sync the aspect lock's ratio to the preset's
    // W:H BEFORE dispatching events. Otherwise the lock's input listener
    // would recompute the dependent dimension using the previous ratio,
    // corrupting the preset values mid-dispatch.
    if (isPreset && onPresetApplied) onPresetApplied();
    widthEl.dispatchEvent(new Event('input', { bubbles: true }));
    widthEl.dispatchEvent(new Event('change', { bubbles: true }));
    heightEl.dispatchEvent(new Event('input', { bubbles: true }));
    heightEl.dispatchEvent(new Event('change', { bubbles: true }));
    applyingPreset = false;
  }

  selectEl.addEventListener('change', () => {
    const key = selectEl.value;
    if (key === 'custom') return;
    const p: Preset | null = findPreset(key);
    if (!p) return;
    applyValues(p.w, p.h, true);
  });

  const onManualChange = () => {
    if (!applyingPreset) selectEl.value = 'custom';
  };
  widthEl.addEventListener('input', onManualChange);
  heightEl.addEventListener('input', onManualChange);

  swapBtnEl.addEventListener('click', () => {
    const w = Number(widthEl.value) || 0;
    const h = Number(heightEl.value) || 0;
    // Invert the aspect ratio BEFORE writing values so the lock listener
    // (if any) sees the swapped W and inverted ratio together.
    if (onSwap) onSwap();
    applyValues(h, w, false);
    selectEl.value = 'custom';
  });
}

export const BridgeResolutionPresets = { attach };

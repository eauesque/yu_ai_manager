/**
 * Bridge Aspect Lock — shared W↔H aspect-ratio lock module.
 *
 * Wires a lock toggle button + ratio text input next to width/height inputs.
 *
 * Behavior:
 * - Ratio is displayed as "W:H" (e.g. "4:3"). When the lock is OFF the ratio
 *   reflects the current W:H (auto-updated from input changes). When the lock
 *   is ON, editing W/H or the ratio recomputes the dependent dimension.
 * - On lock toggle ON, the ratio is recaptured from the current W/H so the
 *   user starts from the present state.
 * - Rounding uses the heightEl's `step` attribute (default 8) so SD (step=8)
 *   and NAI (step=64) both produce valid values.
 * - Caller must invoke onSwap() from their swap handler so the ratio inverts
 *   when locked. Likewise call onPresetApplied() after a preset sets W/H.
 */

import { getI18nDictionary } from '../i18n/runtime-state';

declare const window: {
  tr?: (key: string, fallback?: string) => string;
} & Window;

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

export interface AspectLockHandle {
  isLocked: () => boolean;
  /** Caller hook: invoke after a Swap-W/H action so the ratio inverts when locked. */
  onSwap: () => void;
  /** Caller hook: invoke after a preset applies new W/H so the ratio re-syncs. */
  onPresetApplied: () => void;
}

export interface AttachConfig {
  widthEl: HTMLInputElement;
  heightEl: HTMLInputElement;
  ratioEl: HTMLInputElement;
  lockBtnEl: HTMLButtonElement;
  /** Optional: dispatched 'input'/'change' on these listeners after we mutate W/H. */
  i18nPrefix?: string;
}

function gcd(a: number, b: number): number {
  a = Math.abs(Math.round(a));
  b = Math.abs(Math.round(b));
  while (b > 0) {
    const t = b;
    b = a % b;
    a = t;
  }
  return a || 1;
}

function formatRatio(w: number, h: number): string {
  if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) return '1:1';
  const g = gcd(w, h);
  return `${Math.round(w / g)}:${Math.round(h / g)}`;
}

function parseRatio(text: string): { w: number; h: number } | null {
  if (!text) return null;
  const parts = text.split(/[:/×x]/i).map((s) => s.trim());
  if (parts.length !== 2) return null;
  const w = parseFloat(parts[0]);
  const h = parseFloat(parts[1]);
  if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) return null;
  return { w, h };
}

function readStep(el: HTMLInputElement): number {
  const s = parseFloat(el.step || '');
  if (isFinite(s) && s > 0) return s;
  return 8;
}

function clampToBounds(el: HTMLInputElement, value: number): number {
  const min = parseFloat(el.min || '');
  const max = parseFloat(el.max || '');
  if (isFinite(min) && value < min) value = min;
  if (isFinite(max) && value > max) value = max;
  return value;
}

function roundToStep(value: number, step: number): number {
  if (step <= 0) return Math.round(value);
  return Math.max(step, Math.round(value / step) * step);
}

function attach(config: AttachConfig): AspectLockHandle {
  const { widthEl, heightEl, ratioEl, lockBtnEl } = config;

  let locked = false;
  let applying = false; // suppress feedback loops while we mutate W/H ourselves

  function applyLabels(): void {
    const lockedTitle = tr('bridge.aspect_lock_on', 'Aspect ratio locked');
    const unlockedTitle = tr('bridge.aspect_lock_off', 'Lock aspect ratio');
    const placeholder = tr('bridge.aspect_ratio_placeholder', 'W:H');
    lockBtnEl.setAttribute('title', locked ? lockedTitle : unlockedTitle);
    lockBtnEl.setAttribute('aria-label', locked ? lockedTitle : unlockedTitle);
    ratioEl.setAttribute('placeholder', placeholder);
    ratioEl.setAttribute(
      'aria-label',
      tr('bridge.aspect_ratio_label', 'Aspect ratio'),
    );
  }

  function syncRatioFromWH(): void {
    const w = parseFloat(widthEl.value) || 0;
    const h = parseFloat(heightEl.value) || 0;
    ratioEl.value = formatRatio(w, h);
  }

  function setLocked(next: boolean): void {
    locked = next;
    lockBtnEl.classList.toggle('locked', locked);
    lockBtnEl.setAttribute('aria-pressed', String(locked));
    ratioEl.classList.toggle('readonly', !locked);
    // When OFF the ratio mirrors current W:H. When turned ON we capture the
    // present W:H so subsequent edits scale from a known starting point.
    syncRatioFromWH();
    applyLabels();
  }

  function setDimension(
    el: HTMLInputElement,
    raw: number,
    dispatch: boolean,
  ): void {
    const step = readStep(el);
    const v = clampToBounds(el, roundToStep(raw, step));
    el.value = String(v);
    if (dispatch) {
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  function recomputeFromWidth(): void {
    const r = parseRatio(ratioEl.value);
    if (!r) return;
    const w = parseFloat(widthEl.value) || 0;
    if (w <= 0) return;
    const targetH = (w * r.h) / r.w;
    applying = true;
    setDimension(heightEl, targetH, true);
    applying = false;
  }

  function recomputeFromHeight(): void {
    const r = parseRatio(ratioEl.value);
    if (!r) return;
    const h = parseFloat(heightEl.value) || 0;
    if (h <= 0) return;
    const targetW = (h * r.w) / r.h;
    applying = true;
    setDimension(widthEl, targetW, true);
    applying = false;
  }

  // --- Wire DOM listeners --------------------------------------------------

  lockBtnEl.addEventListener('click', () => {
    setLocked(!locked);
  });

  widthEl.addEventListener('input', () => {
    if (applying) return;
    if (locked) {
      recomputeFromWidth();
    } else {
      syncRatioFromWH();
    }
  });

  heightEl.addEventListener('input', () => {
    if (applying) return;
    if (locked) {
      recomputeFromHeight();
    } else {
      syncRatioFromWH();
    }
  });

  ratioEl.addEventListener('input', () => {
    if (!locked) return;
    // Re-flow H from W using the new ratio. We pick W as the anchor because
    // users typically set "I want 1024 wide at 4:3" rather than the inverse.
    recomputeFromWidth();
  });

  // Treat blur as a normalization point: re-format the ratio nicely.
  ratioEl.addEventListener('blur', () => {
    const r = parseRatio(ratioEl.value);
    if (!r) {
      // Restore from current W:H if input becomes invalid.
      syncRatioFromWH();
      return;
    }
    // Reduce typed values like "16:9" → "16:9" (already minimal) or
    // "1280:720" → "16:9".
    ratioEl.value = formatRatio(r.w, r.h);
  });

  document.addEventListener('i18n:changed', applyLabels);

  // Initial state
  setLocked(false);
  syncRatioFromWH();

  return {
    isLocked: () => locked,
    onSwap: () => {
      // After W/H swap, if locked we want the ratio to invert too so we keep
      // the new orientation. If unlocked we just refresh the displayed ratio.
      const r = parseRatio(ratioEl.value);
      if (locked && r) {
        ratioEl.value = formatRatio(r.h, r.w);
      } else {
        syncRatioFromWH();
      }
    },
    onPresetApplied: () => {
      // Preset takes precedence: re-sync ratio from the new W/H regardless of
      // lock state, so locked editing continues from the preset's ratio.
      syncRatioFromWH();
    },
  };
}

export const BridgeAspectLock = { attach };

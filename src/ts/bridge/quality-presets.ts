/**
 * Bridge Quality Presets — One-click insertion of quality enhancement tags
 *
 * Built-in presets + user custom presets (localStorage).
 * Uses the same attach() pattern as BridgePromptLibrary for 3-bridge integration.
 *
 * Split into:
 *   quality-presets-data.ts  — types, built-in presets, localStorage helpers
 *   quality-presets-ui.ts    — UI components (toast, style, menu, modal)
 *   quality-presets.ts       — attach() entry point + export (this file)
 */

import type { AttachConfig } from './quality-presets-data';
import { injectStyle, toggleMenu } from './quality-presets-ui';

/* ------------------------------------------------------------------ */
/*  attach()                                                           */
/* ------------------------------------------------------------------ */

function attach(config: AttachConfig): void {
  injectStyle();

  const toolbar = document.querySelector(
    config.toolbarSelector || '.bridge-editor-toolbar',
  ) as HTMLElement | null;
  if (!toolbar) return;

  const hint = toolbar.querySelector('.bridge-toolbar-hint');
  const prefix = config.prefix || '';

  const btn = document.createElement('button');
  btn.className = prefix + '-btn small';
  btn.textContent = 'Quality Preset';
  btn.title = window.tr('preset.quality_presets', 'QP — Quality Presets（品質プリセット）');
  btn.setAttribute('aria-label', btn.title);
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleMenu(btn, config);
  });

  if (hint) {
    toolbar.insertBefore(btn, hint);
  } else {
    toolbar.appendChild(btn);
  }
}

/* ------------------------------------------------------------------ */
/*  Export                                                             */
/* ------------------------------------------------------------------ */

export type { AttachConfig, QualityPreset } from './quality-presets-data';
export const BridgeQualityPresets = { attach };

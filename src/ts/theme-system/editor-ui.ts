/**
 * Theme Editor -- fullscreen overlay modal with color pickers and HSL sliders.
 * Opens from the theme manager; provides live preview by directly modifying CSS variables.
 *
 * HTML builders are in editor-html.ts.
 */

import type { ThemeData, ThemeColors } from './types';
import { applyTheme, clearCustomTheme, getActiveTheme } from './apply';
import { addCustomTheme, setActiveThemeId } from './storage';
import { refreshThemeManager, setEditorCallback } from './manager-ui';
import { hexToHsl, hslToHex } from './color-utils';
import {
  COLOR_FIELDS,
  getCurrentColorsFromCSS,
  buildEditorHTML,
  buildPreviewHTML,
} from './editor-html';

let overlay: HTMLElement | null = null;
let savedThemeBefore: ThemeData | null = null;
let originalBodyClasses = '';

/** Initialize: register as editor callback for the manager UI. */
export function initThemeEditor(): void {
  setEditorCallback(openEditor);
}

function openEditor(editTheme?: ThemeData): void {
  if (overlay) return; // already open

  // Save current state for cancel
  savedThemeBefore = getActiveTheme();
  originalBodyClasses = document.body.className;

  const theme: ThemeData = editTheme ? structuredClone(editTheme) : {
    id: 'custom-' + Date.now().toString(36),
    name: '',
    base: document.body.classList.contains('dark') ? 'dark' : 'light',
    colors: getCurrentColorsFromCSS(),
    effects: {},
  };

  overlay = document.createElement('div');
  overlay.className = 'theme-editor-overlay';
  overlay.innerHTML = buildEditorHTML(theme);
  document.body.appendChild(overlay);

  // Bind events
  bindEditorEvents(theme);

  // Apply the theme live immediately
  applyTheme(theme);
}

function bindEditorEvents(theme: ThemeData): void {
  if (!overlay) return;
  const panel = overlay.querySelector('.theme-editor-panel') as HTMLElement;

  // Store base colors for HSL adjustments
  let baseColors = { ...theme.colors } as Record<string, string | undefined>;

  // Color pickers
  panel.querySelectorAll('input[data-picker]').forEach(input => {
    const inp = input as HTMLInputElement;
    const key = inp.dataset.picker as keyof ThemeColors;
    inp.addEventListener('input', () => {
      (theme.colors as unknown as Record<string, string | undefined>)[key] = inp.value;
      baseColors[key] = inp.value;
      const hexSpan = inp.parentElement?.querySelector('.color-hex');
      if (hexSpan) hexSpan.textContent = inp.value;
      applyTheme(theme);
      updatePreview(theme.colors);
    });
  });

  // Base mode radio
  panel.querySelectorAll('input[name="theme-base"]').forEach(radio => {
    radio.addEventListener('change', () => {
      theme.base = (radio as HTMLInputElement).value as 'light' | 'dark';
      applyTheme(theme);
    });
  });

  // HSL sliders
  panel.querySelectorAll('input[data-slider]').forEach(slider => {
    const s = slider as HTMLInputElement;
    const id = s.dataset.slider!;
    s.addEventListener('input', () => {
      const val = parseInt(s.value);
      const valDisplay = panel.querySelector(`[data-slider-val="${id}"]`);
      if (valDisplay) valDisplay.textContent = String(val);

      // Get current slider values
      const brightnessSlider = panel.querySelector('[data-slider="brightness"]') as HTMLInputElement;
      const saturationSlider = panel.querySelector('[data-slider="saturation"]') as HTMLInputElement;
      const bOff = brightnessSlider ? parseInt(brightnessSlider.value) : 0;
      const sOff = saturationSlider ? parseInt(saturationSlider.value) : 0;

      // Apply adjustments from base colors
      for (const f of COLOR_FIELDS) {
        const base = baseColors[f.key];
        if (!base || !base.startsWith('#')) continue;
        const hsl = hexToHsl(base);
        hsl.l = Math.max(0, Math.min(100, hsl.l + bOff));
        hsl.s = Math.max(0, Math.min(100, hsl.s + sOff));
        const adjusted = hslToHex(hsl.h, hsl.s, hsl.l);
        (theme.colors as unknown as Record<string, string | undefined>)[f.key] = adjusted;

        // Update picker UI
        const picker = panel.querySelector(`input[data-picker="${f.key}"]`) as HTMLInputElement;
        if (picker) picker.value = adjusted;
        const hexSpan = picker?.parentElement?.querySelector('.color-hex');
        if (hexSpan) hexSpan.textContent = adjusted;
      }

      applyTheme(theme);
      updatePreview(theme.colors);
    });
  });

  // Glow checkbox
  const glowCb = panel.querySelector('#theme-effect-glow') as HTMLInputElement;
  if (glowCb) {
    glowCb.addEventListener('change', () => {
      if (!theme.effects) theme.effects = {};
      theme.effects.glow = glowCb.checked;
      applyTheme(theme);
    });
  }

  // Cancel
  panel.querySelectorAll('[data-action="cancel"]').forEach(btn => {
    btn.addEventListener('click', () => closeEditor(false));
  });

  // Save
  const saveBtn = panel.querySelector('[data-action="save"]');
  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      const nameInput = panel.querySelector('#theme-editor-name') as HTMLInputElement;
      const name = nameInput?.value.trim();
      if (!name) {
        nameInput?.focus();
        nameInput?.style.setProperty('border-color', '#e55');
        return;
      }
      theme.name = name;
      addCustomTheme(theme);
      setActiveThemeId(theme.id);
      closeEditor(true);
    });
  }

  // Click overlay background to cancel
  overlay!.addEventListener('click', (e) => {
    if (e.target === overlay) closeEditor(false);
  });

  // Escape key
  const escHandler = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      closeEditor(false);
      document.removeEventListener('keydown', escHandler);
    }
  };
  document.addEventListener('keydown', escHandler);
}

function updatePreview(colors: ThemeColors): void {
  const mini = document.getElementById('theme-preview-mini');
  if (mini) mini.innerHTML = buildPreviewHTML(colors);
}

function closeEditor(saved: boolean): void {
  if (overlay) {
    overlay.remove();
    overlay = null;
  }

  if (!saved) {
    // Restore previous theme
    if (savedThemeBefore) {
      applyTheme(savedThemeBefore);
    } else {
      clearCustomTheme();
      // Restore body classes
      document.body.className = originalBodyClasses;
    }
  }

  refreshThemeManager();
}

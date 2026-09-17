/**
 * editor-html.ts -- HTML builders for the Theme Editor overlay.
 *
 * Contains buildEditorHTML, buildPreviewHTML, buildSlider, and
 * helper functions used by editor-ui.ts.
 * Extracted from editor-ui.ts to keep each module under 300 lines.
 */

import type { ThemeData, ThemeColors } from './types';

export const COLOR_FIELDS: { key: keyof ThemeColors; label: string }[] = [
  { key: 'bg', label: 'Background' },
  { key: 'card', label: 'Card' },
  { key: 'text', label: 'Text' },
  { key: 'muted', label: 'Muted' },
  { key: 'border', label: 'Border' },
  { key: 'accent', label: 'Accent' },
  { key: 'btnBg', label: 'Btn BG' },
  { key: 'btnText', label: 'Btn Text' },
  { key: 'btnHover', label: 'Btn Hover' },
];

/** Escape HTML attribute value. */
export function escapeAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

/** Convert RGB/hex CSS color to 6-digit hex. */
export function rgbToHex(color: string): string {
  if (color.startsWith('#')) return color.length === 4 ? expandShortHex(color) : color;
  const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (!m) return color;
  return '#' + [m[1], m[2], m[3]].map(v =>
    parseInt(v).toString(16).padStart(2, '0')
  ).join('');
}

function expandShortHex(h: string): string {
  return '#' + h[1] + h[1] + h[2] + h[2] + h[3] + h[3];
}

/** Read current CSS variable values as a ThemeColors object. */
export function getCurrentColorsFromCSS(): ThemeColors {
  const cs = getComputedStyle(document.documentElement);
  const get = (v: string) => rgbToHex(cs.getPropertyValue(v).trim()) || '#888888';
  return {
    bg: get('--bg'),
    card: get('--card'),
    text: get('--text'),
    muted: get('--muted'),
    border: get('--border'),
    accent: get('--accent'),
    btnBg: get('--btn-bg'),
    btnText: get('--btn-text'),
    btnHover: get('--btn-hover'),
  };
}

/** Build the mini preview HTML showing theme colors. */
export function buildPreviewHTML(c: ThemeColors): string {
  return `<div style="padding:10px;background:${c.bg};min-height:120px;">
    <div style="background:${c.card};border:1px solid ${c.border};border-radius:6px;padding:8px;margin-bottom:6px;">
      <div style="font-size:11px;color:${c.text};margin-bottom:3px;">Card Title</div>
      <div style="font-size:10px;color:${c.muted};">Muted text</div>
    </div>
    <div style="display:flex;gap:4px;">
      <span style="background:${c.btnBg || c.card};color:${c.btnText || c.text};border:1px solid ${c.border};border-radius:4px;padding:2px 6px;font-size:9px;">Button</span>
      <span style="background:${c.accent};color:#fff;border-radius:4px;padding:2px 6px;font-size:9px;">Accent</span>
    </div>
  </div>`;
}

/** Build a labeled range slider. */
export function buildSlider(label: string, id: string, val: number, min: number, max: number): string {
  return `<div class="theme-hsl-slider">
    <label>${label}</label>
    <input type="range" data-slider="${id}" min="${min}" max="${max}" value="${val}" step="1">
    <span class="slider-val" data-slider-val="${id}">${val}</span>
  </div>`;
}

/** Build the full Theme Editor panel HTML. */
export function buildEditorHTML(theme: ThemeData): string {
  const c = theme.colors;
  let html = '<div class="theme-editor-panel">';

  // Header
  html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">';
  html += '<h2 style="font-size:16px;margin:0;">Theme Editor</h2>';
  html += '<button type="button" data-action="cancel" style="background:transparent;border:none;color:var(--muted);font-size:20px;cursor:pointer;padding:4px 8px;">&times;</button>';
  html += '</div>';

  // Theme name
  html += '<div style="margin-bottom:12px;display:flex;gap:8px;align-items:center;">';
  html += `<input type="text" id="theme-editor-name" value="${escapeAttr(theme.name)}" placeholder="Theme name" style="flex:1;padding:6px 10px;border-radius:6px;border:1px solid rgba(128,128,128,0.3);background:var(--bg);color:var(--text);font-size:13px;">`;
  html += '<label style="font-size:12px;color:var(--muted);display:flex;align-items:center;gap:4px;">';
  html += `<input type="radio" name="theme-base" value="light" ${theme.base === 'light' ? 'checked' : ''}> Light`;
  html += '</label>';
  html += '<label style="font-size:12px;color:var(--muted);display:flex;align-items:center;gap:4px;">';
  html += `<input type="radio" name="theme-base" value="dark" ${theme.base === 'dark' ? 'checked' : ''}> Dark`;
  html += '</label>';
  html += '</div>';

  // Two-column layout
  html += '<div class="theme-editor-row">';

  // Left: color pickers
  html += '<div class="theme-editor-colors">';
  for (const f of COLOR_FIELDS) {
    const val = (c as unknown as Record<string, string | undefined>)[f.key] || '';
    html += `<div class="theme-color-row" data-color-key="${f.key}">`;
    html += `<label>${f.label}</label>`;
    html += `<input type="color" value="${val || '#888888'}" data-picker="${f.key}">`;
    html += `<span class="color-hex">${val || ''}</span>`;
    html += '</div>';
  }
  html += '</div>';

  // Right: live preview mini
  html += '<div class="theme-editor-preview">';
  html += '<div class="theme-preview-box" id="theme-preview-mini">';
  html += buildPreviewHTML(c);
  html += '</div>';
  html += '</div>';

  html += '</div>'; // end row

  // HSL batch sliders
  html += '<div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border);">';
  html += '<h3 style="font-size:13px;margin-bottom:8px;color:var(--muted);">Batch Adjust</h3>';
  html += buildSlider('Brightness', 'brightness', 0, -30, 30);
  html += buildSlider('Saturation', 'saturation', 0, -40, 40);
  html += '</div>';

  // Effects
  html += '<div style="margin-top:12px;">';
  html += '<label style="font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px;">';
  html += `<input type="checkbox" id="theme-effect-glow" ${theme.effects?.glow ? 'checked' : ''}> Header glow effect`;
  html += '</label>';
  html += '</div>';

  // Buttons
  html += '<div style="margin-top:16px;display:flex;gap:8px;justify-content:flex-end;">';
  html += '<button type="button" data-action="cancel" class="theme-mgr-btn">Cancel</button>';
  html += '<button type="button" data-action="save" class="theme-mgr-btn theme-mgr-btn-primary">Save Theme</button>';
  html += '</div>';

  html += '</div>'; // end panel
  return html;
}

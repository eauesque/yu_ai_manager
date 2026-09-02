/**
 * Theme QR export dialog — renders a QR code + copyable JSON for a theme.
 */

import type { ThemeData } from './types';
import { escapeHtml } from './qr-decode';

const SCHEMA = 'yu://theme/1';
let _qrCorePromise: Promise<typeof import('../runtime-tools-ui/tools/qr-core')> | null = null;

function _loadQrCore() {
  if (!_qrCorePromise) {
    _qrCorePromise = import('../runtime-tools-ui/tools/qr-core');
  }
  return _qrCorePromise;
}

/** Serialize theme data into a JSON payload string. */
export function themeToPayload(theme: ThemeData): string {
  const payload = {
    schema: SCHEMA,
    theme: {
      name: theme.name,
      base: theme.base,
      colors: theme.colors,
      effects: theme.effects,
    },
  };
  return JSON.stringify(payload);
}

/** Parse a JSON payload string back into ThemeData, or null if invalid. */
export function parsePayload(raw: string): ThemeData | null {
  try {
    const parsed = JSON.parse(raw);
    if (parsed?.schema !== SCHEMA || !parsed?.theme) return null;
    const t = parsed.theme;
    if (!t.name || !t.base || !t.colors) return null;
    return {
      id: 'custom-' + Date.now().toString(36),
      name: t.name,
      base: t.base,
      colors: t.colors,
      effects: t.effects || {},
    };
  } catch {
    return null;
  }
}

/** Show a modal dialog displaying the theme as a QR code and raw JSON. */
export function showExportDialog(theme: ThemeData): void {
  const qrText = themeToPayload(theme);

  if (qrText.length > 2953) {
    alert('Theme data is too large for QR code. Try simplifying the theme.');
    return;
  }

  const overlay = document.createElement('div');
  overlay.className = 'theme-editor-overlay';
  overlay.innerHTML = `<div class="theme-editor-panel" style="max-width:400px;text-align:center;">
    <h3 style="font-size:15px;margin-bottom:12px;">Export: ${escapeHtml(theme.name)}</h3>
    <div id="theme-qr-container" style="display:inline-block;margin-bottom:12px;"></div>
    <div style="margin-bottom:12px;">
      <textarea readonly style="width:100%;height:60px;font-size:10px;font-family:monospace;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px;resize:none;">${escapeHtml(qrText)}</textarea>
    </div>
    <button type="button" class="theme-mgr-btn" data-action="close">Close</button>
  </div>`;

  document.body.appendChild(overlay);

  const container = overlay.querySelector('#theme-qr-container') as HTMLElement;
  void _loadQrCore().then((mod) => {
    mod.renderQr(container, qrText);
  }).catch(() => {});

  overlay.querySelector('[data-action="close"]')?.addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  document.addEventListener('keydown', function esc(e) {
    if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', esc); }
  });
}

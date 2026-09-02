/**
 * Keyboard help overlay — shows/hides the keyboard shortcuts cheatsheet.
 * Converted from static/js/keyboard/help.js
 */

import { safeViewTransition } from '../shared/view-transition';
import { getAppApi, getRuntimeToolsApi } from '../shared/browser-apis';

let keyboardHelpVisible = false;

/**
 * Toggle keyboard help overlay. If already visible, hide it; otherwise build
 * the overlay DOM and append it to the body.
 */
export function showKeyboardHelp(): void {
  if (keyboardHelpVisible) {
    hideKeyboardHelp();
    return;
  }
  const { escapeHtml } = getAppApi();
  const th = (k: string, vars: unknown = null): string =>
    escapeHtml(window.tr(k, vars)) as string;
  const runtimeToolsApi = getRuntimeToolsApi();

  const overlay = document.createElement('div');
  overlay.id = 'keyboardHelpOverlay';
  overlay.className = 'keyboard-help-overlay';
  overlay.innerHTML = `
      <div class="keyboard-help-content">
        <div class="keyboard-help-header">
          <h2>\u2328\uFE0F ${th('kb_help.title')}</h2>
          <button type="button" class="help-close-btn" data-keyboard-help-close="1">\u2715</button>
        </div>

        <div class="keyboard-help-sections">
          <div style="background:linear-gradient(135deg,rgba(102,126,234,0.15),rgba(118,75,162,0.15));border:1px solid rgba(102,126,234,0.3);border-radius:8px;padding:10px 16px;margin-bottom:12px;display:flex;align-items:center;gap:12px;">
            <span style="font-size:24px;">\uD83D\uDCD6</span>
            <div style="flex:1;">
              <div style="font-weight:600;font-size:13px;">${th('kb_help.regex_intro.title')}</div>
              <div style="font-size:12px;color:#888;margin-top:2px;">${th('kb_help.regex_intro.desc')}</div>
            </div>
            <a href="#" data-keyboard-help-open-regex="1" style="padding:6px 14px;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border-radius:6px;text-decoration:none;font-size:12px;font-weight:600;white-space:nowrap;">${th('kb_help.regex_intro.open')}</a>
          </div>

          <div class="help-section">
            <h3>\uD83D\uDD30 ${th('kb_help.basic.title')}</h3>
            <div class="help-item"><kbd>/</kbd><span>${th('kb_help.basic.focus_search')}</span></div>
            <div class="help-item"><kbd>Esc</kbd><span>${th('kb_help.basic.close_or_blur')}</span></div>
            <div class="help-item"><kbd>?</kbd><span>${th('kb_help.basic.toggle_help')}</span></div>
            <div class="help-item"><kbd>Ctrl</kbd>+<kbd>Enter</kbd><span>${th('kb_help.basic.run_search')}</span></div>
            <div class="help-item"><kbd>L</kbd> / <kbd>Ctrl</kbd>+<kbd>L</kbd><span>${th('kb_help.basic.screen_lock')}</span></div>
            <div class="help-item"><kbd>\\</kbd><span>${th('kb_help.basic.toggle_sidebar', 'Toggle sidebar')}</span></div>
          </div>

          <div class="help-section">
            <h3>\uD83D\uDCDD ${th('kb_help.edit.title')}</h3>
            <div class="help-item"><kbd>Ctrl</kbd>+<kbd>K</kbd><span>${th('kb_help.edit.kill_to_end')}</span></div>
            <div class="help-item"><kbd>Ctrl</kbd>+<kbd>U</kbd><span>${th('kb_help.edit.kill_line')}</span></div>
            <div class="help-item"><kbd>Ctrl</kbd>+<kbd>W</kbd><span>${th('kb_help.edit.delete_prev_word')}</span></div>
          </div>

          <div class="help-section">
            <h3>\uD83C\uDFAF ${th('kb_help.move.title')}</h3>
            <div class="help-item"><kbd>Alt</kbd>+<kbd>W</kbd><span>${th('kb_help.move.next_word')}</span></div>
            <div class="help-item"><kbd>Alt</kbd>+<kbd>B</kbd><span>${th('kb_help.move.prev_word')}</span></div>
            <div class="help-item"><kbd>Alt</kbd>+<kbd>0</kbd><span>${th('kb_help.move.line_start')}</span></div>
            <div class="help-item"><kbd>Alt</kbd>+<kbd>$</kbd><span>${th('kb_help.move.line_end')}</span></div>
            <div class="help-item"><kbd>Alt</kbd>+<kbd>X</kbd><span>${th('kb_help.move.delete_char')}</span></div>
          </div>

          <div class="help-section">
            <h3>\uD83D\uDDBC\uFE0F ${th('kb_help.modal.title', 'Image Viewer')}</h3>
            <div class="help-item"><kbd>\u2190</kbd> <kbd>\u2192</kbd><span>${th('kb_help.modal.prev_next', 'Previous / Next image')}</span></div>
            <div class="help-item"><kbd>Esc</kbd><span>${th('kb_help.modal.close', 'Close viewer')}</span></div>
            <div class="help-item"><kbd>F</kbd><span>${th('kb_help.modal.filmstrip', 'Toggle filmstrip')}</span></div>
            <div class="help-item"><kbd>P</kbd><span>${th('kb_help.modal.autoplay', 'Autoplay')}</span></div>
            <div class="help-item"><kbd>B</kbd><span>${th('kb_help.modal.spread', 'Spread / book view')}</span></div>
            <div class="help-item"><kbd>K</kbd> / <kbd>Space</kbd><span>${th('kb_help.modal.play_pause', 'Play / Pause media')}</span></div>
            <div class="help-item"><kbd>J</kbd> <kbd>L</kbd><span>${th('kb_help.modal.seek', 'Seek -5s / +5s')}</span></div>
            <div class="help-item"><kbd>M</kbd><span>${th('kb_help.modal.mute', 'Mute')}</span></div>
          </div>

          <div class="help-section">
            <h3>\uD83D\uDDBC\uFE0F ${th('kb_help.results.title', 'Result Grid')}</h3>
            <div class="help-item"><kbd>\u2190</kbd><kbd>\u2192</kbd><kbd>\u2191</kbd><kbd>\u2193</kbd><span>${th('kb_help.results.navigate', 'Move focus')}</span></div>
            <div class="help-item"><kbd>Enter</kbd><span>${th('kb_help.results.open', 'Open detail')}</span></div>
            <div class="help-item"><kbd>C</kbd><span>${th('kb_help.results.copy_prompt', 'Copy prompt')}</span></div>
            <div class="help-item"><kbd>M</kbd> / right-click<span>${th('kb_help.results.context_menu', 'Context menu (right-click / M key)')}</span></div>
            <div class="help-item help-hint" style="font-size:11px;color:#888;padding-left:0;">${th('kb_help.results.context_menu_hint', 'Right-click a card for: copy params, App QR, bridge, analysis, ...')}</div>
          </div>

          <div class="help-section">
            <h3>\u26A1 ${th('kb_help.existing.title')}</h3>
            <div class="help-item"><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>A</kbd><span>${th('kb_help.existing.open_condition_menu')}</span></div>
            <div class="help-item"><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>E</kbd><span>${th('kb_help.existing.toggle_regex')}</span></div>
            <div class="help-item"><kbd>Ctrl</kbd>+<kbd>/</kbd><span>${th('kb_help.existing.regex_cheatsheet')}</span></div>
          </div>
        </div>

        <div class="keyboard-help-footer">
          <p style="margin-bottom:6px;"><a href="#" data-keyboard-help-reopen-regex="1" style="color:#667eea;text-decoration:underline;">\uD83D\uDCD6 ${th('kb_help.footer.regex_intro_link')}</a></p>
          <p>\uD83D\uDCA1 ${th('kb_help.footer.hint_line')}</p>
          <p><kbd>?</kbd> ${th('kb_help.footer.or')} <kbd>Esc</kbd> ${th('kb_help.footer.close')}</p>
        </div>
      </div>
    `;

  document.body.appendChild(overlay);
  keyboardHelpVisible = true;
  overlay.querySelector<HTMLElement>('[data-keyboard-help-close="1"]')?.addEventListener('click', () => {
    hideKeyboardHelp();
  });
  overlay.querySelector<HTMLElement>('[data-keyboard-help-open-regex="1"]')?.addEventListener('click', (e) => {
    e.preventDefault();
    hideKeyboardHelp();
    runtimeToolsApi.openRegexIntro();
  });
  overlay.querySelector<HTMLElement>('[data-keyboard-help-reopen-regex="1"]')?.addEventListener('click', (e) => {
    e.preventDefault();
    runtimeToolsApi.closeRegexIntro();
    runtimeToolsApi.openRegexIntro();
  });
  overlay.addEventListener('click', (e: MouseEvent) => {
    if (e.target === overlay) hideKeyboardHelp();
  });
}

/**
 * Remove the keyboard help overlay from the DOM.
 */
export function hideKeyboardHelp(): void {
  const overlay = document.getElementById('keyboardHelpOverlay');
  if (!overlay) return;
  safeViewTransition(() => { overlay.remove(); });
  keyboardHelpVisible = false;
}

/**
 * Returns whether the keyboard help overlay is currently visible.
 */
export function isKeyboardHelpVisible(): boolean {
  return keyboardHelpVisible;
}

/** Public API object for the keyboard help module. */
export const keyboardHelpApi = {
  show: showKeyboardHelp,
  hide: hideKeyboardHelp,
  isVisible: isKeyboardHelpVisible,
} as const;

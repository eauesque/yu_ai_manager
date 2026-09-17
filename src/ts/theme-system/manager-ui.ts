/**
 * Theme Manager UI — rendered in the settings appearance tab.
 * Shows preset themes, custom themes, and action buttons.
 */

import type { ThemeData } from './types';
import { PRESETS } from './presets';
import { applyTheme, clearCustomTheme, getActiveTheme } from './apply';
import { loadCustomThemes, deleteCustomTheme, setActiveThemeId, getActiveThemeId } from './storage';

declare const window: Window & {
  tr: (key: string, fallback?: string) => string;
};

let editorOpenCallback: ((theme?: ThemeData) => void) | null = null;
let qrExportCallback: ((theme: ThemeData) => void) | null = null;
let qrImportCallback: (() => void) | null = null;

export function setEditorCallback(cb: (theme?: ThemeData) => void): void {
  editorOpenCallback = cb;
}

export function setQrExportCallback(cb: (theme: ThemeData) => void): void {
  qrExportCallback = cb;
}

export function setQrImportCallback(cb: () => void): void {
  qrImportCallback = cb;
}

export function initThemeManager(): void {
  const container = document.getElementById('themeManagerSection');
  if (!container) return;
  renderManager(container);
}

function renderManager(container: HTMLElement): void {
  const activeId = getActiveThemeId();
  const customs = loadCustomThemes();

  let html = '';

  // Hint text
  html += `<p class="theme-mgr-hint">${escapeHtml(window.tr('settings.theme_hint', 'Click a theme to apply it instantly.'))}</p>`;

  // Preset themes
  html += '<div style="margin-bottom:16px;">';
  html += `<h3 style="font-size:14px;margin-bottom:8px;color:var(--text);">${escapeHtml(window.tr('settings.preset_themes', 'Preset Themes'))}</h3>`;
  html += '<div class="theme-card-grid">';

  // "Default" option
  html += renderThemeCard(null, activeId === null);

  for (const preset of PRESETS) {
    html += renderThemeCard(preset, activeId === preset.id);
  }
  html += '</div></div>';

  // Custom themes
  if (customs.length > 0) {
    html += '<div style="margin-bottom:16px;">';
    html += `<h3 style="font-size:14px;margin-bottom:8px;color:var(--text);">${escapeHtml(window.tr('settings.custom_themes', 'Custom Themes'))}</h3>`;
    html += '<div class="theme-card-grid">';
    for (const theme of customs) {
      html += renderThemeCard(theme, activeId === theme.id, true);
    }
    html += '</div></div>';
  }

  // Action buttons
  html += '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;">';
  html += `<button type="button" class="theme-mgr-btn theme-mgr-btn-primary" data-action="new-theme">${escapeHtml(window.tr('settings.new_theme', 'New Theme'))}</button>`;
  html += `<button type="button" class="theme-mgr-btn" data-action="qr-import">${escapeHtml(window.tr('settings.qr_import', 'QR Import'))}</button>`;
  html += '</div>';

  container.innerHTML = html;

  // Bind events
  container.querySelectorAll('[data-theme-id]').forEach(el => {
    el.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      const card = target.closest('[data-theme-id]') as HTMLElement;
      if (!card) return;
      const id = card.dataset.themeId || '';
      const action = target.dataset.action;

      if (action === 'delete') {
        e.stopPropagation();
        if (confirm(window.tr('settings.theme_delete_confirm', 'Delete this custom theme?'))) {
          deleteCustomTheme(id);
          renderManager(container);
        }
        return;
      }
      if (action === 'edit') {
        e.stopPropagation();
        const theme = findThemeById(id);
        if (theme && editorOpenCallback) editorOpenCallback(theme);
        return;
      }
      if (action === 'qr-export') {
        e.stopPropagation();
        const theme = findThemeById(id);
        if (theme && qrExportCallback) qrExportCallback(theme);
        return;
      }

      // Click on card = apply theme
      applySelectedTheme(id, container);
    });
  });

  // Default card click
  const defaultCard = container.querySelector('[data-theme-default]');
  if (defaultCard) {
    defaultCard.addEventListener('click', () => {
      clearCustomTheme();
      setActiveThemeId(null);
      // Restore saved mode
      const saved = localStorage.getItem('themeMode');
      const systemDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
      const mode = saved || (systemDark ? 'dark' : 'light');
      document.body.classList.toggle('dark', mode === 'dark');
      showAppliedToast(window.tr('settings.theme_default', 'Default'));
      renderManager(container);
    });
  }

  // Keyboard activation (Enter/Space) on theme cards
  container.querySelectorAll('.theme-card[tabindex="0"]').forEach(card => {
    card.addEventListener('keydown', (e) => {
      const ke = e as KeyboardEvent;
      if (ke.key === 'Enter' || ke.key === ' ') {
        ke.preventDefault();
        (card as HTMLElement).click();
      }
    });
  });

  // Action buttons
  const newBtn = container.querySelector('[data-action="new-theme"]');
  if (newBtn) newBtn.addEventListener('click', () => editorOpenCallback?.());

  const importBtn = container.querySelector('[data-action="qr-import"]');
  if (importBtn) importBtn.addEventListener('click', () => qrImportCallback?.());
}

function renderThemeCard(theme: ThemeData | null, isActive: boolean, isCustom = false): string {
  const checkmark = isActive
    ? '<span class="theme-card-check" aria-label="Active">&#10003;</span>'
    : '';

  if (!theme) {
    // Default theme card
    const cls = isActive ? ' theme-card-active' : '';
    return `<div class="theme-card${cls}" data-theme-default role="button" tabindex="0"
        aria-pressed="${isActive}" title="${escapeHtml(window.tr('settings.theme_click_to_apply', 'Click to apply'))}">
      ${checkmark}
      <div class="theme-card-preview theme-card-preview--default">
        <span class="theme-dot theme-dot--lg" style="background:#f5f6f8;"></span>
        <span class="theme-dot theme-dot--lg" style="background:#0f1115;"></span>
        <span class="theme-dot theme-dot--lg" style="background:#2563eb;"></span>
      </div>
      <span class="theme-card-name">${escapeHtml(window.tr('settings.theme_default', 'Default'))}</span>
    </div>`;
  }

  const c = theme.colors;
  const cls = isActive ? ' theme-card-active' : '';
  let actions = '';
  if (isCustom) {
    actions = `<div class="theme-card-actions">
      <button type="button" data-action="edit" title="${escapeHtml(window.tr('settings.theme_edit', 'Edit'))}">${escapeHtml(window.tr('settings.theme_edit', 'Edit'))}</button>
      <button type="button" data-action="qr-export" title="QR Export">QR</button>
      <button type="button" data-action="delete" title="${escapeHtml(window.tr('settings.theme_delete', 'Del'))}" class="theme-card-action-del">${escapeHtml(window.tr('settings.theme_delete', 'Del'))}</button>
    </div>`;
  } else if (theme.id.startsWith('preset-')) {
    actions = `<div class="theme-card-actions">
      <button type="button" data-action="qr-export" title="QR Export">QR</button>
    </div>`;
  }

  return `<div class="theme-card${cls}" data-theme-id="${theme.id}" role="button" tabindex="0"
      aria-pressed="${isActive}" title="${escapeHtml(window.tr('settings.theme_click_to_apply', 'Click to apply'))}">
    ${checkmark}
    <div class="theme-card-preview" style="background:${c.bg};">
      <span class="theme-dot theme-dot--lg" style="background:${c.card};border-color:${c.border};"></span>
      <span class="theme-dot theme-dot--lg" style="background:${c.text};"></span>
      <span class="theme-dot theme-dot--lg" style="background:${c.accent};"></span>
    </div>
    <span class="theme-card-name">${escapeHtml(theme.name)}</span>
    ${actions}
  </div>`;
}

function applySelectedTheme(id: string, container: HTMLElement): void {
  const theme = findThemeById(id);
  if (!theme) return;
  setActiveThemeId(id);
  applyTheme(theme);
  showAppliedToast(theme.name);
  renderManager(container);
}

function showAppliedToast(name: string): void {
  // Remove existing toast
  document.querySelector('.theme-applied-toast')?.remove();

  const toast = document.createElement('div');
  toast.className = 'theme-applied-toast';
  toast.textContent = `${window.tr('settings.theme_applied', 'Theme applied:')} ${name}`;
  document.body.appendChild(toast);

  // Trigger reflow for animation
  toast.offsetHeight; // eslint-disable-line @typescript-eslint/no-unused-expressions
  toast.classList.add('theme-applied-toast--show');

  setTimeout(() => {
    toast.classList.remove('theme-applied-toast--show');
    setTimeout(() => toast.remove(), 300);
  }, 2000);
}

function findThemeById(id: string): ThemeData | undefined {
  const preset = PRESETS.find(p => p.id === id);
  if (preset) return preset;
  return loadCustomThemes().find(t => t.id === id);
}

function escapeHtml(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

/** Re-render the theme manager (call after editor save, QR import, etc.) */
export function refreshThemeManager(): void {
  const container = document.getElementById('themeManagerSection');
  if (container) renderManager(container);
}

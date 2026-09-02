/**
 * startup-mode.ts -- Startup mode radio button handling.
 * Converted from tools-startup-mode.js
 */

export function initStartupMode(): void {
  const mode = localStorage.getItem('tagdb_startup_mode') || 'auto';
  const radio = document.querySelector<HTMLInputElement>(
    `input[name="startupMode"][value="${mode}"]`,
  );
  if (radio) radio.checked = true;
}

export function setStartupMode(v: string | HTMLElement): void {
  const nextValue =
    typeof v === 'string'
      ? v
      : v instanceof HTMLInputElement
        ? v.value
        : '';
  if (!nextValue) return;
  localStorage.setItem('tagdb_startup_mode', nextValue);
}

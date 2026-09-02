/**
 * Main early declarations — toast, startup mode.
 * Converted from static/js/main/main.js
 */

export { showToast } from '../shared/toast';

const STARTUP_MODE_KEY = 'tagdb_startup_mode';

export function getStartupMode(): string {
  return localStorage.getItem(STARTUP_MODE_KEY) || 'auto';
}

export function setStartupMode(mode: string): void {
  localStorage.setItem(STARTUP_MODE_KEY, mode);
}

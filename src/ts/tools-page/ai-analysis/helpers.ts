/**
 * ai-analysis/helpers.ts -- Shared state and utility helpers for AI analysis module.
 */

import { getAppApi } from '../../shared/browser-apis';

/** i18n translation helper. */
export function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

/** Escape a string for safe HTML insertion. */
export function _esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** Check whether a URL points to a private/local address. */
export function _isPrivateUrl(url: string): boolean {
  try {
    const u = new URL(url || 'http://localhost');
    const h = u.hostname;
    if (h === 'localhost' || h === '127.0.0.1' || h === '::1') return true;
    // 10.x.x.x, 172.16-31.x.x, 192.168.x.x
    const parts = h.split('.').map(Number);
    if (parts.length === 4 && parts.every(n => !isNaN(n))) {
      if (parts[0] === 10) return true;
      if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return true;
      if (parts[0] === 192 && parts[1] === 168) return true;
    }
    return false;
  } catch {
    return false;
  }
}

/* ------------------------------------------------------------------ */
/* Shared mutable state                                                */
/* ------------------------------------------------------------------ */

/** Whether the initial config load has completed (skip auto-save on first call). */
let _configLoaded = false;

/** Whether the currently selected engine is local (cost-free). */
let _isLocalEngine = false;

export function getConfigLoaded(): boolean { return _configLoaded; }
export function setConfigLoaded(v: boolean): void { _configLoaded = v; }
export function getIsLocalEngine(): boolean { return _isLocalEngine; }
export function setIsLocalEngine(v: boolean): void { _isLocalEngine = v; }

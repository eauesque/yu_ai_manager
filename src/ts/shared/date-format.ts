/**
 * Timezone-aware date formatting utilities.
 *
 * Reads the configured timezone from ``/api/server-info`` (cached)
 * and formats dates using ``Intl.DateTimeFormat``.
 */

import { loadServerInfo } from './runtime-state/server-info-state';

let _timezone: string | null = null;
let _initialized = false;
let _loading = false;

function _applyTimezone(data: Record<string, unknown> | null): void {
  _timezone = data && typeof data.timezone === 'string' ? data.timezone : null;
}

function _fetchTimezone(): void {
  if (_loading) return;
  _loading = true;
  loadServerInfo()
    .then((data) => {
      _applyTimezone(data);
    })
    .catch(() => {
      _timezone = null;
    });
}

/**
 * Initialize timezone from server info. Called once from nav.
 */
export async function initTimezone(): Promise<void> {
  if (_initialized) return;
  _initialized = true;

  const run = (): void => {
    if (document.hidden) return;
    _fetchTimezone();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      if ('requestIdleCallback' in window) {
        window.requestIdleCallback(run, { timeout: 2500 });
      } else {
        setTimeout(run, 1200);
      }
    }, { once: true });
    return;
  }

  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(run, { timeout: 2500 });
    return;
  }

  setTimeout(run, 1200);
}

/**
 * Format a Unix timestamp as a full date-time string.
 */
export function formatDateTime(unixTs: number): string {
  const date = new Date(unixTs * 1000);
  const opts: Intl.DateTimeFormatOptions = {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  };
  if (_timezone) opts.timeZone = _timezone;
  try {
    return new Intl.DateTimeFormat('sv-SE', opts).format(date).replace(',', '');
  } catch {
    return date.toLocaleString();
  }
}

/**
 * Format a Unix timestamp as a date-only string (YYYY-MM-DD).
 */
export function formatDate(unixTs: number): string {
  const date = new Date(unixTs * 1000);
  const opts: Intl.DateTimeFormatOptions = {
    year: 'numeric', month: '2-digit', day: '2-digit',
  };
  if (_timezone) opts.timeZone = _timezone;
  try {
    return new Intl.DateTimeFormat('sv-SE', opts).format(date);
  } catch {
    return date.toLocaleDateString();
  }
}

/**
 * Format a Unix timestamp as a time-only string (HH:MM:SS).
 */
export function formatTime(unixTs: number): string {
  const date = new Date(unixTs * 1000);
  const opts: Intl.DateTimeFormatOptions = {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  };
  if (_timezone) opts.timeZone = _timezone;
  try {
    return new Intl.DateTimeFormat('sv-SE', opts).format(date);
  } catch {
    return date.toLocaleTimeString();
  }
}

/** Get the currently configured timezone (or null for system default). */
export function getTimezone(): string | null {
  return _timezone;
}

/**
 * Format an elapsed duration (in seconds) as dd:hh:mm:ss.
 * Always shows at least mm:ss; prepends hh: when >= 1 hour, dd: when >= 1 day.
 * Examples: 5 → "0:05", 90 → "1:30", 3665 → "1:01:05", 90061 → "1:01:01:01"
 */
export function formatElapsedHms(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const ss = s % 60;
  const totalMinutes = Math.floor(s / 60);
  const mm = totalMinutes % 60;
  const totalHours = Math.floor(totalMinutes / 60);
  const hh = totalHours % 24;
  const dd = Math.floor(totalHours / 24);

  const ssPad = String(ss).padStart(2, '0');
  const mmPad = String(mm).padStart(2, '0');

  if (dd > 0) return `${dd}:${String(hh).padStart(2, '0')}:${mmPad}:${ssPad}`;
  if (hh > 0) return `${hh}:${mmPad}:${ssPad}`;
  return `${mm}:${ssPad}`;
}

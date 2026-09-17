/**
 * boss-lock / utils — HTML escaping, i18n bridge, media stop, random helpers.
 * Converted from static/js/boss-lock/utils.js
 */

/** HTML-escape a string for safe insertion into markup. */
export function esc(s: unknown): string {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Thin i18n bridge — delegates to window.tr when available, else returns key. */
export function tr(key: string): string {
  try {
    if (typeof window.tr === 'function') return String(window.tr(key));
  } catch {
    // ignore — window.tr may not be ready
  }
  return key;
}

/** Return the current UI language code (e.g. "en", "ja"). */
export function getCurrentLang(): string {
  const stored = (localStorage.getItem('lang') || '').trim().toLowerCase();
  if (stored) return stored;
  const nav = String(navigator.language || 'en').toLowerCase();
  return nav.split('-')[0] || 'en';
}

/** Pause all <video> and <audio> elements and stop any active media streams. */
export function stopAllMediaPlayback(): void {
  const mediaEls = document.querySelectorAll<HTMLMediaElement>('video, audio');
  mediaEls.forEach((el) => {
    try {
      el.pause();
      if (el.srcObject && typeof (el.srcObject as MediaStream).getTracks === 'function') {
        (el.srcObject as MediaStream).getTracks().forEach((track) => track.stop());
      }
    } catch {
      // ignore — element may already be detached
    }
  });
}

/** Return a random element from `arr`, or empty string if empty/invalid. */
export function pickRandom<T>(arr: T[]): T | string {
  if (!Array.isArray(arr) || arr.length === 0) return '';
  return arr[Math.floor(Math.random() * arr.length)];
}

/** Return `count` unique random elements from `arr` (Fisher-Yates shuffle). */
export function pickRandomUnique<T>(arr: T[], count: number): T[] {
  const src = Array.isArray(arr) ? arr.slice() : [];
  for (let i = src.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    const t = src[i];
    src[i] = src[j];
    src[j] = t;
  }
  return src.slice(0, Math.max(0, count));
}

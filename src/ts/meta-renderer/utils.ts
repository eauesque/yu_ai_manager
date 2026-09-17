/**
 * Meta-renderer utilities — escaping, Base64, section HTML builders.
 * Converted from static/js/meta-renderer/utils.js
 */

export function esc(s: string | null | undefined): string {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

/** Escape a value for use inside a double-quoted HTML attribute. */
export function escAttr(s: string | null | undefined): string {
  return esc(s).replace(/"/g, '&quot;');
}

export function toB64(value: unknown): string {
  try {
    return btoa(unescape(encodeURIComponent(String(value))));
  } catch {
    return btoa(String(value));
  }
}

export function sectionOpen(icon: string, title: string, extra?: string): string {
  let h = '<div class="meta-section"><h3>' + icon + ' ' + esc(title);
  if (extra) h += ' <span style="font-size:12px;color:#666;font-weight:normal;">' + extra + '</span>';
  h += '</h3>';
  return h;
}

export function sectionClose(): string {
  return '</div>';
}

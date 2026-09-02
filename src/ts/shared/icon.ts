/**
 * SVG sprite icon helper.
 *
 * Sprite location: /static/img/icons/icons.svg (referenced via <use href>).
 * Symbols are defined as <symbol id="icon-NAME"> within the sprite.
 * Stroke icons inherit stroke="currentColor" from the symbol; filled
 * variants use the "-filled" suffix (e.g. icon-star-filled).
 *
 * Returns an HTML string suitable for embedding in template literals.
 * For state toggles (favorite, play/pause, lock), update the <use> href
 * via setIconSymbol() rather than re-rendering the wrapper.
 */
const SPRITE_URL = '/static/img/icons/icons.svg';

export interface IconOptions {
  /** Extra class names appended to the root <svg>. */
  className?: string;
  /** Override pixel size (sets width/height attributes). Defaults to 1em via CSS. */
  size?: number;
  /** Accessible label. When set, sets role="img" and aria-label. */
  label?: string;
  /**
   * When true (default), the icon is decorative (aria-hidden="true").
   * Set label to make it semantic instead.
   */
  decorative?: boolean;
}

/**
 * Render an icon as an HTML string.
 *
 * Example:
 *   `<button>${icon('star')}</button>`
 *   `<button>${icon('star-filled', { className: 'icon-star-toggle is-active' })}</button>`
 */
export function icon(name: string, opts: IconOptions = {}): string {
  const classes = ['icon', `icon-${name}`];
  if (opts.className) classes.push(opts.className);

  const sizeAttr = opts.size ? ` width="${opts.size}" height="${opts.size}"` : '';

  const isDecorative = opts.label ? false : (opts.decorative !== false);
  const aria = isDecorative
    ? ' aria-hidden="true"'
    : ` role="img" aria-label="${escapeAttr(opts.label || '')}"`;

  return `<svg class="${classes.join(' ')}"${sizeAttr}${aria}><use href="${SPRITE_URL}#icon-${name}"/></svg>`;
}

/**
 * Swap the symbol referenced by an existing icon's <use> element.
 * Used to toggle state (e.g. star ↔ star-filled) without re-rendering
 * the wrapping element, preserving event listeners and CSS transitions.
 */
export function setIconSymbol(svgEl: SVGSVGElement | HTMLElement | null, name: string): void {
  if (!svgEl) return;
  const use = svgEl.querySelector('use');
  if (use) {
    use.setAttribute('href', `${SPRITE_URL}#icon-${name}`);
  }
}

function escapeAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

/**
 * nav/textarea-mirror — Visual helpers for textarea drag-and-drop.
 *
 * Provides mirror div creation, coordinate-to-character mapping,
 * ghost element, and caret indicator used by textarea-drag.ts.
 *
 * Pure leaf module with no imports from textarea-drag.
 */

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

export const GHOST_MAX_CHARS = 40;

export const MIRROR_PROPS: string[] = [
  'fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'letterSpacing',
  'lineHeight', 'textTransform', 'wordSpacing', 'textIndent',
  'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
  'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
  'boxSizing', 'whiteSpace', 'wordWrap', 'overflowWrap', 'tabSize',
  'direction', 'textAlign',
];

/* ------------------------------------------------------------------ */
/*  Mirror div: maps mouse coords to char index inside textarea        */
/* ------------------------------------------------------------------ */

export function createMirror(ta: HTMLTextAreaElement): HTMLDivElement {
  const mirror = document.createElement('div');
  mirror.className = 'ta-drag-mirror';

  const cs = getComputedStyle(ta);
  for (const prop of MIRROR_PROPS) {
    (mirror.style as any)[prop] = cs.getPropertyValue(
      prop.replace(/[A-Z]/g, m => '-' + m.toLowerCase())
    );
  }

  const rect = ta.getBoundingClientRect();
  mirror.style.position = 'fixed';
  mirror.style.left = rect.left + 'px';
  mirror.style.top = rect.top + 'px';
  mirror.style.width = rect.width + 'px';
  mirror.style.height = rect.height + 'px';
  mirror.style.overflow = 'hidden';
  mirror.style.opacity = '0';
  mirror.style.pointerEvents = 'none';
  mirror.style.zIndex = '-1';

  mirror.textContent = ta.value;
  mirror.scrollTop = ta.scrollTop;

  document.body.appendChild(mirror);
  return mirror;
}

export function charIndexFromPoint(mirror: HTMLDivElement, x: number, y: number): number {
  const textNode = mirror.firstChild;
  if (!textNode) return 0;

  // caretPositionFromPoint (Firefox) or caretRangeFromPoint (Chrome/Safari/Edge)
  const doc = document as any;
  if (typeof doc.caretPositionFromPoint === 'function') {
    const pos = doc.caretPositionFromPoint(x, y);
    if (pos && pos.offsetNode === textNode) return pos.offset;
  } else if (typeof doc.caretRangeFromPoint === 'function') {
    const range = doc.caretRangeFromPoint(x, y) as Range | null;
    if (range && range.startContainer === textNode) return range.startOffset;
  }

  // Fallback: binary search by character rects
  return binarySearchIndex(textNode as Text, x, y);
}

export function binarySearchIndex(textNode: Text, x: number, y: number): number {
  const len = textNode.length;
  if (len === 0) return 0;

  const range = document.createRange();
  let lo = 0;
  let hi = len;

  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    range.setStart(textNode, mid);
    range.setEnd(textNode, Math.min(mid + 1, len));
    const rect = range.getBoundingClientRect();
    if (y < rect.top) {
      hi = mid;
    } else if (y > rect.bottom) {
      lo = mid + 1;
    } else if (x < rect.left) {
      hi = mid;
    } else {
      lo = mid + 1;
    }
  }
  return lo;
}

/** Get the bounding rect of a character at a given index in the mirror. */
export function caretRectAt(mirror: HTMLDivElement, idx: number): DOMRect | null {
  const textNode = mirror.firstChild;
  if (!textNode) return null;

  const range = document.createRange();
  const len = (textNode as Text).length;
  const clampedIdx = Math.min(idx, len);

  if (clampedIdx < len) {
    range.setStart(textNode, clampedIdx);
    range.setEnd(textNode, clampedIdx + 1);
  } else if (len > 0) {
    range.setStart(textNode, len - 1);
    range.setEnd(textNode, len);
  } else {
    return null;
  }

  const rects = range.getClientRects();
  return rects.length > 0 ? rects[0] : null;
}

/* ------------------------------------------------------------------ */
/*  Ghost element: follows cursor during drag                          */
/* ------------------------------------------------------------------ */

export function createGhost(text: string): HTMLDivElement {
  const ghost = document.createElement('div');
  ghost.className = 'ta-drag-ghost';
  ghost.textContent = text.length > GHOST_MAX_CHARS
    ? text.slice(0, GHOST_MAX_CHARS) + '\u2026'
    : text;
  document.body.appendChild(ghost);
  return ghost;
}

export function positionGhost(ghost: HTMLDivElement, x: number, y: number): void {
  ghost.style.left = (x + 12) + 'px';
  ghost.style.top = (y + 12) + 'px';
}

/* ------------------------------------------------------------------ */
/*  Caret indicator: shows drop position                               */
/* ------------------------------------------------------------------ */

export function createCaret(): HTMLDivElement {
  const caret = document.createElement('div');
  caret.className = 'ta-drag-caret';
  document.body.appendChild(caret);
  return caret;
}

export function positionCaret(caret: HTMLDivElement, rect: DOMRect): void {
  caret.style.left = rect.left + 'px';
  caret.style.top = rect.top + 'px';
  caret.style.height = rect.height + 'px';
  caret.style.display = 'block';
}

/**
 * shared/caret-position.ts — Get pixel coordinates of the caret in a textarea/input.
 *
 * Uses the "mirror div" technique: creates a hidden div with the same styling
 * as the textarea, copies text up to the caret, and measures a marker span.
 *
 * Returns coordinates relative to the textarea element itself.
 */

const MIRROR_PROPS = [
  'direction', 'boxSizing', 'width', 'overflowX', 'overflowY',
  'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
  'borderStyle',
  'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
  'fontStyle', 'fontVariant', 'fontWeight', 'fontStretch', 'fontSize',
  'fontSizeAdjust', 'lineHeight', 'fontFamily',
  'textAlign', 'textTransform', 'textIndent', 'textDecoration',
  'letterSpacing', 'wordSpacing', 'tabSize', 'MozTabSize',
  'whiteSpace', 'wordWrap', 'wordBreak',
] as const;

export interface CaretCoords {
  top: number;
  left: number;
  height: number;
}

let mirrorDiv: HTMLDivElement | null = null;

/**
 * Get the pixel coordinates of the caret at `position` in the given element,
 * relative to the element's top-left corner (including scroll offset).
 */
export function getCaretCoordinates(
  element: HTMLTextAreaElement | HTMLInputElement,
  position: number,
): CaretCoords {
  if (!mirrorDiv) {
    mirrorDiv = document.createElement('div');
    mirrorDiv.id = '_caretMirror';
    mirrorDiv.setAttribute('aria-hidden', 'true');
    mirrorDiv.setAttribute('data-1p-ignore', '');
    mirrorDiv.setAttribute('data-lpignore', 'true');
    document.body.appendChild(mirrorDiv);
  }
  const s = mirrorDiv.style;
  const computed = getComputedStyle(element);

  s.whiteSpace = 'pre-wrap';
  s.wordWrap = 'break-word';
  s.position = 'fixed';
  s.visibility = 'hidden';
  s.overflow = 'hidden';
  s.top = '-9999px';
  s.left = '-9999px';
  s.height = 'auto';

  for (const prop of MIRROR_PROPS) {
    (s as unknown as Record<string, string>)[prop] = computed.getPropertyValue(
      prop.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase()),
    );
  }

  // For input elements, force single-line
  if (element.nodeName === 'INPUT') {
    s.whiteSpace = 'nowrap';
    s.height = 'auto';
  }

  mirrorDiv.textContent = element.value.substring(0, position);

  // If textarea, replace trailing newline with newline+space so the browser
  // doesn't collapse it
  if (element.nodeName === 'TEXTAREA' && mirrorDiv.textContent.endsWith('\n')) {
    mirrorDiv.textContent += ' ';
  }

  const marker = document.createElement('span');
  marker.textContent = '\u200b'; // zero-width space
  mirrorDiv.appendChild(marker);

  const coords: CaretCoords = {
    top: marker.offsetTop - element.scrollTop,
    left: marker.offsetLeft - element.scrollLeft,
    height: parseInt(computed.lineHeight) || parseInt(computed.fontSize) * 1.2,
  };

  // Cleanup for next call
  mirrorDiv.textContent = '';

  return coords;
}

/**
 * toml-editor-enhance.ts
 *
 * Lightweight TOML textarea enhancer providing:
 *   1. Syntax colouring — comments, headers, keys, strings, values.
 *   2. Syntax-error detection via server-side validation.
 *
 * Uses the same overlay technique as json-editor-enhance.ts.
 * QA constraint (from ACCIDENT_POINTS #8 / QA_HANDOFF):
 *   span elements must NOT have padding/margin/letter-spacing/font-weight
 *   (causes cursor-position drift between overlay and textarea).
 */

// Colour tokens — keyed same as json-editor-enhance for consistency.
const C = {
  comment: 'var(--jeh-d4,#e5c07b)',   // yellow
  header:  'var(--jeh-d1,#61afef)',   // blue
  key:     'var(--jeh-d3,#c678dd)',   // purple
  eq:      'var(--jeh-d0,#e06c75)',   // red
  string:  'var(--jeh-d2,#98c379)',   // green
  value:   'var(--jeh-d0,#e06c75)',   // red/orange (numbers, bools, dates)
} as const;

type Span = { text: string; color: string | null };

/**
 * Tokenise a single TOML line into coloured spans.
 * Line-by-line is sufficient for TOML (no cross-line constructs in keys/headers).
 * Multi-line strings are left as plain text (rare in config files).
 */
function tokeniseLine(line: string): Span[] {
  const parts: Span[] = [];

  // Empty line
  if (line === '') return [{ text: '\n', color: null }];

  // Comment (may be indented)
  const leadingSpaces = line.match(/^(\s*)/)?.[1] ?? '';

  // Check if '#' appears before any non-whitespace that would be a value char
  const stripped = line.trimStart();
  if (stripped.startsWith('#')) {
    parts.push({ text: leadingSpaces, color: null });
    parts.push({ text: stripped + '\n', color: C.comment });
    return parts;
  }

  // Table header: [table] or [[array-table]]
  if (stripped.startsWith('[')) {
    parts.push({ text: leadingSpaces, color: null });
    parts.push({ text: stripped + '\n', color: C.header });
    return parts;
  }

  // Key = value (possibly with inline comment after the value)
  const eqPos = line.indexOf('=');
  if (eqPos >= 0) {
    const rawKey = line.slice(0, eqPos);
    const rawVal = line.slice(eqPos + 1);

    // Key portion (may have leading whitespace + key + trailing whitespace)
    const keyParts = tokeniseKey(rawKey);
    parts.push(...keyParts);

    // '=' sign
    parts.push({ text: '=', color: C.eq });

    // Value portion: split off inline comment first
    const { valuePart, commentPart } = splitValueComment(rawVal);
    parts.push(...tokeniseValue(valuePart));
    if (commentPart !== null) {
      parts.push({ text: commentPart, color: C.comment });
    }
    parts.push({ text: '\n', color: null });
    return parts;
  }

  // Fallback — bare text (dotted keys, etc.)
  parts.push({ text: line + '\n', color: null });
  return parts;
}

function tokeniseKey(raw: string): Span[] {
  // Keep leading/trailing whitespace as plain, key itself coloured.
  const leading = raw.match(/^(\s*)/)?.[1] ?? '';
  const trailing = raw.match(/(\s*)$/)?.[1] ?? '';
  const key = raw.slice(leading.length, raw.length - trailing.length);
  const parts: Span[] = [];
  if (leading)  parts.push({ text: leading,  color: null });
  if (key)      parts.push({ text: key,      color: C.key });
  if (trailing) parts.push({ text: trailing, color: null });
  return parts;
}

/**
 * Split "value # comment" respecting strings.
 * Returns { valuePart, commentPart } where commentPart includes the '#'.
 */
function splitValueComment(raw: string): { valuePart: string; commentPart: string | null } {
  let inStr = false;
  let strChar = '';
  let escape = false;
  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    if (escape) { escape = false; continue; }
    if (inStr) {
      if (ch === '\\') { escape = true; continue; }
      if (ch === strChar) inStr = false;
      continue;
    }
    if (ch === '"' || ch === "'") { inStr = true; strChar = ch; continue; }
    if (ch === '#') {
      return { valuePart: raw.slice(0, i), commentPart: raw.slice(i) };
    }
  }
  return { valuePart: raw, commentPart: null };
}

function tokeniseValue(raw: string): Span[] {
  const leading = raw.match(/^(\s*)/)?.[1] ?? '';
  const trailing = raw.match(/(\s*)$/)?.[1] ?? '';
  const val = raw.slice(leading.length, raw.length - trailing.length);
  const parts: Span[] = [];
  if (leading) parts.push({ text: leading, color: null });
  if (val) {
    const isString = val.startsWith('"') || val.startsWith("'");
    const isArray  = val.startsWith('[') || val.startsWith('{');
    parts.push({ text: val, color: isString ? C.string : isArray ? null : C.value });
  }
  if (trailing) parts.push({ text: trailing, color: null });
  return parts;
}

function tokeniseToml(text: string): Span[] {
  const out: Span[] = [];
  // Split but keep line endings to preserve character count.
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    // Last segment after final \n is usually '' — emit as-is.
    if (i === lines.length - 1) {
      if (lines[i] !== '') out.push({ text: lines[i], color: null });
      // Trailing newline already appended by tokeniseLine for all other lines.
      // For final empty string, nothing to do.
      break;
    }
    out.push(...tokeniseLine(lines[i]));
  }
  // Trailing newline prevents 1-line height mismatch (same trick as json-editor-enhance).
  out.push({ text: '\n', color: null });
  return out;
}

function applyHighlight(el: HTMLDivElement, spans: Span[]): void {
  const frag = document.createDocumentFragment();
  for (const s of spans) {
    if (s.color) {
      const span = document.createElement('span');
      span.style.color = s.color;
      span.textContent = s.text;
      frag.appendChild(span);
    } else {
      frag.appendChild(document.createTextNode(s.text));
    }
  }
  if (typeof el.replaceChildren === 'function') {
    el.replaceChildren(frag);
  } else {
    while (el.firstChild) el.removeChild(el.firstChild);
    el.appendChild(frag);
  }
}

const STABLE_RENDER_PROPS: ReadonlyArray<readonly [string, string]> = [
  ['font-kerning',           'none'],
  ['text-rendering',         'geometricPrecision'],
  ['font-variant-ligatures', 'none'],
  ['letter-spacing',         '0'],
  ['word-spacing',           '0'],
];

let _selectionStyleInjected = false;
function injectSelectionStyle(): void {
  if (_selectionStyleInjected) return;
  _selectionStyleInjected = true;
  const style = document.createElement('style');
  style.textContent = [
    'textarea.teh-enhanced::selection{color:transparent!important;-webkit-text-fill-color:transparent!important;background:rgba(102,126,234,0.3)}',
    'textarea.teh-enhanced::-moz-selection{color:transparent!important;background:rgba(102,126,234,0.3)}',
  ].join('\n');
  document.head.appendChild(style);
}

const _TAG = Symbol('tehCleanup');
type EnhanceCleanup = () => void;

export function getTomlEnhanceHandle(ta: HTMLTextAreaElement): EnhanceCleanup | undefined {
  return (ta as HTMLTextAreaElement & { [_TAG]?: EnhanceCleanup })[_TAG];
}

export function enhanceTomlEditor(ta: HTMLTextAreaElement): EnhanceCleanup {
  const tagged = ta as HTMLTextAreaElement & { [_TAG]?: EnhanceCleanup };
  if (tagged[_TAG]) return tagged[_TAG]!;

  const cs = window.getComputedStyle(ta);
  const caretColor = cs.color;
  injectSelectionStyle();

  const wrapper = document.createElement('div');
  wrapper.className = 'jeh-wrap';  // reuse json-editor-enhance CSS
  wrapper.style.display = 'grid';

  const bg = document.createElement('div');
  bg.className = 'jeh-bg';
  bg.setAttribute('aria-hidden', 'true');
  bg.style.gridArea    = '1 / 1';
  bg.style.alignSelf   = 'stretch';
  bg.style.justifySelf = 'stretch';
  bg.style.overflow    = 'auto';
  bg.style.position    = 'relative';
  bg.style.zIndex      = '1';
  bg.style.setProperty('scrollbar-width',    'none', 'important');
  bg.style.setProperty('-ms-overflow-style', 'none', 'important');
  bg.style.setProperty('color', 'var(--text, currentColor)');

  const bgInner = document.createElement('div');
  bgInner.className = 'jeh-bg-inner';
  bgInner.style.fontFamily    = cs.fontFamily;
  bgInner.style.fontSize      = cs.fontSize;
  bgInner.style.fontWeight    = cs.fontWeight;
  bgInner.style.lineHeight    = cs.lineHeight;
  bgInner.style.paddingTop    = cs.paddingTop;
  bgInner.style.paddingRight  = cs.paddingRight;
  bgInner.style.paddingBottom = cs.paddingBottom;
  bgInner.style.paddingLeft   = cs.paddingLeft;
  bgInner.style.whiteSpace    = cs.whiteSpace   || 'pre-wrap';
  bgInner.style.overflowWrap  = cs.overflowWrap || 'break-word';
  bgInner.style.wordBreak     = cs.wordBreak    || 'normal';
  bg.style.borderTopWidth     = cs.borderTopWidth;
  bg.style.borderRightWidth   = cs.borderRightWidth;
  bg.style.borderBottomWidth  = cs.borderBottomWidth;
  bg.style.borderLeftWidth    = cs.borderLeftWidth;
  bg.style.boxSizing          = cs.boxSizing;
  bg.appendChild(bgInner);

  ta.parentNode!.insertBefore(wrapper, ta);
  wrapper.appendChild(bg);
  wrapper.appendChild(ta);
  ta.style.setProperty('grid-area', '1 / 1', 'important');

  for (const [prop, val] of STABLE_RENDER_PROPS) {
    bgInner.style.setProperty(prop, val);
    ta.style.setProperty(prop, val, 'important');
  }

  ta.classList.add('teh-enhanced');
  ta.style.setProperty('background',              'transparent', 'important');
  ta.style.setProperty('color',                   'transparent', 'important');
  ta.style.setProperty('-webkit-text-fill-color', 'transparent', 'important');
  ta.style.setProperty('caret-color',             caretColor,    'important');
  ta.style.setProperty('scrollbar-width',         'none',        'important');
  ta.style.setProperty('-ms-overflow-style',      'none',        'important');

  function syncHighlight(): void { applyHighlight(bgInner, tokeniseToml(ta.value)); }
  function syncScroll(): void { bg.scrollTop = ta.scrollTop; bg.scrollLeft = ta.scrollLeft; }
  function onInput(): void { syncHighlight(); syncScroll(); }

  ta.addEventListener('input', onInput);
  ta.addEventListener('scroll', syncScroll);
  syncHighlight();

  const cleanup: EnhanceCleanup = () => {
    ta.removeEventListener('input', onInput);
    ta.removeEventListener('scroll', syncScroll);
    ta.classList.remove('teh-enhanced');
    ta.style.removeProperty('background');
    ta.style.removeProperty('color');
    ta.style.removeProperty('-webkit-text-fill-color');
    ta.style.removeProperty('caret-color');
    ta.style.removeProperty('scrollbar-width');
    ta.style.removeProperty('-ms-overflow-style');
    ta.style.removeProperty('grid-area');
    for (const [prop] of STABLE_RENDER_PROPS) ta.style.removeProperty(prop);
    if (wrapper.parentNode) { wrapper.parentNode.insertBefore(ta, wrapper); wrapper.remove(); }
    delete tagged[_TAG];
  };

  tagged[_TAG] = cleanup;
  return cleanup;
}

export function initTomlEditorEnhance(): void {
  const doInit = (): void => {
    document.querySelectorAll<HTMLTextAreaElement>('textarea[data-toml-enhance]').forEach(ta => {
      enhanceTomlEditor(ta);
    });
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', doInit, { once: true });
  } else {
    doInit();
  }
}

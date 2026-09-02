/**
 * json-editor-enhance.ts
 *
 * Lightweight JSON textarea enhancer providing:
 *   1. Bracket-pair colouring — {, [, ], } highlighted by nesting depth.
 *   2. Syntax-error detection — JSON.parse errors shown in a bar below
 *      the textarea with a Japanese message and line/column position.
 *
 * Usage (declarative):  add `data-json-enhance` to any <textarea>.
 *                       nav.js calls initJsonEditorEnhance() on DOMContentLoaded.
 * Usage (programmatic): window.enhanceJsonEditor(textareaElement)
 *
 * Overlay technique and alignment lessons from prompt-syntax ACCIDENT_POINTS #8:
 *   - Hide textarea scrollbar (scrollbar-width:none) so content widths match.
 *   - Set font-kerning:none / text-rendering:geometricPrecision /
 *     font-variant-ligatures:none on BOTH elements for identical rendering.
 *   - Sync scroll via direct scrollTop assignment (bg uses overflow:auto
 *     with hidden scrollbar, not overflow:hidden + transform).
 *   - Span elements must NOT change character widths (no bold, no padding).
 *   - Add ::selection { color:transparent } to suppress double-text on select.
 */

import type { JsonSchema, ValidationIssue } from './json-schema-validator';
import { validateJson } from './json-schema-validator';
import { SCHEMA_REGISTRY } from './json-schemas';

// Five depth colours, cycling. Override via --jeh-d0…--jeh-d4 CSS variables.
const DEPTH_COLORS: readonly string[] = [
  'var(--jeh-d0,#e06c75)',
  'var(--jeh-d1,#61afef)',
  'var(--jeh-d2,#98c379)',
  'var(--jeh-d3,#c678dd)',
  'var(--jeh-d4,#e5c07b)',
];

// ── Tokenizer ───────────────────────────────────────────────────────────────

interface PlainPart  { readonly kind: 'text';   readonly text: string }
interface ColourPart { readonly kind: 'bracket'; readonly text: string; readonly color: string }
type Part = PlainPart | ColourPart;

/**
 * Tokenise `text` into plain-text and bracket parts.
 * String contents are skipped so brackets inside strings are not coloured.
 * Returns parts in source order.
 */
function tokeniseBrackets(text: string): Part[] {
  const parts: Part[] = [];
  let depth = 0;
  let inStr = false;
  let escape = false;
  let buf = '';

  function flush(): void {
    if (buf) { parts.push({ kind: 'text', text: buf }); buf = ''; }
  }

  for (let i = 0; i < text.length; i++) {
    const ch = text[i];

    if (escape) { escape = false; buf += ch; continue; }

    if (inStr) {
      if (ch === '\\') { escape = true; buf += ch; continue; }
      if (ch === '"') inStr = false;
      buf += ch;
      continue;
    }

    if (ch === '"') { inStr = true; buf += ch; continue; }

    if (ch === '{' || ch === '[') {
      flush();
      parts.push({ kind: 'bracket', text: ch, color: DEPTH_COLORS[depth % DEPTH_COLORS.length] });
      depth++;
    } else if (ch === '}' || ch === ']') {
      flush();
      depth = Math.max(0, depth - 1);
      parts.push({ kind: 'bracket', text: ch, color: DEPTH_COLORS[depth % DEPTH_COLORS.length] });
    } else {
      buf += ch;
    }
  }
  flush();
  return parts;
}

/**
 * Apply highlight parts to `el` using DOM methods only — no innerHTML,
 * no XSS risk from user content.  Span style attributes use only
 * constant values from DEPTH_COLORS.
 */
function applyHighlight(el: HTMLDivElement, parts: Part[]): void {
  const frag = document.createDocumentFragment();
  for (const part of parts) {
    if (part.kind === 'bracket') {
      const span = document.createElement('span');
      span.style.color = part.color;
      span.textContent = part.text;
      frag.appendChild(span);
    } else {
      frag.appendChild(document.createTextNode(part.text));
    }
  }
  // Trailing newline prevents 1-line height mismatch at the bottom edge
  frag.appendChild(document.createTextNode('\n'));

  if (typeof el.replaceChildren === 'function') {
    el.replaceChildren(frag);
  } else {
    // Fallback for older Safari <14
    while (el.firstChild) el.removeChild(el.firstChild);
    el.appendChild(frag);
  }
}

// ── Error formatting ─────────────────────────────────────────────────────────

function formatJsonError(rawMessage: string, text: string): string {
  const lower = rawMessage.toLowerCase();

  let friendly: string;
  if (lower.includes('unexpected end') || lower.includes('end of json') || lower.includes('end of data')) {
    friendly = 'JSON が不完全です（カンマ忘れ・括弧の閉じ忘れの可能性）';
  } else if (
    lower.includes("expected ',' or '}'") ||
    lower.includes("expected ',' or ']'") ||
    (lower.includes("','") && lower.includes("'}'"))
  ) {
    friendly = 'カンマ , が不足しています';
  } else if (
    lower.includes('trailing comma') ||
    lower.includes("unexpected ','") ||
    (lower.includes('unexpected token') && lower.includes("','"))
  ) {
    friendly = '余分なカンマがあります（末尾カンマは JSON では不可）';
  } else if (
    lower.includes('expected double-quoted') ||
    lower.includes('expected property name') ||
    lower.includes('invalid character')
  ) {
    friendly = 'キー名はダブルクォートで囲んでください';
  } else {
    friendly = '構文エラー';
  }

  // Position: Chrome ≥88 "at position N" | Firefox "at line N column M"
  let pos = '';
  const atPos = rawMessage.match(/at position (\d+)/i);
  if (atPos) {
    const idx = Math.min(parseInt(atPos[1], 10), text.length);
    const lines = text.slice(0, idx).split('\n');
    pos = ` (行 ${lines.length}、列 ${(lines[lines.length - 1]?.length ?? 0) + 1})`;
  } else {
    const lc = rawMessage.match(/line (\d+) column (\d+)/i);
    if (lc) pos = ` (行 ${lc[1]}、列 ${lc[2]})`;
  }

  return friendly + pos;
}

// ── Global ::selection style injection ───────────────────────────────────────

let _selectionStyleInjected = false;

function injectSelectionStyle(): void {
  if (_selectionStyleInjected) return;
  _selectionStyleInjected = true;
  // Keep textarea text invisible during selection.
  // Without this, the browser default ::selection overrides color:transparent,
  // causing the raw text to appear as a "ghost" layer over the highlight.
  const style = document.createElement('style');
  style.textContent = [
    'textarea.jeh-enhanced::selection {',
    '  color: transparent !important;',
    '  -webkit-text-fill-color: transparent !important;',
    '  background: rgba(102,126,234,0.3);',
    '}',
    'textarea.jeh-enhanced::-moz-selection {',
    '  color: transparent !important;',
    '  background: rgba(102,126,234,0.3);',
    '}',
  ].join('\n');
  document.head.appendChild(style);
}

// ── Font rendering stabilisation ─────────────────────────────────────────────

// Properties that prevent sub-pixel rendering differences between
// the textarea and the highlight div (from prompt-syntax ACCIDENT_POINTS #8).
const STABLE_RENDER_PROPS: ReadonlyArray<readonly [string, string]> = [
  ['font-kerning',           'none'],
  ['text-rendering',         'geometricPrecision'],
  ['font-variant-ligatures', 'none'],
  ['letter-spacing',         '0'],
  ['word-spacing',           '0'],
];

// ── Tag symbol ───────────────────────────────────────────────────────────────

const _TAG = Symbol('jehCleanup');

type EnhanceCleanup = (() => void) & {
  getValidationIssues: () => ValidationIssue[];
};

/**
 * Return the EnhanceCleanup handle attached to a textarea by enhanceJsonEditor().
 * Returns undefined if the textarea has not been enhanced or has been cleaned up.
 * Uses the existing _TAG Symbol as source of truth — no new WeakMap needed.
 */
export function getEnhanceHandle(ta: HTMLTextAreaElement): EnhanceCleanup | undefined {
  return (ta as HTMLTextAreaElement & { [_TAG]?: EnhanceCleanup })[_TAG];
}

// ── Public API ───────────────────────────────────────────────────────────────

export interface JsonEnhanceOptions {
  /** Milliseconds to debounce the JSON.parse check after last keystroke (default 400). */
  debounceMs?: number;
  /** Optional schema for real-time validation warnings. When omitted, behaviour is identical to pre-JSON-Doctor. */
  schema?: JsonSchema | undefined;
}

/**
 * Enhance a single textarea with bracket colouring and syntax error detection.
 * Returns a cleanup function that removes the enhancement and restores the textarea.
 * Calling again on an already-enhanced textarea returns the existing cleanup function.
 */
export function enhanceJsonEditor(
  ta: HTMLTextAreaElement,
  options: JsonEnhanceOptions = {},
): EnhanceCleanup {
  const tagged = ta as HTMLTextAreaElement & { [_TAG]?: EnhanceCleanup };
  if (tagged[_TAG]) return tagged[_TAG]!;

  const debounceMs = options.debounceMs ?? 400;
  const schema = options.schema;

  // Validation state (only used when schema is provided)
  let currentIssues: ValidationIssue[] = [];
  let isDestroyed = false;

  /** i18n helper scoped to this enhancement instance */
  function _trWarn(key: string, fb: string, replacements?: Record<string, string>): string {
    const raw =
      typeof window !== 'undefined' &&
      typeof (window as { tr?: (k: string, fb: string) => string }).tr === 'function'
        ? (window as { tr: (k: string, fb: string) => string }).tr(key, fb)
        : fb;
    if (!replacements) return raw;
    return Object.entries(replacements).reduce((s, [k, v]) => s.replaceAll(`{${k}}`, v), raw);
  }

  // Capture computed style before ANY DOM or style changes.
  const cs = window.getComputedStyle(ta);
  const caretColor = cs.color;

  // Inject ::selection style once per page
  injectSelectionStyle();

  // ── DOM construction ─────────────────────────────────────────────────────

  const wrapper = document.createElement('div');
  wrapper.className = 'jeh-wrap';
  // Critical overlay structure — set inline so it works even when
  // widgets-json-enhance.css is not loaded (e.g. extension pages that use
  // their own CSS bundle instead of main.css).
  wrapper.style.display = 'grid';

  const bg = document.createElement('div');
  bg.className = 'jeh-bg';
  bg.setAttribute('aria-hidden', 'true');
  // Structural styles that must be present regardless of external CSS.
  bg.style.gridArea    = '1 / 1';
  bg.style.alignSelf   = 'stretch';
  bg.style.justifySelf = 'stretch';
  bg.style.overflow    = 'auto';
  bg.style.position    = 'relative';
  // Must sit visually above the textarea so the highlight text is not occluded
  // by the browser's native form-control background (triggered by color-scheme).
  bg.style.zIndex      = '1';
  bg.style.setProperty('scrollbar-width',    'none', 'important');
  bg.style.setProperty('-ms-overflow-style', 'none', 'important');

  const bgInner = document.createElement('div');
  bgInner.className = 'jeh-bg-inner';
  bg.appendChild(bgInner);

  const errDiv = document.createElement('div');
  errDiv.className = 'jeh-err';
  // No role/aria-live here — renderErrBar manages ARIA attributes exclusively

  ta.parentNode!.insertBefore(wrapper, ta);
  wrapper.appendChild(bg);
  wrapper.appendChild(ta);
  wrapper.parentNode!.insertBefore(errDiv, wrapper.nextSibling);

  // Place textarea in the same grid cell as bg so they visually stack.
  ta.style.setProperty('grid-area', '1 / 1', 'important');

  // ── Font/spacing sync ────────────────────────────────────────────────────
  // bgInner must render at identical pixel positions to the textarea.

  bgInner.style.fontFamily    = cs.fontFamily;
  bgInner.style.fontSize      = cs.fontSize;
  // font-weight: use computed value, NOT hardcoded; bold would widen characters
  bgInner.style.fontWeight    = cs.fontWeight;
  bgInner.style.lineHeight    = cs.lineHeight;
  bgInner.style.paddingTop    = cs.paddingTop;
  bgInner.style.paddingRight  = cs.paddingRight;
  bgInner.style.paddingBottom = cs.paddingBottom;
  bgInner.style.paddingLeft   = cs.paddingLeft;
  // Text color for plain text nodes (non-bracket) is NOT set as an inline style.
  // It inherits from .jeh-bg which carries `color: var(--text)` via CSS
  // (widgets-json-enhance.css).  CSS custom property resolution updates
  // automatically on theme switch; an inline static value would not.
  // For extension pages that load their own CSS bundle instead of main.css,
  // we set the variable on bg itself so the same inheritance chain applies.
  bg.style.setProperty('color', 'var(--text, currentColor)');
  // Match wrap behaviour (some JSON textareas use white-space:pre, not pre-wrap)
  bgInner.style.whiteSpace    = cs.whiteSpace   || 'pre-wrap';
  bgInner.style.overflowWrap  = cs.overflowWrap || 'break-word';
  bgInner.style.wordBreak     = cs.wordBreak    || 'normal';

  // bg border: transparent same-width border keeps box-sizing origin aligned
  bg.style.borderTopWidth    = cs.borderTopWidth;
  bg.style.borderRightWidth  = cs.borderRightWidth;
  bg.style.borderBottomWidth = cs.borderBottomWidth;
  bg.style.borderLeftWidth   = cs.borderLeftWidth;
  bg.style.boxSizing         = cs.boxSizing;

  // Stabilise rendering — apply to BOTH bgInner and textarea so they render
  // identically regardless of browser hinting / kerning defaults.
  for (const [prop, val] of STABLE_RENDER_PROPS) {
    bgInner.style.setProperty(prop, val);
    ta.style.setProperty(prop, val, 'important');
  }

  // Make textarea text invisible; keep caret and selection visible.
  ta.classList.add('jeh-enhanced');
  ta.style.setProperty('background',                'transparent', 'important');
  ta.style.setProperty('color',                     'transparent', 'important');
  ta.style.setProperty('-webkit-text-fill-color',   'transparent', 'important');
  ta.style.setProperty('caret-color',               caretColor,    'important');
  // Hide scrollbar on the textarea — must match bg scrollbar-width:none so
  // both elements have the same content width (avoids line-wrap drift).
  ta.style.setProperty('scrollbar-width',           'none',        'important');
  ta.style.setProperty('-ms-overflow-style',        'none',        'important');

  // ── Update functions ─────────────────────────────────────────────────────

  function syncHighlight(): void {
    applyHighlight(bgInner, tokeniseBrackets(ta.value));
  }

  function syncScroll(): void {
    // Direct scrollTop assignment works because bg has overflow:auto +
    // hidden scrollbar — identical to textarea scroll model.
    bg.scrollTop  = ta.scrollTop;
    bg.scrollLeft = ta.scrollLeft;
  }

  let debounceTimer: ReturnType<typeof setTimeout> | null = null;

  /**
   * Render the .jeh-err bar.
   * - syntaxMsg set → red syntax error (text only, role="status" on errDiv)
   * - issues.length > 0 → yellow warning with <details> expand
   * - both null/empty → hide bar
   * Always clears child nodes first (prevents DOM accumulation across state transitions).
   */
  function renderErrBar(syntaxMsg: string | null, issues: ValidationIssue[]): void {
    // Always clear (textContent='' removes all child nodes too)
    errDiv.textContent = '';
    errDiv.removeAttribute('role');
    errDiv.removeAttribute('aria-live');
    errDiv.className = 'jeh-err';

    if (syntaxMsg) {
      // Syntax error: simple text, restore live region on errDiv
      errDiv.setAttribute('role', 'status');
      errDiv.setAttribute('aria-live', 'polite');
      errDiv.textContent = '⚠ ' + syntaxMsg;
      errDiv.style.display = 'block';
      return;
    }

    if (issues.length === 0) {
      errDiv.style.display = 'none';
      return;
    }

    // Validation warning: split aria-live from <details>
    errDiv.classList.add('jeh-err--warn');
    errDiv.style.display = 'block';

    // 1-line summary span — live region for screen reader notification
    const summarySpan = document.createElement('span');
    summarySpan.className = 'jeh-err-summary';
    summarySpan.setAttribute('role', 'status');
    summarySpan.setAttribute('aria-live', 'polite');
    summarySpan.textContent =
      '⚠ ' +
      _trWarn('json_doctor.summary', '{n} issue(s) found ▼', { n: String(issues.length) });
    errDiv.appendChild(summarySpan);

    // <details> expandable list — NOT inside live region
    const details = document.createElement('details');
    details.className = 'jeh-err-details';

    const summary = document.createElement('summary');
    summary.textContent = _trWarn('json_doctor.show_details', 'Show details');
    details.appendChild(summary);

    const ul = document.createElement('ul');
    ul.style.margin = '4px 0 0 0';
    ul.style.paddingLeft = '16px';
    for (const issue of issues) {
      const li = document.createElement('li');
      li.textContent = (issue.path ? issue.path + ': ' : '') + issue.message;
      ul.appendChild(li);
    }
    details.appendChild(ul);
    errDiv.appendChild(details);
  }

  function runValidationNow(): void {
    if (!ta.value.trim()) {
      currentIssues = [];
      renderErrBar(null, []);
      return;
    }
    try {
      JSON.parse(ta.value);
    } catch (e: unknown) {
      // Syntax error: show syntax message, clear validation issues
      currentIssues = [];
      renderErrBar(formatJsonError(e instanceof Error ? e.message : String(e), ta.value), []);
      return;
    }
    // Syntax OK: run schema validation (guard against schema.applies throwing)
    try {
      currentIssues = schema ? validateJson(ta.value, schema) : [];
    } catch {
      currentIssues = [];
    }
    renderErrBar(null, currentIssues);
  }

  function checkError(): void {
    runValidationNow();
  }

  function onInput(): void {
    syncHighlight();
    syncScroll();
    if (debounceTimer !== null) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(checkError, debounceMs);
  }

  ta.addEventListener('input', onInput);
  ta.addEventListener('scroll', syncScroll);

  // Initial render
  syncHighlight();
  checkError();

  // ── Cleanup ──────────────────────────────────────────────────────────────

  const cleanupFn = (): void => {
    ta.removeEventListener('input', onInput);
    ta.removeEventListener('scroll', syncScroll);
    if (debounceTimer !== null) clearTimeout(debounceTimer);
    currentIssues = [];
    isDestroyed = true;

    ta.classList.remove('jeh-enhanced');
    ta.style.removeProperty('background');
    ta.style.removeProperty('color');
    ta.style.removeProperty('-webkit-text-fill-color');
    ta.style.removeProperty('caret-color');
    ta.style.removeProperty('scrollbar-width');
    ta.style.removeProperty('-ms-overflow-style');
    ta.style.removeProperty('grid-area');
    for (const [prop] of STABLE_RENDER_PROPS) ta.style.removeProperty(prop);

    if (wrapper.parentNode) {
      wrapper.parentNode.insertBefore(ta, wrapper);
      wrapper.remove();
    }
    errDiv.remove();
    delete tagged[_TAG];
  };

  const cleanup: EnhanceCleanup = Object.assign(cleanupFn, {
    getValidationIssues: (): ValidationIssue[] => {
      if (isDestroyed) return [];
      // Flush pending debounce so caller gets up-to-date results
      if (debounceTimer !== null) {
        clearTimeout(debounceTimer);
        debounceTimer = null;
        runValidationNow();
      }
      return currentIssues;
    },
  });

  tagged[_TAG] = cleanup;
  return cleanup;
}

/**
 * Auto-initialise all textareas with a `data-json-enhance` attribute.
 * Safe to call before DOMContentLoaded; defers init if DOM is not ready.
 */
export function initJsonEditorEnhance(): void {
  const doInit = (): void => {
    document.querySelectorAll<HTMLTextAreaElement>('textarea[data-json-enhance]').forEach(ta => {
      const schemaKey = ta.dataset.jsonSchema;
      const schema = schemaKey ? SCHEMA_REGISTRY[schemaKey] : undefined;
      enhanceJsonEditor(ta, { schema });
    });
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', doInit, { once: true });
  } else {
    doInit();
  }
}

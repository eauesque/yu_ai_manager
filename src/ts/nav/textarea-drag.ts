/**
 * nav/textarea-drag — Drag-and-drop text movement within textareas.
 *
 * Enables selecting text in any textarea and dragging it to a new position.
 * Uses a mirror div technique to map mouse coordinates to character indices
 * within the textarea, since the browser does not expose textarea internal
 * layout to the DOM.
 *
 * State machine: idle -> pending -> dragging -> idle
 *
 * Automatically applies to all textareas via event delegation on document.
 * Skips readonly/disabled textareas.
 */

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type DragState = 'idle' | 'pending' | 'dragging';

interface DragContext {
  ta: HTMLTextAreaElement;
  selStart: number;
  selEnd: number;
  selText: string;
  startX: number;
  startY: number;
  ghost: HTMLDivElement | null;
  caret: HTMLDivElement | null;
  mirror: HTMLDivElement | null;
  dropIdx: number;
}

type TextareaMirrorModule = typeof import('./textarea-mirror');

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const DRAG_THRESHOLD = 5;          // px before pending -> dragging

/* ------------------------------------------------------------------ */
/*  Module state                                                       */
/* ------------------------------------------------------------------ */

let state: DragState = 'idle';
let ctx: DragContext | null = null;
let _mirrorModPromise: Promise<TextareaMirrorModule> | null = null;

function _loadMirrorMod(): Promise<TextareaMirrorModule> {
  if (!_mirrorModPromise) {
    _mirrorModPromise = import('./textarea-mirror').catch((e) => {
      _mirrorModPromise = null; // allow retry on next interaction
      return Promise.reject(e) as never;
    });
  }
  return _mirrorModPromise;
}

/* ------------------------------------------------------------------ */
/*  Drop logic                                                         */
/* ------------------------------------------------------------------ */

function executeDrop(ta: HTMLTextAreaElement, selStart: number, selEnd: number, dropIdx: number): void {
  if (dropIdx >= selStart && dropIdx <= selEnd) return; // drop inside selection = no-op

  const selText = ta.value.slice(selStart, selEnd);
  let newVal: string;
  let newSelStart: number;
  let newSelEnd: number;

  if (dropIdx < selStart) {
    // Move before the original selection
    newVal =
      ta.value.slice(0, dropIdx) +
      selText +
      ta.value.slice(dropIdx, selStart) +
      ta.value.slice(selEnd);
    newSelStart = dropIdx;
    newSelEnd = dropIdx + selText.length;
  } else {
    // Move after the original selection
    const adjustedDrop = dropIdx - selText.length;
    newVal =
      ta.value.slice(0, selStart) +
      ta.value.slice(selEnd, dropIdx) +
      selText +
      ta.value.slice(dropIdx);
    newSelStart = adjustedDrop;
    newSelEnd = adjustedDrop + selText.length;
  }

  // Try execCommand for undo support
  ta.focus();
  ta.setSelectionRange(0, ta.value.length);
  if (!document.execCommand('insertText', false, newVal)) {
    ta.value = newVal;
    ta.dispatchEvent(new Event('input', { bubbles: true }));
  }

  ta.setSelectionRange(newSelStart, newSelEnd);
}

/* ------------------------------------------------------------------ */
/*  Cleanup                                                            */
/* ------------------------------------------------------------------ */

function cleanup(): void {
  if (ctx) {
    ctx.ghost?.remove();
    ctx.caret?.remove();
    ctx.mirror?.remove();
    ctx = null;
  }
  state = 'idle';
  document.body.classList.remove('ta-dragging');
}

/* ------------------------------------------------------------------ */
/*  Event handlers                                                     */
/* ------------------------------------------------------------------ */

async function onMouseDown(e: MouseEvent): Promise<void> {
  if (e.button !== 0) return;                         // left click only
  const target = e.target as HTMLElement;
  if (target.tagName !== 'TEXTAREA') return;

  const ta = target as HTMLTextAreaElement;
  if (ta.readOnly || ta.disabled) return;

  const { selectionStart, selectionEnd } = ta;
  if (selectionStart === selectionEnd) return;        // no selection

  if (!_mirrorModPromise) {
    void _loadMirrorMod();
    return;
  }

  const mirrorMod = await _loadMirrorMod();
  if (state !== 'idle') return;

  // Build mirror to check if click is within selection
  const mirror = mirrorMod.createMirror(ta);
  const clickIdx = mirrorMod.charIndexFromPoint(mirror, e.clientX, e.clientY);

  if (clickIdx < selectionStart || clickIdx >= selectionEnd) {
    mirror.remove();
    return; // click outside selection — let browser handle normally
  }

  // Prevent default to keep selection intact
  e.preventDefault();

  state = 'pending';
  ctx = {
    ta,
    selStart: selectionStart,
    selEnd: selectionEnd,
    selText: ta.value.slice(selectionStart, selectionEnd),
    startX: e.clientX,
    startY: e.clientY,
    ghost: null,
    caret: null,
    mirror,
    dropIdx: clickIdx,
  };
}

function onMouseMove(e: MouseEvent): void {
  if (!ctx) return;

  if (state === 'pending') {
    const dx = e.clientX - ctx.startX;
    const dy = e.clientY - ctx.startY;
    if (dx * dx + dy * dy < DRAG_THRESHOLD * DRAG_THRESHOLD) return;

    // Transition to dragging
    state = 'dragging';
    _loadMirrorMod().then((mirrorMod) => {
      if (!ctx || state !== 'dragging') return;
      ctx.ghost = mirrorMod.createGhost(ctx.selText);
      ctx.caret = mirrorMod.createCaret();
    }).catch(() => {
      cleanup();
    });
    document.body.classList.add('ta-dragging');
  }

  if (state === 'dragging' && ctx.ghost && ctx.caret && ctx.mirror) {
    _loadMirrorMod().then((mirrorMod) => {
      if (!ctx || state !== 'dragging' || !ctx.ghost || !ctx.caret || !ctx.mirror) return;

      mirrorMod.positionGhost(ctx.ghost, e.clientX, e.clientY);

      // Sync mirror scroll with textarea
      ctx.mirror.scrollTop = ctx.ta.scrollTop;

      const idx = mirrorMod.charIndexFromPoint(ctx.mirror, e.clientX, e.clientY);
      ctx.dropIdx = idx;

      // Position caret indicator
      const rect = mirrorMod.caretRectAt(ctx.mirror, idx);
      if (rect) {
        mirrorMod.positionCaret(ctx.caret, rect);
      }

      // Visual feedback: hide caret if dropping inside selection (no-op zone)
      if (idx >= ctx.selStart && idx <= ctx.selEnd) {
        ctx.caret.style.display = 'none';
      } else {
        ctx.caret.style.display = '';
      }
    }).catch(() => {
      cleanup();
    });
  }
}

function onMouseUp(_e: MouseEvent): void {
  if (!ctx) return;

  if (state === 'dragging') {
    executeDrop(ctx.ta, ctx.selStart, ctx.selEnd, ctx.dropIdx);
  }

  cleanup();
}

function onKeyDown(e: KeyboardEvent): void {
  if (state !== 'idle' && e.key === 'Escape') {
    e.preventDefault();
    cleanup();
  }
}

function onTextareaIntent(e: Event): void {
  const target = e.target as HTMLElement | null;
  if (target?.tagName === 'TEXTAREA') {
    _loadMirrorMod().catch(() => {});
  }
}

/* ------------------------------------------------------------------ */
/*  Public init                                                        */
/* ------------------------------------------------------------------ */

export function initTextareaDrag(): void {
  // Capture phase on mousedown to intercept before textarea clears selection
  document.addEventListener('mousedown', onMouseDown, true);
  document.addEventListener('mousemove', onMouseMove);
  document.addEventListener('mouseup', onMouseUp);
  document.addEventListener('keydown', onKeyDown);
  document.addEventListener('focusin', onTextareaIntent);
  document.addEventListener('mouseover', onTextareaIntent, { passive: true });
}

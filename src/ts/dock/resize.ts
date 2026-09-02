/**
 * Regex cheat sheet dock — pointer-based resize.
 *
 * Allows dragging the top handle of the cheat panel to resize
 * its height. Persists the height in localStorage.
 */

/* ------------------------------------------------------------------ */
/*  DOM helper                                                        */
/* ------------------------------------------------------------------ */

function $(id: string): HTMLElement | null {
  return document.getElementById(id);
}

/* ------------------------------------------------------------------ */
/*  Constants                                                         */
/* ------------------------------------------------------------------ */

const LS_HEIGHT = 'regexCheatPanelHeight' as const;
const MIN_HEIGHT = 220;

function maxHeight(): number {
  return Math.floor(window.innerHeight * 0.8);
}

/* ------------------------------------------------------------------ */
/*  Public: initialise resize behaviour                               */
/* ------------------------------------------------------------------ */

export function initCheatResize(): void {
  const panel  = $('regexCheatPanel');
  const handle = $('cheatResizeHandle');
  if (!panel || !handle) return;

  /* Restore persisted height */
  const saved = parseInt(localStorage.getItem(LS_HEIGHT) || '', 10);
  if (saved && Number.isFinite(saved)) {
    panel.style.height = saved + 'px';
  }

  let startY   = 0;
  let startH   = 0;
  let dragging  = false;

  /* --- Pointer down: begin drag --- */
  handle.addEventListener('pointerdown', (e: PointerEvent): void => {
    if (!panel.classList.contains('open')) return;
    dragging = true;
    startY   = e.clientY;
    startH   = panel.getBoundingClientRect().height;
    handle.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  /* --- Pointer move: resize panel --- */
  handle.addEventListener('pointermove', (e: PointerEvent): void => {
    if (!dragging) return;
    const dy = e.clientY - startY;
    let h = Math.round(startH - dy);
    h = Math.max(MIN_HEIGHT, Math.min(maxHeight(), h));
    panel.style.height = h + 'px';
    e.preventDefault();
  });

  /* --- Pointer up / cancel: end drag & persist --- */
  const endDrag = (e: PointerEvent): void => {
    if (!dragging) return;
    dragging = false;
    try {
      const h = Math.round(panel.getBoundingClientRect().height);
      localStorage.setItem(LS_HEIGHT, String(h));
    } catch {
      // localStorage may be full or unavailable — ignore
    }
    e.preventDefault();
  };

  handle.addEventListener('pointerup', endDrag);
  handle.addEventListener('pointercancel', endDrag);

  /* --- Window resize: clamp panel height to new viewport --- */
  window.addEventListener('resize', (): void => {
    const h = parseInt(panel.style.height || '', 10);
    if (!h) return;
    const clamped = Math.max(MIN_HEIGHT, Math.min(maxHeight(), h));
    if (clamped !== h) panel.style.height = clamped + 'px';
  });
}

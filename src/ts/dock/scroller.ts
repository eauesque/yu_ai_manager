/**
 * Regex cheat sheet dock — scroll enhancements.
 *
 * - Converts vertical wheel events into horizontal scroll
 *   when the scroller overflows horizontally.
 * - Snap-scrolls to the nearest cheat-item after a brief pause.
 */

/* ------------------------------------------------------------------ */
/*  DOM helper                                                        */
/* ------------------------------------------------------------------ */

function $(id: string): HTMLElement | null {
  return document.getElementById(id);
}

/* ------------------------------------------------------------------ */
/*  Snap-scroll debounce interval (ms)                                */
/* ------------------------------------------------------------------ */

const SNAP_DELAY = 120;

/* ------------------------------------------------------------------ */
/*  Public: wire up scroll enhancements                               */
/* ------------------------------------------------------------------ */

export function enhanceCheatScroller(): void {
  const scroller = $('regexCheatScroller');
  if (!scroller) return;

  /* --- Vertical wheel → horizontal scroll --- */
  scroller.addEventListener(
    'wheel',
    (e: WheelEvent): void => {
      const dy = e.deltaY || 0;
      const dx = e.deltaX || 0;
      if (scroller.scrollWidth <= scroller.clientWidth) return;
      if (Math.abs(dx) > Math.abs(dy)) return;
      scroller.scrollLeft += dy;
      e.preventDefault();
    },
    { passive: false },
  );

  /* --- Snap to nearest cheat-item after scroll settles --- */
  let snapTimer: ReturnType<typeof setTimeout> | null = null;

  scroller.addEventListener(
    'scroll',
    (): void => {
      if (!scroller.closest('.cheat-panel')?.classList.contains('open')) return;

      if (snapTimer !== null) clearTimeout(snapTimer);

      snapTimer = setTimeout((): void => {
        const items = scroller.querySelectorAll<HTMLElement>('.cheat-item');
        if (!items.length) return;

        const left = scroller.scrollLeft;
        let best: number | null = null;
        let bestDist = Infinity;

        for (const it of items) {
          const x = it.offsetLeft;
          const d = Math.abs(x - left);
          if (d < bestDist) {
            bestDist = d;
            best = x;
          }
        }

        if (best !== null) {
          scroller.scrollTo({ left: best, behavior: 'smooth' });
        }
      }, SNAP_DELAY);
    },
    { passive: true },
  );
}

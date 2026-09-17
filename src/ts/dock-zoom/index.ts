/**
 * Dock-style fish-eye magnification effect for the result grid.
 *
 * When hovering over thumbnails, the hovered card scales up and nearby cards
 * also scale proportionally — effect diminishes with distance (Gaussian falloff).
 * Similar to the macOS Dock magnification behavior.
 */

const MAX_SCALE = 0.15;        // maximum extra scale (1 + 0.15 = 1.15x)
const NEIGHBOR_REACH = 2.2;    // influence extends to ~2.2 card-widths from cursor

interface CardRect {
  el: HTMLElement;
  cx: number;  // center x
  cy: number;  // center y
}

let _grid: HTMLElement | null = null;
let _cache: CardRect[] = [];
let _influencePx = 600;       // recalculated from actual card size
let _sigma = 240;
let _raf = 0;
let _mouseX = 0;
let _mouseY = 0;
let _active = false;
let _bound = false;

/* ---- Gaussian helper ---- */

function _gaussian(dist: number): number {
  return Math.exp(-(dist * dist) / (2 * _sigma * _sigma));
}

/* ---- Position cache ---- */

function _rebuildCache(): void {
  _cache = [];
  if (!_grid) return;
  // Exclude container cards — dock zoom is unnecessary on collapsed cards (reduces GPU load)
  const cards = _grid.querySelectorAll<HTMLElement>('.result-card:not(.container-card)');
  if (!cards.length) return;

  // Calculate influence radius from actual card width
  const firstRect = cards[0].getBoundingClientRect();
  if (firstRect.width > 0) {
    _influencePx = firstRect.width * NEIGHBOR_REACH;
    _sigma = _influencePx / 2.8;
  }

  cards.forEach(el => {
    const r = el.getBoundingClientRect();
    _cache.push({ el, cx: r.left + r.width / 2, cy: r.top + r.height / 2 });
  });
}

/* ---- Apply transforms ---- */

function _applyScales(): void {
  _raf = 0;
  if (!_active) return;

  for (let i = 0; i < _cache.length; i++) {
    const c = _cache[i];
    const dx = _mouseX - c.cx;
    const dy = _mouseY - c.cy;
    const dist = Math.sqrt(dx * dx + dy * dy);

    if (dist > _influencePx) {
      if (c.el.style.transform) {
        c.el.style.transform = '';
        c.el.style.zIndex = '';
        c.el.style.boxShadow = '';
      }
      continue;
    }

    const factor = _gaussian(dist);
    const s = 1 + MAX_SCALE * factor;
    c.el.style.transform = `scale(${s.toFixed(2)})`;
    c.el.style.zIndex = String(Math.round(factor * 10) + 2);
    // shadow only for the most magnified card (avoid per-frame blur recompute)
    if (factor > 0.7) {
      c.el.style.boxShadow = '0 8px 24px rgba(0,0,0,0.2)';
    } else {
      c.el.style.boxShadow = '';
    }
  }
}

function _scheduleApply(): void {
  if (!_raf) _raf = requestAnimationFrame(_applyScales);
}

/* ---- Reset all transforms ---- */

function _resetAll(): void {
  for (let i = 0; i < _cache.length; i++) {
    const c = _cache[i];
    c.el.style.transform = '';
    c.el.style.zIndex = '';
    c.el.style.boxShadow = '';
  }
}

/* ---- Event handlers ---- */

function _onMouseMove(e: MouseEvent): void {
  _mouseX = e.clientX;
  _mouseY = e.clientY;

  if (!_active) {
    _active = true;
    _rebuildCache();
  }
  _scheduleApply();
}

function _onMouseLeave(): void {
  _active = false;
  if (_raf) { cancelAnimationFrame(_raf); _raf = 0; }
  _resetAll();
}

function _onScroll(): void {
  if (_active) _rebuildCache();
  _scheduleApply();
}

/* ---- Public API ---- */

function _isDisabled(): boolean {
  return (
    document.body.classList.contains('no-dock-zoom') ||
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

export function initDockZoom(): void {
  if (_bound) return;
  _bound = true;

  _grid = document.getElementById('results');
  if (!_grid) return;

  document.body.classList.add('dock-zoom-js');

  _grid.addEventListener('mousemove', _onMouseMove, { passive: true });
  _grid.addEventListener('mouseleave', _onMouseLeave);
  window.addEventListener('scroll', _onScroll, { passive: true });

  // Rebuild cache after DOM mutations (new cards loaded)
  const observer = new MutationObserver(() => {
    if (_active) _rebuildCache();
  });
  observer.observe(_grid, { childList: true });

  // Respect dynamic toggle of dock zoom setting.
  // Only touch classList when the state actually needs to change,
  // to avoid re-triggering the MutationObserver in a loop.
  const mo = new MutationObserver(() => {
    const disabled = _isDisabled();
    const hasClass = document.body.classList.contains('dock-zoom-js');
    if (disabled && hasClass) {
      _onMouseLeave();
      document.body.classList.remove('dock-zoom-js');
    } else if (!disabled && !hasClass) {
      document.body.classList.add('dock-zoom-js');
    }
  });
  mo.observe(document.body, { attributeFilter: ['class'] });
}

/* Auto-init */
function _scheduleVisibleIdleInit(timeout = 3000): void {
  const run = (): void => {
    if (document.hidden || _isDisabled()) return;
    initDockZoom();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      if ('requestIdleCallback' in window) {
        window.requestIdleCallback(run, { timeout });
      } else {
        setTimeout(run, 1400);
      }
    }, { once: true });
    return;
  }

  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(run, { timeout });
    return;
  }

  setTimeout(run, 1400);
}

_scheduleVisibleIdleInit();

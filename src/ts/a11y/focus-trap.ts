/**
 * Generic focus trap for WCAG 2.2 AA dialog compliance.
 * Converted from static/js/a11y/focus-trap.js
 *
 * Usage:
 *   FocusTrap.activate(dialogEl, () => { closeMyDialog(); });
 *   FocusTrap.deactivate(dialogEl);
 */

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

interface TrapEntry {
  el: HTMLElement;
  onClose?: (() => void) | undefined;
  prev: HTMLElement | null;
  active: boolean;
}

const _traps = new Map<HTMLElement, TrapEntry>();

function getFocusable(container: HTMLElement): HTMLElement[] {
  const nodes = container.querySelectorAll(FOCUSABLE);
  const result: HTMLElement[] = [];
  for (let i = 0; i < nodes.length; i++) {
    const el = nodes[i] as HTMLElement;
    if (el.getAttribute('aria-hidden') === 'true') continue;
    if (el.offsetParent === null && el.getAttribute('type') !== 'hidden') continue;
    result.push(el);
  }
  return result;
}

function getActiveTrap(): TrapEntry | undefined {
  let found: TrapEntry | undefined;
  _traps.forEach(function (t) {
    if (t.active) found = t;
  });
  return found;
}

function onKeydown(e: KeyboardEvent): void {
  const trap = getActiveTrap();
  if (!trap) return;

  if (e.key === 'Tab') {
    const focusable = getFocusable(trap.el);
    if (!focusable.length) {
      e.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = document.activeElement;
    if (e.shiftKey) {
      if (active === first || !trap.el.contains(active)) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (active === last || !trap.el.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  if (e.key === 'Escape') {
    e.preventDefault();
    if (trap.onClose) trap.onClose();
  }
}

// Single global listener (capture phase for priority)
let _listening = false;
function ensureListener(): void {
  if (_listening) return;
  _listening = true;
  document.addEventListener('keydown', onKeydown, true);
}

/**
 * Activate focus trap on a dialog element.
 */
export function activate(el: HTMLElement, onClose?: () => void): void {
  ensureListener();
  const prev = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  _traps.set(el, { el, onClose, prev, active: true });

  // Focus first focusable element or the dialog itself
  const focusable = getFocusable(el);
  if (focusable.length) {
    focusable[0].focus();
  } else {
    el.setAttribute('tabindex', '-1');
    el.focus();
  }
}

/**
 * Deactivate focus trap and restore previous focus.
 */
export function deactivate(el: HTMLElement): void {
  const trap = _traps.get(el);
  if (!trap) return;
  trap.active = false;
  _traps.delete(el);

  // Restore focus
  const prev = trap.prev;
  if (prev && prev.isConnected && typeof prev.focus === 'function') {
    requestAnimationFrame(function () {
      prev.focus();
    });
  }
}

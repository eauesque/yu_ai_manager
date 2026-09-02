/**
 * Shared toast notifications.
 */

/** Maximum number of toasts visible at once */
const MAX_TOASTS = 5;

/**
 * Show a stacking toast notification.
 *
 * Multiple toasts stack vertically from the bottom. The legacy
 * single `#toast` element is kept for backwards-compatibility but
 * new toasts are created dynamically inside `#toast-container`.
 */
export function showToast(message: string, isError?: boolean): void {
  const container = _ensureContainer();

  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = message;
  el.style.background = isError ? 'rgba(180,40,40,0.86)' : 'rgba(0,0,0,0.78)';
  el.setAttribute('role', isError ? 'alert' : 'status');
  el.setAttribute('aria-live', isError ? 'assertive' : 'polite');
  el.setAttribute('aria-atomic', 'true');

  container.appendChild(el);

  void el.offsetWidth;
  el.classList.add('show');

  const toasts = container.querySelectorAll('.toast');
  if (toasts.length > MAX_TOASTS) {
    _dismissToast(toasts[0] as HTMLElement);
  }

  const duration = isError ? 4500 : 2500;
  setTimeout(() => _dismissToast(el), duration);
}

function _dismissToast(el: HTMLElement): void {
  el.classList.remove('show');
  el.classList.add('hide');
  el.addEventListener('transitionend', () => el.remove(), { once: true });
  setTimeout(() => { if (el.parentNode) el.remove(); }, 400);
}

function _ensureContainer(): HTMLElement {
  let container = document.getElementById('toast-container');
  if (container) return container;

  container = document.createElement('div');
  container.id = 'toast-container';
  document.body.appendChild(container);

  const legacy = document.getElementById('toast');
  if (legacy) legacy.style.display = 'none';

  return container;
}

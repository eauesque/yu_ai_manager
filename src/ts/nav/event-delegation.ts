/**
 * Generic event delegation for inline event handler migration.
 *
 * Replaces onclick="func()" with data-action="func" attributes,
 * resolving functions from window[name] or dotted paths at click time.
 *
 * Supported data attributes:
 *   data-action="funcName"           → window.funcName()
 *   data-action="featureApi.func"    → window.featureApi.func()
 *   data-action-arg="value"          → resolvedFn("value")
 *   data-action-event="change"       → listen for 'change' instead of 'click'
 *   data-action-this="1"             → window.funcName(element)
 *   data-action-enter="funcName"     → call on Enter key (keydown)
 *   data-action-toggle="funcName"    → call on <details> toggle (open only)
 *   data-action-self="1"             → only fire when the click target IS this
 *                                       element (backdrop-click-to-close pattern);
 *                                       clicks bubbling up from descendants are ignored
 *
 * For oninput that updates another element's text:
 *   data-mirror-target="elementId"   → el.textContent = this.value
 *   data-mirror-format="float2"      → parseFloat(value).toFixed(2)
 */

export function initEventDelegation(): void {
  // Click / change / input delegation
  document.addEventListener('click', (e) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>('[data-action]:not([data-action-scope])');
    if (!el) return;
    if (el.dataset.actionSelf && e.target !== el) return; // backdrop-only: ignore bubbled child clicks
    const eventType = el.dataset.actionEvent;
    if (eventType && eventType !== 'click') return; // handled by specific listener
    _dispatch(el, e);
  });

  // Change events (select, checkbox)
  document.addEventListener('change', (e) => {
    const el = e.target as HTMLElement;
    const actionEl = el.closest<HTMLElement>('[data-action][data-action-event="change"]:not([data-action-scope])');
    if (!actionEl) return;
    _dispatch(actionEl, e);
  });

  // Input events (range sliders, text fields)
  document.addEventListener('input', (e) => {
    const el = e.target as HTMLElement;
    // Mirror pattern: data-mirror-target (ID-based)
    if (el.dataset.mirrorTarget) {
      const target = document.getElementById(el.dataset.mirrorTarget);
      if (target) {
        const val = (el as HTMLInputElement).value;
        const fmt = el.dataset.mirrorFormat;
        target.textContent = fmt === 'float2' ? parseFloat(val).toFixed(2) : val;
      }
      return;
    }
    // Mirror pattern: data-mirror-target-class (class-based, for dynamic cards)
    // Walks up ancestors until it finds a descendant with the given class.
    if (el.dataset.mirrorTargetClass) {
      const cls = el.dataset.mirrorTargetClass;
      let scope: HTMLElement | null = el.parentElement;
      let target: HTMLElement | null = null;
      while (scope && !target) {
        target = scope.querySelector<HTMLElement>(`.${cls}`);
        if (target) break;
        scope = scope.parentElement;
      }
      if (target) {
        const val = (el as HTMLInputElement).value;
        const fmt = el.dataset.mirrorFormat;
        target.textContent = fmt === 'float2' ? parseFloat(val).toFixed(2) : val;
      }
      return;
    }
    const actionEl = el.closest<HTMLElement>('[data-action][data-action-event="input"]:not([data-action-scope])');
    if (!actionEl) return;
    _dispatch(actionEl, e);
  });

  // Enter key delegation
  document.addEventListener('keydown', (e) => {
    if ((e as KeyboardEvent).key !== 'Enter') return;
    const el = e.target as HTMLElement;
    const action = el.dataset.actionEnter;
    if (!action) return;
    e.preventDefault();
    const fn = _resolveAction(action);
    if (typeof fn === 'function') fn();
  });

  // Prevent form submission for password-wrapper forms (CSP-safe alternative to onsubmit)
  document.addEventListener('submit', (e) => {
    const form = e.target as HTMLFormElement;
    if (form.dataset?.noSubmit) e.preventDefault();
  });

  // Details toggle delegation
  document.addEventListener('toggle', (e) => {
    const el = e.target as HTMLDetailsElement;
    if (!el.open) return;
    const action = el.dataset.actionToggle;
    if (!action) return;
    const fn = _resolveAction(action);
    if (typeof fn === 'function') fn();
  }, true); // capture phase for toggle events
}

function _dispatch(el: HTMLElement, e: Event): void {
  const action = el.dataset.action;
  if (!action) return;
  const fn = _resolveAction(action);
  if (typeof fn !== 'function') return;

  const arg = el.dataset.actionArg;
  const useThis = el.dataset.actionThis;

  if (useThis) {
    (fn as (el: HTMLElement) => void)(el);
  } else if (arg !== undefined) {
    // Pass the event as second arg so handlers can inspect modifier keys / event type
    (fn as (a: string, ev: Event) => void)(arg, e);
  } else {
    (fn as () => void)();
  }
}

function _resolveAction(path: string): unknown {
  const root = window as unknown as Record<string, unknown>;
  if (!path.includes('.')) return root[path];

  return path.split('.').reduce<unknown>((current, key) => {
    if (!current || typeof current !== 'object') return undefined;
    return (current as Record<string, unknown>)[key];
  }, root);
}

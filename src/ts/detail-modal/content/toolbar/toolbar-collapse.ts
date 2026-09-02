/*
 * toolbar-collapse.ts — collapse/expand + overflow menu toggle helpers.
 * T-key handler and outside-click / ESC close: Task 7.
 * spec: docs/superpowers/specs/2026-05-04-modal-toolbar-floating-bar-merge-design.md
 */
import { getAppApi } from '../../../shared/browser-apis';

export function renderToolbarHandle(): string {
  const { escapeHtml } = getAppApi();
  const tr = (k: string) => escapeHtml((window as unknown as Record<string, (k: string) => string>).tr(k));
  return `<button type="button" class="modal-toolbar-handle" id="modalToolbarHandle" aria-label="${tr('detail.modal.toolbar_show')}"></button>`;
}

export function toggleOverflowMenu(): void {
  const menu = document.getElementById('modalToolbarOverflow');
  const btn = document.getElementById('modalToolbarOverflowBtn');
  if (!menu || !btn) return;
  const isOpen = menu.classList.toggle('is-open');
  btn.setAttribute('aria-expanded', String(isOpen));
  if (isOpen) {
    const first = menu.querySelector<HTMLElement>('[role="menuitem"]');
    first?.focus();
  } else {
    btn.focus();
  }
}

export function closeOverflowMenu(): void {
  const menu = document.getElementById('modalToolbarOverflow');
  const btn = document.getElementById('modalToolbarOverflowBtn');
  if (!menu || !btn) return;
  if (menu.classList.contains('is-open')) {
    menu.classList.remove('is-open');
    btn.setAttribute('aria-expanded', 'false');
  }
}

export function collapseToolbar(): void {
  const container = document.getElementById('modalImageContainer');
  container?.classList.add('toolbar-collapsed');
  closeOverflowMenu();
}

export function expandToolbar(): void {
  const container = document.getElementById('modalImageContainer');
  container?.classList.remove('toolbar-collapsed');
}

export function toggleToolbar(): void {
  const container = document.getElementById('modalImageContainer');
  if (!container) return;
  container.classList.toggle('toolbar-collapsed');
  if (!container.classList.contains('toolbar-collapsed')) {
    const tb = document.getElementById('modalToolbar');
    tb?.querySelector<HTMLElement>('button')?.focus();
  } else {
    closeOverflowMenu();
  }
}

let listenersAttached = false;

export function initToolbarCollapse(): void {
  if (listenersAttached) return;
  listenersAttached = true;

  // Edge handle click → expand (also handles Enter/Space natively via <button>)
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement | null;
    if (!target) return;
    const handle = target.closest('#modalToolbarHandle');
    if (handle) { expandToolbar(); return; }

    // Outside click closes overflow menu
    const menu = document.getElementById('modalToolbarOverflow');
    if (!menu?.classList.contains('is-open')) return;
    const wrap = target.closest('.tb-overflow-wrap');
    if (!wrap) closeOverflowMenu();
  }, true);

  // ESC closes overflow (without closing the modal)
  document.addEventListener('keydown', (e) => {
    const menu = document.getElementById('modalToolbarOverflow');
    if (e.key === 'Escape' && menu?.classList.contains('is-open')) {
      e.stopPropagation();
      closeOverflowMenu();
    }
  }, true);
}

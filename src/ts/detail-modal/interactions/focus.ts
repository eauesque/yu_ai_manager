export function getModalFocusableElements(): HTMLElement[] {
  const modal = document.getElementById('modal');
  if (!modal?.classList.contains('active')) return [];
  const selector = [
    'a[href]', 'button:not([disabled])', 'textarea:not([disabled])',
    'input:not([disabled]):not([type="hidden"])', 'select:not([disabled])',
    '[tabindex]:not([tabindex="-1"])'
  ].join(',');
  const nodes = Array.from(modal.querySelectorAll<HTMLElement>(selector));
  return nodes.filter((el) => {
    if (el.getAttribute('aria-hidden') === 'true') return false;
    return el.offsetParent !== null || el === document.activeElement;
  });
}

export function focusFirstInModal(): void {
  const modal = document.getElementById('modal');
  if (!modal?.classList.contains('active')) return;
  const preferred = modal.querySelector('.modal-close') as HTMLElement | null;
  if (preferred) { preferred.focus(); return; }
  const focusables = getModalFocusableElements();
  if (focusables[0]) { focusables[0].focus(); return; }
  const content = document.getElementById('modalContent');
  if (content) { content.tabIndex = -1; content.focus(); }
}

export function focusBestInModal(): void {
  const modal = document.getElementById('modal');
  if (!modal?.classList.contains('active')) return;
  const nextBtn = modal.querySelector('.modal-nav-right') as HTMLButtonElement | null;
  const prevBtn = modal.querySelector('.modal-nav-left') as HTMLButtonElement | null;
  const closeBtn = modal.querySelector('.modal-close') as HTMLElement | null;
  if (nextBtn && !nextBtn.disabled) { nextBtn.focus(); return; }
  if (prevBtn && !prevBtn.disabled) { prevBtn.focus(); return; }
  if (closeBtn) { closeBtn.focus(); return; }
  focusFirstInModal();
}

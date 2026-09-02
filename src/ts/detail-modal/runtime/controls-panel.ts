export function toggleModalInfo(): void {
  const modal = document.getElementById('modal');
  if (!modal) return;
  const info = modal.querySelector('.modal-info') as HTMLElement | null;
  const btn = document.getElementById('modalInfoToggle');
  if (!info) {
    console.warn('toggleModalInfo: .modal-info not found');
    return;
  }
  if (modal.classList.contains('immersive')) {
    info.style.display = '';
    info.classList.toggle('info-visible');
    return;
  }

  const isVisible = info.style.display !== 'none';
  info.style.display = isVisible ? 'none' : '';
  if (btn) {
    btn.textContent = '\u24D8';
    btn.classList.toggle('toggled-off', isVisible);
  }
  localStorage.setItem('modalInfoHidden', isVisible ? '1' : '0');
}

export function collapseControlsBar(): void {
  // Legacy no-op: toolbar is now always visible via .modal-toolbar
  localStorage.setItem('controlsBarCollapsed', '1');
}

export function expandControlsBar(): void {
  // Legacy no-op: toolbar is now always visible via .modal-toolbar
  localStorage.setItem('controlsBarCollapsed', '0');
}

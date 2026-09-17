let autoHideTimer: ReturnType<typeof setTimeout> | null = null;
let autoHideBound = false;
const IMMERSIVE_IDLE_HIDE_MS = 0;

function syncViewingToggleState(): void {
  const modal = document.getElementById('modal');
  const toggle = document.getElementById('modalViewingToggle');
  if (!modal || !toggle) return;
  const isImmersive = modal.classList.contains('immersive');
  toggle.setAttribute('aria-pressed', isImmersive ? 'true' : 'false');
  toggle.classList.toggle('is-active', isImmersive);
}

function onAutoHideMouseMove(): void {
  const container = document.getElementById('modalImageContainer');
  if (container) container.classList.remove('ui-hidden');
  if (autoHideTimer) clearTimeout(autoHideTimer);
  autoHideTimer = setTimeout(() => {
    const current = document.getElementById('modalImageContainer');
    if (current) current.classList.add('ui-hidden');
  }, IMMERSIVE_IDLE_HIDE_MS);
}

function initImmersiveAutoHide(): void {
  if (autoHideBound) return;
  document.addEventListener('mousemove', onAutoHideMouseMove);
  document.addEventListener('mousedown', onAutoHideMouseMove);
  autoHideBound = true;
  onAutoHideMouseMove();
}

function destroyImmersiveAutoHide(): void {
  if (!autoHideBound) return;
  document.removeEventListener('mousemove', onAutoHideMouseMove);
  document.removeEventListener('mousedown', onAutoHideMouseMove);
  autoHideBound = false;
  if (autoHideTimer) {
    clearTimeout(autoHideTimer);
    autoHideTimer = null;
  }
  const container = document.getElementById('modalImageContainer');
  if (container) container.classList.remove('ui-hidden');
}

export function toggleImmersiveMode(): void {
  const modal = document.getElementById('modal');
  if (!modal) return;
  const isImmersive = modal.classList.toggle('immersive');
  localStorage.setItem('immersiveMode', isImmersive ? '1' : '0');
  if (isImmersive) {
    initImmersiveAutoHide();
    const info = modal.querySelector('.modal-info') as HTMLElement | null;
    if (info) {
      info.classList.remove('info-visible');
      info.style.display = '';
    }
    syncViewingToggleState();
    return;
  }

  destroyImmersiveAutoHide();
  const info = modal.querySelector('.modal-info') as HTMLElement | null;
  if (info) {
    info.classList.remove('info-visible');
    info.style.display = localStorage.getItem('modalInfoHidden') === '1' ? 'none' : '';
  }
  syncViewingToggleState();
}

export function applyImmersiveIfStored(): void {
  const modal = document.getElementById('modal');
  if (!modal) return;
  const stored = localStorage.getItem('immersiveMode');
  if (stored === '1') {
    modal.classList.add('immersive');
    initImmersiveAutoHide();
  }
  syncViewingToggleState();
}

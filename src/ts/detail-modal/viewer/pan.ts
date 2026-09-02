import { viewerState as vs } from './state';

export function installPanHandlersOnce(): void {
  const container = vs.getModalImageContainer?.() as HTMLElement | null;
  if (!container) return;
  if (container.dataset.panInstalled === '1') return;
  container.dataset.panInstalled = '1';

  container.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if ((e.target as HTMLElement).closest('button, .modal-toolbar, .modal-filmstrip, .modal-kbd-guide, video')) return;
    if (!container.classList.contains('pannable')) return;
    vs.panState.active = true;
    vs.panState.pointerId = e.pointerId;
    vs.panState.startX = e.clientX;
    vs.panState.startY = e.clientY;
    vs.panState.startPanX = vs.panX;
    vs.panState.startPanY = vs.panY;
    container.classList.add('panning');
    try { container.setPointerCapture(e.pointerId); } catch (_e) { /* ignore */ }
  });

  container.addEventListener('pointermove', (e) => {
    if (!vs.panState.active) return;
    if (vs.panState.pointerId !== e.pointerId) return;
    const dx = e.clientX - vs.panState.startX;
    const dy = e.clientY - vs.panState.startY;
    vs.panX = vs.panState.startPanX + dx;
    vs.panY = vs.panState.startPanY + dy;
    vs.updatePanAvailability?.();
  });

  function endPan(e: PointerEvent) {
    if (!vs.panState.active) return;
    if (vs.panState.pointerId !== e.pointerId) return;
    vs.panState.active = false;
    vs.panState.pointerId = null;
    container!.classList.remove('panning');
    try { container!.releasePointerCapture(e.pointerId); } catch (_e) { /* ignore */ }
  }

  container.addEventListener('pointerup', endPan);
  container.addEventListener('pointercancel', endPan);
}

// Ctrl+wheel zoom
document.addEventListener(
  'wheel',
  (e) => {
    const modal = document.getElementById('modal');
    if (!modal?.classList.contains('active')) return;
    if (!(e.ctrlKey || e.metaKey)) return;
    const img = vs.getModalImage?.();
    if (!img) return;
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.05 : +0.05;
    vs.zoomStep?.(delta);
  },
  { passive: false }
);

window.addEventListener('resize', () => requestAnimationFrame(() => vs.updatePanAvailability?.()));
document.addEventListener('fullscreenchange', () => requestAnimationFrame(() => vs.updatePanAvailability?.()));

vs.installPanHandlersOnce = installPanHandlersOnce;

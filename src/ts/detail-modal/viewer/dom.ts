import { viewerState as vs } from './state';

export function getModalImage(): HTMLElement | null {
  return document.getElementById('modalImage');
}

export function getModalImageContainer(): Element | null {
  return document.querySelector('.modal-image-container');
}

function getModalStage(): HTMLElement | null {
  return document.getElementById('modalImageStage');
}

export function applyTransforms(): void {
  const img = getModalImage();
  const stage = getModalStage();
  if (!img || !stage) return;
  (img as HTMLElement).style.transform = `scale(${vs.currentScale})`;
  stage.style.transform = `translate(${vs.panX}px, ${vs.panY}px)`;
  const pct = `${Math.round(vs.currentScale * 100)}%`;
  const readout = document.getElementById('zoomReadout');
  if (readout) readout.textContent = pct;
}

export function updatePanAvailability(): void {
  const container = getModalImageContainer();
  const img = getModalImage();
  if (!container || !img) return;
  const contRect = container.getBoundingClientRect();
  const imgRect = img.getBoundingClientRect();
  const zoomedOrOriginal = vs.currentMode === 'original' || vs.currentScale > 1.01;
  const overflow = imgRect.width > contRect.width + 1 || imgRect.height > contRect.height + 1;
  const enable = zoomedOrOriginal && overflow;
  (container as HTMLElement).classList.toggle('pannable', enable);
  if (!enable) {
    if (vs.panX !== 0 || vs.panY !== 0) {
      vs.panX = 0;
      vs.panY = 0;
      applyTransforms();
    }
    return;
  }
  const maxX = Math.max(0, (imgRect.width - contRect.width) / 2);
  const maxY = Math.max(0, (imgRect.height - contRect.height) / 2);
  vs.panX = vs.clampNum(vs.panX, -maxX, maxX);
  vs.panY = vs.clampNum(vs.panY, -maxY, maxY);
  applyTransforms();
}

export function resetPan(): void {
  vs.panX = 0;
  vs.panY = 0;
  applyTransforms();
  updatePanAvailability();
}

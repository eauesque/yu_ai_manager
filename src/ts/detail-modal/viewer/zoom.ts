import { viewerState as vs } from './state';
import * as dom from './dom';

function setZoom(scale: number): void {
  vs.currentScale = vs.clampNum(scale, 0.1, 5.0);
  localStorage.setItem('imageZoomScale', String(vs.currentScale));
  dom.applyTransforms();
  requestAnimationFrame(() => dom.updatePanAvailability());
}

export function zoomStep(delta: number): void {
  setZoom(vs.currentScale + delta);
}

export function zoomReset(): void {
  setZoom(1.0);
}

export function initZoomFromStorage(): void {
  const saved = parseFloat(localStorage.getItem('imageZoomScale') || '1');
  if (!Number.isFinite(saved)) setZoom(1.0);
  else setZoom(saved);
}

const ALL_MODES = ['fit', 'fit-width', 'fit-height', 'fit-custom', 'original'];

export function setImageMode(mode: string): void {
  const img = dom.getModalImage();
  if (!img) return;
  vs.currentMode = mode;
  ALL_MODES.forEach(function (m) { img.classList.remove(m); });
  img.classList.add(mode);
  localStorage.setItem('imageDisplayMode', mode);
  if (mode === 'fit-custom') {
    let h = parseInt(localStorage.getItem('fitCustomHeight') || '600', 10);
    if (!h || h < 50) h = 600;
    (img as HTMLElement).style.maxHeight = h + 'px';
    (img as HTMLElement).style.height = h + 'px';
  } else {
    (img as HTMLElement).style.maxHeight = '';
    (img as HTMLElement).style.height = '';
  }
  ALL_MODES.forEach(function (m) {
    const btn = document.getElementById('btnMode_' + m);
    if (btn) (btn as HTMLElement).style.background = m === mode ? 'rgba(255,255,255,0.4)' : 'rgba(255,255,255,0.2)';
  });
  const customInput = document.getElementById('fitCustomHeightInput');
  if (customInput) (customInput as HTMLElement).style.display = mode === 'fit-custom' ? '' : 'none';
  requestAnimationFrame(() => dom.updatePanAvailability());
}

export function setFitCustomHeight(val: string): void {
  let h = parseInt(val, 10);
  if (!h || h < 50) h = 600;
  localStorage.setItem('fitCustomHeight', String(h));
  if (vs.currentMode === 'fit-custom') setImageMode('fit-custom');
}

export async function toggleFullscreen(): Promise<void> {
  const el = dom.getModalImageContainer();
  if (!el) return;
  try {
    if (!document.fullscreenElement) await (el as HTMLElement).requestFullscreen();
    else await document.exitFullscreen();
  } catch (e) {
    console.error('Fullscreen failed:', e);
  }
}

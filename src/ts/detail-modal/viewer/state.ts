import { getAppApi } from '../../shared/browser-apis';

// Clamp a number between min and max via shared app API
function clampNum(v: number, min: number, max: number): number {
  return getAppApi().clamp(v, min, max);
}

export interface PanState {
  active: boolean;
  startX: number;
  startY: number;
  startPanX: number;
  startPanY: number;
  pointerId: number | null;
}

export interface ViewerState {
  currentScale: number;
  currentMode: string;
  panX: number;
  panY: number;
  panState: PanState;
  clampNum: typeof clampNum;
  // These are filled in by core.ts
  getModalImage?: () => HTMLElement | null;
  getModalImageContainer?: () => Element | null;
  applyTransforms?: () => void;
  updatePanAvailability?: () => void;
  resetPan?: () => void;
  zoomStep?: (delta: number) => void;
  zoomReset?: () => void;
  setImageMode?: (mode: string) => void;
  setFitCustomHeight?: (val: string) => void;
  toggleFullscreen?: () => Promise<void>;
  initZoomFromStorage?: () => void;
  installPanHandlersOnce?: () => void;
}

export const viewerState: ViewerState = {
  currentScale: 1.0,
  currentMode: 'fit',
  panX: 0,
  panY: 0,
  panState: {
    active: false,
    startX: 0,
    startY: 0,
    startPanX: 0,
    startPanY: 0,
    pointerId: null,
  },
  clampNum,
};

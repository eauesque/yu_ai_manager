import { viewerState as vs } from './state';
import * as dom from './dom';
import * as zoom from './zoom';
import { installPanHandlersOnce } from './pan';

export const detailModalViewer = {
  getModalImage: () => dom.getModalImage(),
  applyTransforms: () => dom.applyTransforms(),
  updatePanAvailability: () => dom.updatePanAvailability(),
  installPanHandlersOnce: () => installPanHandlersOnce(),
  resetPan: () => dom.resetPan(),
  setImageMode: (mode: string) => zoom.setImageMode(mode),
  setFitCustomHeight: (val: string) => zoom.setFitCustomHeight(val),
  initZoomFromStorage: () => zoom.initZoomFromStorage(),
  zoomStep: (delta: number) => zoom.zoomStep(delta),
  zoomReset: () => zoom.zoomReset(),
  toggleFullscreen: () => zoom.toggleFullscreen(),
};

import { viewerState as vs } from './state';
import * as dom from './dom';
import * as zoom from './zoom';

vs.getModalImage = dom.getModalImage;
vs.getModalImageContainer = dom.getModalImageContainer;
vs.applyTransforms = dom.applyTransforms;
vs.updatePanAvailability = dom.updatePanAvailability;
vs.resetPan = dom.resetPan;

vs.zoomStep = zoom.zoomStep;
vs.zoomReset = zoom.zoomReset;
vs.setImageMode = zoom.setImageMode;
vs.setFitCustomHeight = zoom.setFitCustomHeight;
vs.toggleFullscreen = zoom.toggleFullscreen;
vs.initZoomFromStorage = zoom.initZoomFromStorage;

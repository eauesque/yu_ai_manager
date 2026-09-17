/**
 * controls.ts -- Modal view controls: immersive mode, info panel toggles,
 * spread view, random result, and controls bar collapse/expand.
 *
 * Filmstrip hover, keyboard guide, and close logic are in controls-hover.ts.
 */

import * as controlsMedia from './controls-media';
import { applyImmersiveIfStored, toggleImmersiveMode } from './controls-immersive';
import {
  initFilmstripHover, closeModal, toggleKbGuide,
} from './controls-hover';
import { collapseControlsBar, expandControlsBar, toggleModalInfo } from './controls-panel';
import {
  openRandomResult, reloadCurrentDetail, toggleSpreadDirection, toggleSpreadView,
} from './controls-navigation';

// Re-export for external consumers
export { closeModal, toggleKbGuide, initFilmstripHover } from './controls-hover';
export { applyImmersiveIfStored, toggleImmersiveMode } from './controls-immersive';
export { collapseControlsBar, expandControlsBar, toggleModalInfo } from './controls-panel';
export { openRandomResult, reloadCurrentDetail, toggleSpreadDirection, toggleSpreadView } from './controls-navigation';

/* ------------------------------------------------------------------ */
/* Public facade                                                       */
/* ------------------------------------------------------------------ */

export const detailModalRuntimeControls = {
  toggleImmersiveMode,
  applyImmersiveIfStored,
  toggleModalInfo,
  collapseControlsBar,
  expandControlsBar,
  cycleModalPlaybackRate: () => controlsMedia.cycleModalPlaybackRate(),
  openRandomResult,
  rewindModalMedia: () => controlsMedia.rewindModalMedia(),
  closeModal,
  toggleMediaResumeMode: () => controlsMedia.toggleMediaResumeMode(),
  toggleModalRepeat: () => controlsMedia.toggleModalRepeat(),
  updateRepeatButtonLabel: () => controlsMedia.updateRepeatButtonLabel(),
  toggleModalMediaPlayback: () => controlsMedia.toggleModalMediaPlayback(),
  updateResumeModeButtonLabel: () => controlsMedia.updateResumeModeButtonLabel(),
  forwardModalMedia: () => controlsMedia.forwardModalMedia(),
  toggleModalMute: () => controlsMedia.toggleModalMute(),
  initModalMediaUi: () => controlsMedia.initModalMediaUi(),
  updateModalSeekUi: () => controlsMedia.updateModalSeekUi(),
  initFilmstripHover,
  toggleSpreadView,
  toggleSpreadDirection,
  reloadCurrentDetail,
  toggleKbGuide,
};

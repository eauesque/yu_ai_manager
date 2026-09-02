// Content
import './content/media';
import './content/character';

// Tabs
import './tabs/modal-tabs';
import './tabs/ocr-panel';

// Viewer
import './viewer/core'; // Side-effect: wires viewerState
import { detailModalViewer } from './viewer/exports';
import { installDetailModalWindowBridges } from './bridges';
import { initDetailModalActionDispatch } from './action-dispatch';
import { createDetailModalServices } from './services';

// Interactions
import { initInteractions } from './interactions/interactions-index';

// Runtime
import { runtimeStateApi, modalDetailStateApi } from './runtime/state';
import './runtime/media-cleanup';
import { copyToClipboard } from './runtime/clipboard';
import * as autoplay from './runtime/autoplay';
import * as navControls from './runtime/nav-controls';
import './runtime/show-detail-helpers';
import { showDetail } from './runtime/show-detail-load';
import {
  toggleModalInfo,
  toggleSpreadView, toggleSpreadDirection,
  closeModal, toggleKbGuide,
  toggleImmersiveMode, detailModalRuntimeControls,
} from './runtime/controls';
import { updateModalNavButtons, navigateModal, searchByTag } from './runtime/nav';
import { openContainerViewForCurrentDetail } from '../runtime-pre/container-view';
import { getRuntimeToolsApi } from '../shared/browser-apis';

const toggleCharGridOverlay = () => {
  const stage = document.getElementById('modalImageStage');
  if (!stage) return;
  void window.runtimeInitApi?.toggleCharacterGrid(stage).then((visible: boolean) => {
    const btn = document.getElementById('charGridToggle');
    if (btn) btn.style.opacity = visible ? '1' : '0.45';
  });
};

const openFpbForCurrentImage = () => {
  const s = runtimeStateApi.getState();
  if (s && s.currentModalIndex >= 0 && s.currentResultIds.length > 0) {
    const fileId = s.currentResultIds[s.currentModalIndex];
    if (fileId != null) {
      window.open('/ext/freeze-pullback/?file_id=' + fileId, '_blank');
    }
  }
};

const services = createDetailModalServices({
  closeModal: () => closeModal(),
  collapseControlsBar: () => detailModalRuntimeControls.collapseControlsBar(),
  copyToClipboard: (text: string) => copyToClipboard(text),
  cycleModalPlaybackRate: () => detailModalRuntimeControls.cycleModalPlaybackRate(),
  expandControlsBar: () => detailModalRuntimeControls.expandControlsBar(),
  forwardModalMedia: () => detailModalRuntimeControls.forwardModalMedia(),
  navigateModal: (delta: number) => navigateModal(delta),
  openContainerViewForCurrentDetail: () => openContainerViewForCurrentDetail(),
  openFpbForCurrentImage: () => openFpbForCurrentImage(),
  rewindModalMedia: () => detailModalRuntimeControls.rewindModalMedia(),
  scrollFilmstripPage: (direction: number) => navControls.scrollFilmstripPage(direction),
  searchByTag: (tag: string) => searchByTag(tag),
  setAutoplayInterval: (value: string) => autoplay.setInterval_val(value),
  setFitCustomHeight: (value: string) => runtimeStateApi.viewerApi()?.setFitCustomHeight?.(value),
  setImageMode: (mode: string) => runtimeStateApi.viewerApi()?.setImageMode?.(mode),
  showDetail: (id: number, opts?: { scope?: string }) => showDetail(id, opts),
  toggleAutoplay: () => autoplay.toggle(),
  toggleCharGridOverlay: () => toggleCharGridOverlay(),
  toggleFavorite: (id: number) => { void getRuntimeToolsApi().toggleFavorite(id); },
  toggleFullscreen: () => runtimeStateApi.viewerApi()?.toggleFullscreen?.(),
  toggleImmersiveMode: () => toggleImmersiveMode(),
  toggleKbGuide: () => toggleKbGuide(),
  toggleMediaResumeMode: () => detailModalRuntimeControls.toggleMediaResumeMode(),
  toggleModalInfo: () => toggleModalInfo(),
  toggleModalMediaPlayback: () => detailModalRuntimeControls.toggleModalMediaPlayback(),
  toggleModalMute: () => detailModalRuntimeControls.toggleModalMute(),
  toggleModalRepeat: () => detailModalRuntimeControls.toggleModalRepeat(),
  toggleSpreadDirection: () => toggleSpreadDirection(),
  toggleSpreadView: () => toggleSpreadView(),
  updateModalNavButtons: () => updateModalNavButtons(),
  zoomReset: () => runtimeStateApi.viewerApi()?.zoomReset?.(),
  zoomStep: (delta: number) => runtimeStateApi.viewerApi()?.zoomStep?.(delta),
});

initDetailModalActionDispatch(services.actionRegistry);

installDetailModalWindowBridges({
  detailModalViewer,
  runtimeStateApi,
  detailModalRuntimeControls,
  modalDetailStateApi,
  compatApi: services.compatApi,
});

/* ── Interaction init ── */
initInteractions(services.interactionsApi);

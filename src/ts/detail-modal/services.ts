import { createDetailModalActionRegistry } from './action-registry';
import { createDetailModalCompatApi } from './bridge-compat';
import type { InteractionsApi } from './interactions/interactions-index';
import { initDetailModalRuntimeHooks } from './runtime/runtime-hooks';

interface DetailModalServicesDeps {
  closeModal: () => void;
  copyToClipboard: (text: string) => Promise<boolean>;
  navigateModal: (delta: number) => void;
  openContainerViewForCurrentDetail: () => void;
  openFpbForCurrentImage: () => void;
  rewindModalMedia: () => void;
  scrollFilmstripPage: (direction: number) => void;
  searchByTag: (tag: string) => void;
  setAutoplayInterval: (value: string) => void;
  setFitCustomHeight: (value: string) => void;
  setImageMode: (mode: string) => void;
  showDetail: (id: number, opts?: { scope?: string }) => void;
  toggleAutoplay: () => void;
  toggleCharGridOverlay: () => void;
  toggleFavorite: (id: number) => void;
  toggleFullscreen: () => void;
  toggleImmersiveMode: () => void;
  toggleKbGuide: () => void;
  toggleMediaResumeMode: () => void;
  toggleModalInfo: () => void;
  toggleModalMediaPlayback: () => void;
  toggleModalMute: () => void;
  toggleModalRepeat: () => void;
  toggleSpreadDirection: () => void;
  toggleSpreadView: () => void;
  updateModalNavButtons: () => void;
  zoomReset: () => void;
  zoomStep: (delta: number) => void;
  collapseControlsBar: () => void;
  cycleModalPlaybackRate: () => void;
  expandControlsBar: () => void;
  forwardModalMedia: () => void;
}

export function createDetailModalServices(deps: DetailModalServicesDeps): {
  actionRegistry: ReturnType<typeof createDetailModalActionRegistry>;
  compatApi: ReturnType<typeof createDetailModalCompatApi>;
  interactionsApi: InteractionsApi;
} {
  const interactionsApi: InteractionsApi = {
    closeModal: deps.closeModal,
    copyToClipboard: deps.copyToClipboard,
    navigateModal: deps.navigateModal,
    searchByTag: deps.searchByTag,
    showDetail: deps.showDetail,
    toggleAutoplay: deps.toggleAutoplay,
    toggleImmersiveMode: deps.toggleImmersiveMode,
    toggleKbGuide: deps.toggleKbGuide,
    toggleModalInfo: deps.toggleModalInfo,
    toggleModalMediaPlayback: deps.toggleModalMediaPlayback,
    toggleModalRepeat: deps.toggleModalRepeat,
    toggleSpreadDirection: deps.toggleSpreadDirection,
    toggleSpreadView: deps.toggleSpreadView,
    updateModalNavButtons: deps.updateModalNavButtons,
    rewindModalMedia: deps.rewindModalMedia,
  };

  initDetailModalRuntimeHooks({
    navigateModal: deps.navigateModal,
    rewindModalMedia: deps.rewindModalMedia,
    toggleModalMediaPlayback: deps.toggleModalMediaPlayback,
    toggleModalRepeat: deps.toggleModalRepeat,
    updateModalNavButtons: deps.updateModalNavButtons,
  });

  return {
    actionRegistry: createDetailModalActionRegistry({
      closeModal: deps.closeModal,
      collapseControlsBar: deps.collapseControlsBar,
      cycleModalPlaybackRate: deps.cycleModalPlaybackRate,
      expandControlsBar: deps.expandControlsBar,
      forwardModalMedia: deps.forwardModalMedia,
      navigateModal: deps.navigateModal,
      openContainerViewForCurrentDetail: deps.openContainerViewForCurrentDetail,
      openFpbForCurrentImage: deps.openFpbForCurrentImage,
      rewindModalMedia: deps.rewindModalMedia,
      scrollFilmstripPage: deps.scrollFilmstripPage,
      setAutoplayInterval: deps.setAutoplayInterval,
      setFitCustomHeight: deps.setFitCustomHeight,
      setImageMode: deps.setImageMode,
      showDetail: deps.showDetail,
      toggleAutoplay: deps.toggleAutoplay,
      toggleCharGridOverlay: deps.toggleCharGridOverlay,
      toggleFavorite: deps.toggleFavorite,
      toggleFullscreen: deps.toggleFullscreen,
      toggleImmersiveMode: deps.toggleImmersiveMode,
      toggleKbGuide: deps.toggleKbGuide,
      toggleMediaResumeMode: deps.toggleMediaResumeMode,
      toggleModalInfo: deps.toggleModalInfo,
      toggleModalMediaPlayback: deps.toggleModalMediaPlayback,
      toggleModalMute: deps.toggleModalMute,
      toggleModalRepeat: deps.toggleModalRepeat,
      toggleSpreadDirection: deps.toggleSpreadDirection,
      toggleSpreadView: deps.toggleSpreadView,
      zoomReset: deps.zoomReset,
      zoomStep: deps.zoomStep,
    }),
    compatApi: createDetailModalCompatApi({
      closeModal: deps.closeModal,
      copyToClipboard: deps.copyToClipboard,
      searchByTag: deps.searchByTag,
      showDetail: deps.showDetail,
    }),
    interactionsApi,
  };
}

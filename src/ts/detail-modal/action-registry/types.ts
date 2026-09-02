import type { DetailModalActionHandler } from '../action-dispatch';

export type DetailModalActionRegistry = Record<string, DetailModalActionHandler>;

export interface DetailModalActionRegistryDeps {
  closeModal: () => void;
  navigateModal: (delta: number) => void;
  showDetail: (id: number, opts?: { scope?: string }) => void;
  scrollFilmstripPage: (direction: number) => void;
  setImageMode: (mode: string) => void;
  setFitCustomHeight: (value: string) => void;
  zoomStep: (delta: number) => void;
  zoomReset: () => void;
  toggleFullscreen: () => void;
  toggleModalInfo: () => void;
  toggleImmersiveMode: () => void;
  toggleKbGuide: () => void;
  toggleAutoplay: () => void;
  setAutoplayInterval: (value: string) => void;
  collapseControlsBar: () => void;
  expandControlsBar: () => void;
  toggleModalMediaPlayback: () => void;
  rewindModalMedia: () => void;
  forwardModalMedia: () => void;
  toggleModalMute: () => void;
  toggleModalRepeat: () => void;
  cycleModalPlaybackRate: () => void;
  toggleMediaResumeMode: () => void;
  toggleSpreadView: () => void;
  toggleSpreadDirection: () => void;
  toggleFavorite: (id: number) => void;
  openContainerViewForCurrentDetail: () => void;
  openFpbForCurrentImage: () => void;
  toggleCharGridOverlay: () => void;
}

import type { DetailModalActionRegistry, DetailModalActionRegistryDeps } from './types';

export function createDetailModalControlActions(
  deps: Pick<
    DetailModalActionRegistryDeps,
    | 'closeModal'
    | 'collapseControlsBar'
    | 'cycleModalPlaybackRate'
    | 'expandControlsBar'
    | 'forwardModalMedia'
    | 'rewindModalMedia'
    | 'setAutoplayInterval'
    | 'toggleAutoplay'
    | 'toggleImmersiveMode'
    | 'toggleKbGuide'
    | 'toggleMediaResumeMode'
    | 'toggleModalInfo'
    | 'toggleModalMediaPlayback'
    | 'toggleModalMute'
    | 'toggleModalRepeat'
    | 'toggleSpreadDirection'
    | 'toggleSpreadView'
  >,
): DetailModalActionRegistry {
  return {
    closeModal: () => {
      deps.closeModal();
    },
    collapseControlsBar: () => {
      deps.collapseControlsBar();
    },
    cycleModalPlaybackRate: () => {
      deps.cycleModalPlaybackRate();
    },
    detailModalCloseIfNotPanning: ({ element }) => {
      if (!element.closest('.panning')) deps.closeModal();
    },
    detailModalSetAutoplayInterval: ({ element }) => {
      deps.setAutoplayInterval((element as HTMLInputElement).value);
    },
    expandControlsBar: () => {
      deps.expandControlsBar();
    },
    forwardModalMedia: () => {
      deps.forwardModalMedia();
    },
    rewindModalMedia: () => {
      deps.rewindModalMedia();
    },
    toggleAutoplay: () => {
      deps.toggleAutoplay();
    },
    toggleImmersiveMode: () => {
      deps.toggleImmersiveMode();
    },
    toggleKbGuide: () => {
      deps.toggleKbGuide();
    },
    toggleMediaResumeMode: () => {
      deps.toggleMediaResumeMode();
    },
    toggleModalInfo: () => {
      deps.toggleModalInfo();
    },
    toggleModalMediaPlayback: () => {
      deps.toggleModalMediaPlayback();
    },
    toggleModalMute: () => {
      deps.toggleModalMute();
    },
    toggleModalRepeat: () => {
      deps.toggleModalRepeat();
    },
    toggleSpreadDirection: () => {
      deps.toggleSpreadDirection();
    },
    toggleSpreadView: () => {
      deps.toggleSpreadView();
    },
  };
}

export interface DetailModalRuntimeHooks {
  navigateModal: (delta: number) => void;
  rewindModalMedia: () => void;
  toggleModalMediaPlayback: () => void;
  toggleModalRepeat: () => void;
  updateModalNavButtons: () => void;
}

const hooks: DetailModalRuntimeHooks = {
  navigateModal: () => {},
  rewindModalMedia: () => {},
  toggleModalMediaPlayback: () => {},
  toggleModalRepeat: () => {},
  updateModalNavButtons: () => {},
};

export function initDetailModalRuntimeHooks(nextHooks: DetailModalRuntimeHooks): void {
  hooks.navigateModal = nextHooks.navigateModal;
  hooks.rewindModalMedia = nextHooks.rewindModalMedia;
  hooks.toggleModalMediaPlayback = nextHooks.toggleModalMediaPlayback;
  hooks.toggleModalRepeat = nextHooks.toggleModalRepeat;
  hooks.updateModalNavButtons = nextHooks.updateModalNavButtons;
}

export function getDetailModalRuntimeHooks(): DetailModalRuntimeHooks {
  return hooks;
}

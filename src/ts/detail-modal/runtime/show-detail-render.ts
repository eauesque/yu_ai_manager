import { buildModalHtml, buildModalInfoHtml, mediaInfo } from '../content/media';
import * as helpers from './show-detail-helpers';
import { detailModalRuntimeControls } from './controls';
import { prefetchNeighborMetadata } from './metadata-prefetch';
import type { state as runtimeState } from './state';
import { deferredInit } from './show-detail-deferred';
import { preloadMediaLink, upgradeToFullImage } from './show-detail-media';

interface RenderDetailModalArgs {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
  id: number;
  requestSeq: number;
  wasActive: boolean;
  modal: HTMLElement;
  content: HTMLElement;
  state: typeof runtimeState;
}

export function renderDetailModal({
  data,
  id,
  requestSeq,
  wasActive,
  modal,
  content,
  state,
}: RenderDetailModalArgs): void {
  const storedMode = localStorage.getItem('imageDisplayMode') || 'fit';
  const mInfo = mediaInfo(data, id) || { isStillImage: true };
  const isStillImage = !!mInfo.isStillImage;

  content.innerHTML = buildModalHtml(data, mInfo, { scopeIds: state.currentResultIds, scope: state.viewerScope }) || '';

  if (wasActive) {
    requestAnimationFrame(() => content.classList.remove('transitioning'));
  }

  if (localStorage.getItem('modalKeepScroll') !== '1') {
    modal.scrollTop = 0;
    if (window.matchMedia('(min-width: 1200px)').matches) {
      const imgContainer = document.getElementById('modalImageContainer');
      if (imgContainer) imgContainer.scrollTop = 0;
    } else {
      content.scrollTop = 0;
    }
  }

  helpers.applyStoredModalVisibilityState();
  detailModalRuntimeControls.applyImmersiveIfStored();
  helpers.setupViewer(storedMode);
  helpers.setupMediaResume(id);
  detailModalRuntimeControls.initModalMediaUi();

  if ((mInfo.isVideo || mInfo.isAudio) && !mInfo.mediaUrl.startsWith('yufile://')) {
    preloadMediaLink(mInfo.mediaUrl, mInfo.isVideo ? 'video' : 'audio');
  }

  _schedulePostRenderWork(() => {
    upgradeToFullImage(requestSeq, state);
    helpers.preloadNeighborImages(state, isStillImage);
    prefetchNeighborMetadata(state.currentResultIds, state.currentModalIndex);
  });
  deferredInit(data, id, requestSeq, state);
  _scheduleMetaInfoPopulate(data, requestSeq, state);
}

function _schedulePostRenderWork(task: () => void): void {
  const run = (): void => {
    if (document.hidden) return;
    task();
  };

  if (typeof requestIdleCallback === 'function') {
    requestIdleCallback(run, { timeout: 250 });
    return;
  }

  setTimeout(run, 32);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function _scheduleMetaInfoPopulate(data: any, requestSeq: number, state: typeof runtimeState): void {
  const run = (): void => {
    if (document.hidden || state.detailLoadSeq !== requestSeq) return;
    const info = document.querySelector<HTMLElement>('.modal-info');
    if (!info || info.dataset.infoReady === '1') return;
    info.innerHTML = buildModalInfoHtml(data);
    info.dataset.infoReady = '1';
  };

  if (typeof requestIdleCallback === 'function') {
    requestIdleCallback(run, { timeout: 300 });
    return;
  }

  setTimeout(run, 24);
}

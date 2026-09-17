/**
 * detail-modal/content/media-modal.ts -- Build the full modal HTML from media info.
 */

import { renderMetaInfo } from '../../meta-renderer/core';
import { runtimeStateApi } from '../runtime/state';
import { getAppApi } from '../../shared/browser-apis';
import {
  MediaInfo, SpreadState,
  getSpreadState, renderMediaElement,
} from './media-info';
import { renderModalToolbar } from './toolbar/toolbar';
import { icon } from '../../shared/icon';

interface BuildModalOpts {
  scope?: string;
  scopeIds?: number[];
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function buildModalHtml(data: any, info: MediaInfo, opts?: BuildModalOpts): string {
  const { escapeHtml } = getAppApi();
  const th = (k: string, vars: unknown = null) => escapeHtml(window.tr(k, vars));
  const isZipMember = /^.+\.zip!.+$/i.test(String(data?.path || ''));
  const scope = (opts && opts.scope) || runtimeStateApi.getViewerScope() || 'result_set';
  const scopeIds: number[] = (opts && opts.scopeIds) || [];
  const currentId = Number(data?.id);
  const isImmersive = localStorage.getItem('immersiveMode') === '1';

  // Extract filename for descriptive alt text
  const rawPath = String(data?.path || '');
  const fileName = rawPath.split(/[\/\\]/).pop() || '';
  const altLabel = fileName ? escapeHtml(fileName) : escapeHtml(window.tr('detail.image_alt'));

  const spread = getSpreadState(scopeIds, currentId, scope);
  const canSpread = (scope === 'folder_only' || scope === 'container_only') && scopeIds.length > 1 && info.isStillImage;

  let mediaElement: string;
  let stageClasses = 'modal-image-stage';
  if (spread.enabled && info.isStillImage) {
    stageClasses += ' spread-view';
    if (spread.isRTL) stageClasses += ' spread-rtl';
    const storedMode = localStorage.getItem('imageDisplayMode') || 'fit';
    let pageId = currentId;
    const currentIdx = scopeIds.indexOf(currentId);
    if (currentIdx > 0 && (currentIdx % 2) === 0) {
      pageId = scopeIds[currentIdx - 1];
      const s = runtimeStateApi.getState();
      if (s) s.currentModalIndex = currentIdx - 1;
    }
    mediaElement = '<img class="modal-image spread-page ' + escapeHtml(storedMode) + '" id="modalImage" src="' + getAppApi().apiUrl('/api/original/' + pageId) + '" alt="' + altLabel + '" onload="this.dataset.loaded=\'1\'">';
    if (spread.pairId != null) {
      mediaElement += '<img class="modal-image spread-page ' + escapeHtml(storedMode) + '" id="modalImagePair" src="' + getAppApi().apiUrl('/api/original/' + spread.pairId) + '" alt="' + altLabel + '" onload="this.dataset.loaded=\'1\'">';
    }
  } else {
    mediaElement = renderMediaElement(info, altLabel);
  }

  const FILMSTRIP_WINDOW = 50;
  let filmstrip = '';
  if (scopeIds.length > 1) {
    const currentIndex = scopeIds.indexOf(currentId);
    const posLabel = currentIndex >= 0
      ? '<span class="modal-filmstrip-pos">' + (currentIndex + 1) + ' / ' + scopeIds.length + '</span>'
      : '';
    let winStart = 0, winEnd = scopeIds.length;
    if (scopeIds.length > FILMSTRIP_WINDOW && currentIndex >= 0) {
      const half = Math.floor(FILMSTRIP_WINDOW / 2);
      winStart = Math.max(0, currentIndex - half);
      winEnd = Math.min(scopeIds.length, winStart + FILMSTRIP_WINDOW);
      if (winEnd === scopeIds.length) winStart = Math.max(0, winEnd - FILMSTRIP_WINDOW);
    }
    let thumbs = '';
    for (let wi = winStart; wi < winEnd; wi++) {
      const fid = scopeIds[wi];
      const isCurrent = Number(fid) === currentId;
      thumbs += '<button type="button" class="modal-filmstrip-thumb' + (isCurrent ? ' active' : '') + '"'
        + ' data-fid="' + fid + '"'
        + ' data-scope="' + escapeHtml(scope) + '"'
        + ' data-action-scope="detail-modal" data-action="detailModalShowFromThumb"'
        + ' title="#' + fid + '" aria-label="Image #' + fid + '">'
        + '<img src="' + getAppApi().apiUrl('/api/thumbnail/' + fid) + '" loading="lazy" alt="#' + fid + '">'
        + '</button>';
    }
    filmstrip = '<div class="modal-filmstrip" id="modalFilmstrip">'
      + '<button type="button" class="modal-filmstrip-nav modal-filmstrip-nav--prev" data-action-scope="detail-modal" data-action="scrollFilmstripPage" data-action-arg="-1" aria-label="Previous thumbnails">\u2190</button>'
      + '<div class="modal-filmstrip-scroll" id="modalFilmstripScroll"'
      + ' data-window-start="' + winStart + '" data-window-end="' + winEnd + '">'
      + posLabel + thumbs
      + '</div>'
      + '<button type="button" class="modal-filmstrip-nav modal-filmstrip-nav--next" data-action-scope="detail-modal" data-action="scrollFilmstripPage" data-action-arg="1" aria-label="Next thumbnails">\u2192</button>'
      + '</div>';
  }

  let posBadgeHtml = '';
  if (scopeIds.length > 1) {
    const posIdx = scopeIds.indexOf(currentId);
    if (posIdx >= 0) {
      posBadgeHtml = '<div class="modal-pos-badge" id="modalPosBadge">' + (posIdx + 1) + ' / ' + scopeIds.length + '</div>';
    }
  }

  // Keyboard guide: compact, auto-dismiss
  const kbGuideHtml = localStorage.getItem('modalKbGuideHidden') !== '1'
    ? `<div class="modal-kbd-guide modal-kbd-floating${sessionStorage.getItem('kbGuideDismissed') === '1' ? ' kbd-guide-dismissed' : ''}" id="modalKeyboardGuide" aria-hidden="false">
      <button type="button" class="kbd-guide-dismiss" id="kbGuideDismissBtn" title="${th('keyboard.guide.dismiss')}" aria-label="${th('keyboard.guide.dismiss')}">&times;</button>
      <kbd>←</kbd><kbd>→</kbd> ${th('keyboard.guide.prev_next_or_seek')}
      <kbd>Esc</kbd> ${th('keyboard.guide.close')}
      <kbd>H</kbd> ${th('keyboard.guide.toggle_btn')}
    </div>`
    : '';

  // Build new unified toolbar (replaces .image-controls + .modal-floating-bar)
  const toolbarHtml = renderModalToolbar(info, {
    isZipMember,
    canSpread,
    spreadEnabled: spread.enabled,
    currentId,
  }, data);

  return `
    <div class="modal-image-container" id="modalImageContainer" style="position:relative;">
      <button class="modal-close" type="button" data-action-scope="detail-modal" data-action="closeModal" aria-label="${th('detail.modal.close')}">${icon('x')}</button>
      <button type="button" class="modal-viewing-toggle" id="modalViewingToggle"
        data-action-scope="detail-modal" data-action="toggleImmersiveMode"
        aria-pressed="${isImmersive ? 'true' : 'false'}"
        title="${th('detail.modal.viewing_mode')}" aria-label="${th('detail.modal.viewing_mode')}">🖼</button>
      <button class="modal-fav-btn" type="button" id="modalFavBtn" data-file-id="${currentId}" data-action-scope="detail-modal" data-action="toggleFavorite" data-action-arg="${currentId}" title="${th('detail.modal.favorite')}" aria-label="${th('detail.modal.favorite')}">${icon('star')}</button>
      <button type="button" class="modal-nav-arrow modal-nav-left" data-nav="${spread.enabled && spread.isRTL ? 'next' : 'prev'}" data-action-scope="detail-modal" data-action="navigateModal" data-action-arg="${spread.enabled && spread.isRTL ? '1' : '-1'}" title="${spread.enabled && spread.isRTL ? th('detail.modal.next') : th('detail.modal.prev')}" aria-label="${spread.enabled && spread.isRTL ? th('detail.modal.next') : th('detail.modal.prev')}">${icon('chevron-left')}</button>
      <button type="button" class="modal-nav-arrow modal-nav-right" data-nav="${spread.enabled && spread.isRTL ? 'prev' : 'next'}" data-action-scope="detail-modal" data-action="navigateModal" data-action-arg="${spread.enabled && spread.isRTL ? '-1' : '1'}" title="${spread.enabled && spread.isRTL ? th('detail.modal.prev') : th('detail.modal.next')}" aria-label="${spread.enabled && spread.isRTL ? th('detail.modal.prev') : th('detail.modal.next')}">${icon('chevron-right')}</button>
      ${posBadgeHtml}
      <div class="modal-viewer" id="modalViewer">
        <div class="${stageClasses}" id="modalImageStage">${mediaElement}</div>
      </div>
      ${filmstrip}
      ${toolbarHtml}
      ${kbGuideHtml}
    </div>
    <div class="modal-info"${spread.enabled ? ' style="display:none"' : ''} data-info-ready="0">
      <div class="modal-info-loading"></div>
    </div>
  `;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function buildModalInfoHtml(data: any): string {
  return renderMetaInfo(data, { mode: 'modal', showCopyButtons: true, showConvertButtons: true, showTagSearch: true });
}

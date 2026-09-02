/*
 * toolbar-still.ts — still-image primary toolbar segments.
 * Segments in order:
 *   1. Fav + Info
 *   2. Prev/Next
 *   3. Zoom (− / readout / +)
 *   4. Fit modes (5 modes + custom height input)
 *   5. Spread (2P + ↔; tb-spread-hidden when not applicable)
 *   6. Immersive ⛶ + Fullscreen ⤢
 *   7. Collection 📁
 *   8. Bridge Send (renderBridgeSendClusters — only if non-empty)
 *
 * Items intentionally omitted (moved to overflow / Task 6):
 *   autoplay button, autoplay interval, FPB, char grid,
 *   ZIP/container button, keyboard guide ?, bar collapse «
 *
 * spec: docs/superpowers/specs/2026-05-04-modal-toolbar-floating-bar-merge-design.md
 */
import type { MediaInfo } from '../media-info';
import { getAppApi } from '../../../shared/browser-apis';
import { renderBridgeSendClusters } from '../media-info';
import type { ToolbarOptions } from './toolbar';
import { icon } from '../../../shared/icon';

function ea(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function renderStillToolbar(info: MediaInfo, options: ToolbarOptions, data: any): string {
  const { escapeHtml } = getAppApi();
  const th = (k: string, vars: unknown = null) => escapeHtml(window.tr(k, vars));

  // ----- Segment 1: Fav + Info -----
  const seg1 = `<span class="tb-segment">
    <button type="button" class="zoom-btn" id="modalFavBtn"
      data-action-scope="detail-modal" data-action="toggleFav"
      title="${th('detail.modal.fav_toggle')}" aria-label="${th('detail.modal.fav_toggle')}">${icon('star')}</button>
    <button type="button" class="zoom-btn" id="modalInfoToggle"
      data-action-scope="detail-modal" data-action="toggleModalInfo"
      title="${th('detail.modal.info_toggle')}" aria-label="${th('detail.modal.info_toggle')}">${icon('info')}</button>
  </span>`;

  // ----- Segment 2: Prev / Next -----
  const seg2 = `<span class="tb-segment">
    <button type="button" class="zoom-btn"
      data-action-scope="detail-modal" data-action="navigateModal" data-action-arg="-1"
      title="${th('detail.modal.prev')}" aria-label="${th('detail.modal.prev')}">${icon('chevron-left')}</button>
    <button type="button" class="zoom-btn"
      data-action-scope="detail-modal" data-action="navigateModal" data-action-arg="1"
      title="${th('detail.modal.next')}" aria-label="${th('detail.modal.next')}">${icon('chevron-right')}</button>
  </span>`;

  // ----- Segment 3: Zoom -----
  const seg3 = `<span class="tb-segment">
    <button type="button" class="zoom-btn"
      data-action-scope="detail-modal" data-action="zoomStep" data-action-arg="-0.1"
      title="${th('detail.modal.zoom_out')}" aria-label="${th('detail.modal.zoom_out')}">－</button>
    <button type="button" class="zoom-btn zoom-readout" id="zoomReadout"
      data-action-scope="detail-modal" data-action="zoomReset"
      title="${th('detail.modal.zoom_reset')}" aria-label="${th('detail.modal.zoom_reset')}">100%</button>
    <button type="button" class="zoom-btn"
      data-action-scope="detail-modal" data-action="zoomStep" data-action-arg="0.1"
      title="${th('detail.modal.zoom_in')}" aria-label="${th('detail.modal.zoom_in')}">＋</button>
  </span>`;

  // ----- Segment 4: Fit modes (icon-only, glyph) -----
  const storedMode = localStorage.getItem('imageDisplayMode') || 'fit';
  const customH = localStorage.getItem('fitCustomHeight') || '600';
  // Glyph icons keep buttons compact and visually consistent with the rest of the bar.
  // Tooltip carries the localized name, so users still get full label on hover.
  const modeIcon = (id: string): string => {
    if (id === 'fit') return '▢';
    if (id === 'fit-width') return '⇔';
    if (id === 'fit-height') return '⇕';
    if (id === 'fit-custom') return '✎';
    if (id === 'original') return '⊙';
    return id;
  };
  const modeBtn = (id: string, label: string): string => {
    const active = storedMode === id ? ' tb-mode-active' : '';
    return `<button type="button" class="zoom-btn tb-mode-btn${active}" id="btnMode_${ea(id)}"
      data-action-scope="detail-modal" data-action="setImageMode" data-action-arg="${ea(id)}"
      title="${label}" aria-label="${label}">${modeIcon(id)}</button>`;
  };
  const customInput = `<input type="number" class="fit-custom-height-input tb-custom-h" id="fitCustomHeightInput"
    name="fitCustomHeight" value="${escapeHtml(customH)}" min="50" max="4000" step="50"
    data-action-scope="detail-modal" data-action="detailModalSetFitCustomHeight" data-action-event="change"
    title="Height (px)" aria-label="Height (px)"
    style="display:${storedMode === 'fit-custom' ? '' : 'none'}">`;
  const seg4 = `<span class="tb-segment">
    ${modeBtn('fit', th('detail.modal.mode_fit'))}
    ${modeBtn('fit-width', th('detail.modal.mode_fit_width'))}
    ${modeBtn('fit-height', th('detail.modal.mode_fit_height'))}
    ${options.spreadEnabled ? '' : modeBtn('fit-custom', th('detail.modal.mode_fit_custom')) + customInput}
    ${modeBtn('original', th('detail.modal.mode_original'))}
  </span>`;

  // ----- Segment 5: Spread -----
  // Always emit the segment; use tb-spread-hidden to hide when not applicable (preserves layout)
  let spreadContent = '';
  if (options.canSpread) {
    spreadContent = `<button type="button"
        class="zoom-btn${options.spreadEnabled ? '' : ' toggled-off'}" id="btnSpreadToggle"
        data-action-scope="detail-modal" data-action="toggleSpreadView"
        title="${th('detail.modal.spread_view')}">2P</button>`;
    if (options.spreadEnabled) {
      spreadContent += `<button type="button" class="zoom-btn" id="btnSpreadDir"
          data-action-scope="detail-modal" data-action="toggleSpreadDirection"
          title="${th('detail.modal.spread_direction')}">↔</button>`;
    }
  }
  const seg5 = `<span class="tb-segment${options.canSpread ? '' : ' tb-spread-hidden'}">
    ${spreadContent}
  </span>`;

  // ----- Segment 6: Immersive + Fullscreen -----
  const seg6 = `<span class="tb-segment">
    <button type="button" class="zoom-btn"
      data-action-scope="detail-modal" data-action="toggleImmersiveMode"
      title="${th('detail.modal.viewing_mode')}" aria-label="${th('detail.modal.viewing_mode')}">${icon('maximize')}</button>
    <button type="button" class="zoom-btn"
      data-action-scope="detail-modal" data-action="toggleFullscreen"
      title="${th('detail.modal.fullscreen')}" aria-label="${th('detail.modal.fullscreen')}">${icon('expand')}</button>
  </span>`;

  // ----- Segment 7: Collection -----
  const collectionBtn = options.currentId != null
    ? `<button type="button" class="zoom-btn" id="modalCollectionBtn"
        data-action-scope="detail-modal" data-action="addToCollectionPicker"
        data-action-arg="${options.currentId}"
        title="${th('detail.modal.add_to_collection')}"
        aria-label="${th('detail.modal.add_to_collection')}">📁</button>`
    : '';
  const seg7 = options.currentId != null
    ? `<span class="tb-segment">${collectionBtn}</span>`
    : '';

  // ----- Segment 8: Bridge Send (optional) -----
  const bridgeHtml = renderBridgeSendClusters(info, data);
  // renderBridgeSendClusters returns '' when nothing to show (no prompt/image)
  // It prepends a <span class="ctrl-div"> — strip that and wrap in tb-segment
  const bridgeInner = bridgeHtml.replace(/^<span class="ctrl-div"><\/span>/, '').trim();
  const seg8 = bridgeInner
    ? `<span class="tb-divider"></span><span class="tb-segment tb-bridge">${bridgeInner}</span>`
    : '';

  const divider = '<span class="tb-divider"></span>';

  // Reduced dividers (was 7, now 2 internal + 1 before bridge if present).
  // Function groups separated by dividers; within-group buttons just use gap.
  return [
    // Group A: fav/info/nav/zoom — frequent everyday actions
    seg1,
    seg2,
    seg3,
    divider,
    // Group B: image-mode controls (fit + spread)
    seg4,
    seg5,
    divider,
    // Group C: screen + collection
    seg6,
    seg7,
    // Group D: bridge send (own divider built into seg8 if present)
    seg8,
  ].join('\n');
}

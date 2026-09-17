/*
 * toolbar-media.ts — video/audio/animated-image toolbar (2-row grid).
 *
 * Row 1 (.tb-row-seek):  time display + seek bar
 * Row 2 (.tb-row-buttons): Fav | Info | Nav | Transport | Sound | Screen | Collection
 *
 * IDs preserved for controls-media.ts:
 *   modalSeek, modalVolume, modalMuteBtn, modalTime
 * IDs intentionally omitted (→ overflow / Task 6):
 *   modalRepeatBtn, mediaResumeToggle, btnAutoplay
 *
 * spec: docs/superpowers/specs/2026-05-04-modal-toolbar-floating-bar-merge-design.md
 */
import type { MediaInfo } from '../media-info';
import { getAppApi } from '../../../shared/browser-apis';
import type { ToolbarOptions } from './toolbar';
import { icon } from '../../../shared/icon';

export function renderMediaToolbar(_info: MediaInfo, options: ToolbarOptions): string {
  const { escapeHtml } = getAppApi();
  const tr = (k: string) => escapeHtml((window as unknown as Record<string, (k: string) => string>).tr(k));

  const currentId = options.currentId ?? null;

  // ----- Fav button (only when item is known) -----
  const fav = currentId != null
    ? `<button type="button" class="zoom-btn" id="modalFavBtn"
        data-action-scope="detail-modal" data-action="toggleFavorite"
        data-action-arg="${currentId}" data-file-id="${currentId}"
        title="${tr('detail.modal.favorite')}" aria-label="${tr('detail.modal.favorite')}">${icon('star')}</button>`
    : '';

  // ----- Info toggle -----
  const info_btn = `<button type="button" class="zoom-btn" id="modalInfoToggle"
    data-action-scope="detail-modal" data-action="toggleModalInfo"
    title="${tr('detail.modal.info_toggle')}" aria-label="${tr('detail.modal.info_toggle')}">${icon('info')}</button>`;

  // ----- Prev / Next navigation -----
  const nav = `<button type="button" class="zoom-btn"
    data-action-scope="detail-modal" data-action="navigateModal" data-action-arg="-1"
    title="${tr('detail.modal.prev')}" aria-label="${tr('detail.modal.prev')}">${icon('chevron-left')}</button>
  <button type="button" class="zoom-btn"
    data-action-scope="detail-modal" data-action="navigateModal" data-action-arg="1"
    title="${tr('detail.modal.next')}" aria-label="${tr('detail.modal.next')}">${icon('chevron-right')}</button>`;

  // ----- Transport: Play/Pause + Rewind + Forward -----
  const transport = `<button type="button" class="zoom-btn"
    data-action-scope="detail-modal" data-action="toggleModalMediaPlayback"
    title="Play / Pause (Space/K)" aria-label="Play / Pause (Space/K)">${icon('play')}</button>
  <button type="button" class="zoom-btn"
    data-action-scope="detail-modal" data-action="rewindModalMedia"
    title="Rewind 10s / Restart (J/0)" aria-label="Rewind 10s / Restart (J/0)">${icon('skip-back')}</button>
  <button type="button" class="zoom-btn"
    data-action-scope="detail-modal" data-action="forwardModalMedia"
    title="Forward 10s (L)" aria-label="Forward 10s (L)">${icon('skip-forward')}</button>`;

  // ----- Sound: Mute button + Volume slider -----
  const sound = `<button type="button" class="zoom-btn" id="modalMuteBtn"
    data-action-scope="detail-modal" data-action="toggleModalMute"
    title="Mute (M)" aria-label="Mute (M)">${icon('volume')}</button>
  <input type="range" id="modalVolume" name="modalVolume" class="modal-volume"
    min="0" max="1" value="1" step="0.01" aria-label="Volume" />`;

  // ----- Screen: Immersive + Fullscreen -----
  const screen = `<button type="button" class="zoom-btn"
    data-action-scope="detail-modal" data-action="toggleImmersiveMode"
    title="${tr('detail.modal.viewing_mode')}" aria-label="${tr('detail.modal.viewing_mode')}">${icon('maximize')}</button>
  <button type="button" class="zoom-btn"
    data-action-scope="detail-modal" data-action="toggleFullscreen"
    title="${tr('detail.modal.fullscreen')}" aria-label="${tr('detail.modal.fullscreen')}">${icon('expand')}</button>`;

  // ----- Collection (only when item is known) -----
  const collection = currentId != null
    ? `<button type="button" class="zoom-btn" id="modalCollectionBtn"
        data-action-scope="detail-modal" data-action="addToCollectionPicker"
        data-action-arg="${currentId}"
        title="${tr('detail.modal.add_to_collection')}" aria-label="${tr('detail.modal.add_to_collection')}">📁</button>`
    : '';

  return `
  <div class="tb-row-seek">
    <span class="modal-time" id="modalTime" aria-label="Time">00:00 / 00:00</span>
    <input type="range" id="modalSeek" name="modalSeek" class="modal-seek"
      min="0" max="1000" value="0" step="1" aria-label="Seek" />
  </div>
  <div class="tb-row-buttons">
    <span class="tb-segment">${fav}${info_btn}</span>
    <span class="tb-divider"></span>
    <span class="tb-segment">${nav}</span>
    <span class="tb-divider"></span>
    <span class="tb-segment">${transport}</span>
    <span class="tb-divider"></span>
    <span class="tb-segment">${sound}</span>
    <span class="tb-divider"></span>
    <span class="tb-segment">${screen}</span>
    <span class="tb-divider"></span>
    <span class="tb-segment">${collection}</span>
  </div>
`;
}

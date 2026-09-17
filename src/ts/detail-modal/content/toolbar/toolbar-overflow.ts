/*
 * toolbar-overflow.ts — overflow menu (…) with ARIA.
 * spec: docs/superpowers/specs/2026-05-04-modal-toolbar-floating-bar-merge-design.md
 */
import type { MediaInfo } from '../media-info';
import { getAppApi } from '../../../shared/browser-apis';
import type { ToolbarOptions } from './toolbar';
import { icon } from '../../../shared/icon';

export function renderOverflowMenu(info: MediaInfo, options: ToolbarOptions): string {
  const { escapeHtml } = getAppApi();
  const tr = (k: string) => escapeHtml((window as unknown as Record<string, (k: string) => string>).tr(k));
  const isMedia = info.isVideo || info.isAudio || info.isAnimatedImage;
  const isStill = info.isStillImage;
  const items: string[] = [];

  // Common: ZIP / Container View
  if (options.isZipMember) {
    items.push(`<button type="button" role="menuitem" class="zoom-btn" data-action-scope="detail-modal" data-action="openContainerViewForCurrentDetail">📦 ${tr('detail.modal.container_view')}</button>`);
  }

  // Still-only: autoplay + interval / FPB / char grid
  if (isStill) {
    const autoplayOn = localStorage.getItem('autoplayEnabled') === '1';
    const apInterval = localStorage.getItem('autoplayInterval') || '5';
    items.push(`<button type="button" role="menuitem" id="btnAutoplay" data-action-scope="detail-modal" data-action="toggleAutoplay">${autoplayOn ? icon('pause') : icon('play')} ${tr('detail.modal.autoplay')}</button>`);
    items.push(`<label role="menuitem" style="display:flex;align-items:center;gap:6px;padding:6px 12px"><span style="flex:1">${tr('detail.modal.autoplay_interval')}</span><input type="number" id="autoplayIntervalInput" name="autoplayInterval" value="${escapeHtml(apInterval)}" min="1" max="60" step="1" data-action-scope="detail-modal" data-action="detailModalSetAutoplayInterval" data-action-event="change" style="width:48px"></label>`);
    items.push(`<button type="button" role="menuitem" data-action-scope="detail-modal" data-action="openFpbForCurrentImage">FPB</button>`);
    items.push(`<button type="button" role="menuitem" id="charGridToggle" data-action-scope="detail-modal" data-action="toggleCharGridOverlay" style="display:none">${icon('grid')} Character Grid</button>`);
  }

  // Media-only: repeat / rate / resume / autoplay
  if (isMedia) {
    items.push(`<button type="button" role="menuitem" id="modalRepeatBtn" data-action-scope="detail-modal" data-action="toggleModalRepeat">${icon('repeat')} Repeat (R)</button>`);
    items.push(`<button type="button" role="menuitem" data-action-scope="detail-modal" data-action="cycleModalPlaybackRate">1x ${icon('repeat')} Speed (&lt; / &gt;)</button>`);
    items.push(`<button type="button" role="menuitem" id="mediaResumeToggle" data-action-scope="detail-modal" data-action="toggleMediaResumeMode">${icon('undo')} Resume</button>`);
    const autoplayOn = localStorage.getItem('autoplayEnabled') === '1';
    items.push(`<button type="button" role="menuitem" id="btnAutoplay" data-action-scope="detail-modal" data-action="toggleAutoplay">${autoplayOn ? icon('pause') : icon('play')} ${tr('detail.modal.autoplay')}</button>`);
  }

  // Common tail: kbd guide / collapse toolbar
  items.push(`<button type="button" role="menuitem" data-action-scope="detail-modal" data-action="toggleKbGuide">? ${tr('keyboard.guide.toggle_btn')}</button>`);
  items.push(`<button type="button" role="menuitem" data-action-scope="detail-modal" data-action="collapseModalToolbar" aria-label="${tr('detail.modal.toolbar_hide')}">« ${tr('detail.modal.toolbar_hide')}</button>`);

  return `<span class="tb-segment tb-overflow-wrap" style="position:relative">
  <button type="button" class="zoom-btn" id="modalToolbarOverflowBtn" data-action-scope="detail-modal" data-action="toggleModalToolbarOverflow" aria-haspopup="menu" aria-expanded="false" aria-controls="modalToolbarOverflow" title="${tr('detail.modal.toolbar_overflow_menu')}" aria-label="${tr('detail.modal.toolbar_overflow_menu')}">…</button>
  <div class="modal-toolbar-overflow" id="modalToolbarOverflow" role="menu">
    ${items.join('\n    ')}
  </div>
</span>`;
}

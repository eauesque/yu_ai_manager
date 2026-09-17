/*
 * toolbar.ts — modal toolbar entry point.
 * Replaces .image-controls and .modal-floating-bar with a unified .modal-toolbar.
 * spec: docs/superpowers/specs/2026-05-04-modal-toolbar-floating-bar-merge-design.md
 */
import type { MediaInfo } from '../media-info';
import { getAppApi } from '../../../shared/browser-apis';
import { renderStillToolbar } from './toolbar-still';
import { renderMediaToolbar } from './toolbar-media';
import { renderOverflowMenu } from './toolbar-overflow';
import { renderToolbarHandle } from './toolbar-collapse';

export interface ToolbarOptions {
  isZipMember?: boolean;
  canSpread?: boolean;
  spreadEnabled?: boolean;
  currentId?: number | null;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function renderModalToolbar(info: MediaInfo, options: ToolbarOptions, data: unknown): string {
  const { escapeHtml } = getAppApi();
  const tr = (k: string) => escapeHtml((window as any).tr(k));
  const isMedia = info.isVideo || info.isAudio || info.isAnimatedImage;
  const klass = isMedia ? 'modal-toolbar is-media' : 'modal-toolbar';
  const inner = isMedia
    ? renderMediaToolbar(info, options)
    : renderStillToolbar(info, options, data);
  const overflow = renderOverflowMenu(info, options);
  return `<div class="${klass}" role="toolbar" aria-label="${tr('detail.modal.toolbar_aria')}" id="modalToolbar">
  ${inner}
  ${overflow}
</div>
${renderToolbarHandle()}`;
}

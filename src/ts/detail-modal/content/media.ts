/**
 * detail-modal/content/media.ts -- Re-export barrel for media modal.
 * Split into media-info.ts (type detection, controls rendering)
 * and media-modal.ts (full modal HTML builder).
 */

export type { MediaInfo, SpreadState, ControlsOptions } from './media-info';
export { getSpreadState, mediaInfo, renderMediaElement, renderBridgeSendClusters } from './media-info';
export { buildModalHtml, buildModalInfoHtml } from './media-modal';

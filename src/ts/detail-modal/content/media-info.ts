/**
 * detail-modal/content/media-info.ts -- Media type detection, spread state,
 * and media element rendering helpers.
 */

import { classifyByPath } from './media-types';
import { getAppApi } from '../../shared/browser-apis';

/** Whether running in Tauri desktop mode */
const _isTauri = typeof (window as any).__TAURI_INTERNALS__ !== 'undefined';

/**
 * For Tauri mode + plain files (not inside ZIP),
 * generate a yufile:// protocol URL for direct filesystem delivery.
 * Completely bypasses HTTP/Python for fastest delivery via Rust direct I/O.
 */
function _yufileUrl(filePath: string): string | null {
  if (!_isTauri) return null;
  // ZIP members (path.zip!inner/file) can only be accessed via API
  if (/\.zip!/i.test(filePath)) return null;
  // Percent-encode the path to build a yufile:// URL
  const encoded = encodeURIComponent(filePath).replace(/%2F/gi, '/').replace(/%5C/gi, '\\');
  return `yufile://localhost/${encoded}`;
}

export interface MediaInfo {
  isVideo: boolean;
  isAudio: boolean;
  isPdf: boolean;
  isAnimatedImage: boolean;
  isStillImage: boolean;
  mediaMime: string;
  mediaUrl: string;
  thumbUrl: string;
  /** Intermediate resolution (1200px) preview URL */
  previewUrl: string;
}

export interface SpreadState {
  enabled: boolean;
  pairId?: number | null;
  currentIdx?: number;
  isRTL?: boolean;
  isCover?: boolean;
}

export function getSpreadState(scopeIds: number[], currentId: number, scope: string): SpreadState {
  if (localStorage.getItem('spreadViewEnabled') !== '1') return { enabled: false };
  if (scope !== 'folder_only' && scope !== 'container_only') return { enabled: false };
  if (!Array.isArray(scopeIds) || scopeIds.length <= 1) return { enabled: false };

  let idx = scopeIds.indexOf(Number(currentId));
  if (idx < 0) return { enabled: false };

  const isRTL = localStorage.getItem('spreadViewRTL') !== '0';
  if (idx === 0) return { enabled: true, pairId: null, isRTL, isCover: true };

  let pairIdx: number;
  if ((idx % 2) === 1) {
    pairIdx = idx + 1;
  } else {
    pairIdx = idx;
    idx = idx - 1;
  }

  if (pairIdx >= scopeIds.length) {
    return { enabled: true, pairId: null, isRTL, isCover: false };
  }

  return { enabled: true, pairId: scopeIds[pairIdx], currentIdx: idx, isRTL, isCover: false };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function mediaInfo(data: any, id: number): MediaInfo {
  const classified = classifyByPath(data.path);
  const isVideo = !!classified.isVideo;
  const isAudio = !!classified.isAudio;
  const isPdf = !!classified.isPdf;
  const backendAnimated = data.is_animated;
  const isAnimatedImage = (backendAnimated === true || (backendAnimated === undefined && !!classified.isAnimatedImage)) && !isVideo && !isAudio;

  // Tauri + video/audio: direct filesystem delivery via yufile:// (HTTP bypass)
  let mediaUrl = getAppApi().apiUrl(`/api/original/${id}`);
  if ((isVideo || isAudio) && data.path) {
    const yuUrl = _yufileUrl(data.path);
    if (yuUrl) mediaUrl = yuUrl;
  }

  return {
    isVideo, isAudio, isPdf, isAnimatedImage,
    isStillImage: !isVideo && !isAudio && !isAnimatedImage && !isPdf,
    mediaMime: classified.mediaMime || '',
    mediaUrl,
    thumbUrl: getAppApi().apiUrl(`/api/thumbnail/${id}`),
    previewUrl: getAppApi().apiUrl(`/api/preview/${id}`),
  };
}

export function renderMediaElement(info: MediaInfo, altLabel?: string): string {
  const { escapeHtml } = getAppApi();
  const imgAlt = altLabel || escapeHtml(window.tr('detail.image_alt'));
  const storedMode = localStorage.getItem('imageDisplayMode') || 'fit';
  let customStyle = '';
  if (storedMode === 'fit-custom') {
    const ch = parseInt(localStorage.getItem('fitCustomHeight') || '600', 10) || 600;
    customStyle = ` style="max-height:${ch}px;height:${ch}px"`;
  }
  if (info.isVideo) {
    // poster=thumbnail for instant preview, preload=auto for ahead-of-time buffering
    return `<video class="modal-image ${escapeHtml(storedMode)}" id="modalImage" controls autoplay playsinline preload="auto" poster="${info.thumbUrl}">
             <source src="${info.mediaUrl}" type="${escapeHtml(info.mediaMime || 'video/webm')}">
             ${escapeHtml(window.tr('detail.video_unsupported'))}
           </video>`;
  }
  if (info.isAudio) {
    // preload=auto for ahead-of-time buffering, show thumbnail as visual
    return `<div class="modal-media-center modal-media-center--audio">
              <img class="modal-audio-poster" src="${info.thumbUrl}" alt="" aria-hidden="true">
              <audio id="modalAudio" class="modal-audio" controls autoplay preload="auto">
                <source src="${info.mediaUrl}" type="${escapeHtml(info.mediaMime || 'audio/mpeg')}">
                ${escapeHtml(window.tr('detail.audio_unsupported'))}
              </audio>
            </div>`;
  }
  if (info.isPdf) {
    return `<div class="modal-media-center modal-media-center--col">
              <img class="modal-image fit modal-pdf-preview" src="${info.thumbUrl}" alt="PDF preview">
              <a href="${info.mediaUrl}" target="_blank" rel="noopener" class="btn-pdf-open">Open PDF</a>
            </div>`;
  }
  if (info.isAnimatedImage) {
    return `<img class="modal-image ${escapeHtml(storedMode)}" id="modalImage" src="${info.mediaUrl}"${customStyle}
              data-animated-image="1" data-animated-src="${info.mediaUrl}" data-static-src="${info.thumbUrl}" data-animated-stopped="0"
              alt="${imgAlt}" onload="this.dataset.loaded='1'" data-action-scope="detail-modal" data-action="detailModalCloseIfNotPanning">`;
  }
  // Progressive loading: thumbnail -> preview (1200px) -> full resolution
  return `<img class="modal-image ${escapeHtml(storedMode)}" id="modalImage" src="${info.thumbUrl}" data-preview-src="${info.previewUrl}" data-full-src="${info.mediaUrl}"${customStyle} alt="${imgAlt}" data-action-scope="detail-modal" data-action="detailModalCloseIfNotPanning" style="filter:blur(2px);transition:filter .3s ease">`;
}

export interface ControlsOptions {
  isZipMember?: boolean;
  canSpread?: boolean;
  spreadEnabled?: boolean;
  currentId?: number;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function renderBridgeSendClusters(info: MediaInfo, data: any): string {
  const { escapeHtml } = getAppApi();
  const th = (k: string, fb: string) => escapeHtml(window.tr(k, fb));

  const hasPrompt = !!(
    data?.positive ||
    data?.negative ||
    data?.novelai_v4?.character_prompts?.length ||
    data?.novelai_v4?.negative_characters?.length
  );
  const hasImage = info.isStillImage || info.isAnimatedImage || info.isVideo;

  let promptCluster = '';
  if (hasPrompt) {
    promptCluster = (
      '<span class="modal-bridge-wrap">'
      + '<button type="button" id="modalBridgePromptTrigger" class="zoom-btn"'
      + ' data-action-scope="detail-modal" data-action="toggleModalBridgeMenu"'
      + ' data-action-arg="modalBridgePromptMenu"'
      + ' title="' + th('detail.modal.send_prompt_title', 'プロンプトのみ送る（画像は変わらず）') + '">'
      + th('detail.modal.send_prompt_label', 'プロンプトを送る') + ' ▾'
      + '</button>'
      + '<div id="modalBridgePromptMenu" class="modal-bridge-menu" style="display:none">'
      + '<label class="modal-bridge-menu-opt" title="' + th('detail.modal.send_omit_seed_title', 'シードを含めずに送ります（毎回ランダム）') + '">'
      + '<input type="checkbox" id="modalBridgeOmitSeedPrompt"> '
      + th('detail.modal.send_omit_seed_label', 'シードを含めない') + '</label>'
      + '<button type="button" data-action-scope="detail-modal" data-action="sendPromptToBridge" data-action-arg="nai">' + th('detail.modal.send_prompt_to_nai', 'NAI Bridge') + '</button>'
      + '<button type="button" data-action-scope="detail-modal" data-action="sendPromptToBridge" data-action-arg="sd">' + th('detail.modal.send_prompt_to_sd', 'SD WebUI') + '</button>'
      + '<button type="button" data-action-scope="detail-modal" data-action="sendPromptToBridge" data-action-arg="comfyui">' + th('detail.modal.send_prompt_to_comfyui', 'ComfyUI') + '</button>'
      + '</div>'
      + '</span>'
    );
  }

  let imageCluster = '';
  if (hasImage) {
    imageCluster = (
      '<span class="modal-bridge-wrap">'
      + '<button type="button" id="modalBridgeImageTrigger" class="zoom-btn"'
      + ' data-action-scope="detail-modal" data-action="toggleModalBridgeMenu"'
      + ' data-action-arg="modalBridgeImageMenu"'
      + ' title="' + th('detail.modal.send_image_title', '画像のみ送る（プロンプトはブリッジ側の前回値のまま）') + '">'
      + th('detail.modal.send_image_label', '画像を送る (img2img)') + ' ▾'
      + '</button>'
      + '<div id="modalBridgeImageMenu" class="modal-bridge-menu" style="display:none">'
      + '<button type="button" data-action-scope="detail-modal" data-action="sendImageToBridge" data-action-arg="nai">' + th('detail.modal.send_image_to_nai', 'NAI Bridge') + '</button>'
      + '<button type="button" data-action-scope="detail-modal" data-action="sendImageToBridge" data-action-arg="sd">' + th('detail.modal.send_image_to_sd', 'SD WebUI') + '</button>'
      + '<button type="button" data-action-scope="detail-modal" data-action="sendImageToBridge" data-action-arg="comfyui">' + th('detail.modal.send_image_to_comfyui', 'ComfyUI') + '</button>'
      + '</div>'
      + '</span>'
    );
  }

  let remixCluster = '';
  if (hasPrompt && hasImage) {
    remixCluster = (
      '<span class="modal-bridge-wrap">'
      + '<button type="button" id="modalBridgeRemixTrigger" class="zoom-btn"'
      + ' data-action-scope="detail-modal" data-action="toggleModalBridgeMenu"'
      + ' data-action-arg="modalBridgeRemixMenu"'
      + ' title="' + th('detail.modal.send_remix_title', 'プロンプトと画像をまとめて送る (リミックス)') + '">'
      + th('detail.modal.send_remix_label', 'リミックス') + ' ▾'
      + '</button>'
      + '<div id="modalBridgeRemixMenu" class="modal-bridge-menu" style="display:none">'
      + '<label class="modal-bridge-menu-opt" title="' + th('detail.modal.send_omit_seed_title', 'シードを含めずに送ります（毎回ランダム）') + '">'
      + '<input type="checkbox" id="modalBridgeOmitSeedRemix"> '
      + th('detail.modal.send_omit_seed_label', 'シードを含めない') + '</label>'
      + '<button type="button" data-action-scope="detail-modal" data-action="sendRemixToBridge" data-action-arg="nai">' + th('detail.modal.send_remix_to_nai', 'NAI Bridge') + '</button>'
      + '<button type="button" data-action-scope="detail-modal" data-action="sendRemixToBridge" data-action-arg="sd">' + th('detail.modal.send_remix_to_sd', 'SD WebUI') + '</button>'
      + '<button type="button" data-action-scope="detail-modal" data-action="sendRemixToBridge" data-action-arg="comfyui">' + th('detail.modal.send_remix_to_comfyui', 'ComfyUI') + '</button>'
      + '</div>'
      + '</span>'
    );
  }

  let workflowCluster = '';
  if (hasImage) {
    workflowCluster = (
      '<button type="button" class="zoom-btn"'
      + ' data-action-scope="detail-modal"'
      + ' data-action="sendWorkflowToComfyUI"'
      + ' title="' + th('detail.modal.send_workflow_comfyui_title', 'ComfyUI にワークフローをキュー投入します') + '">'
      + th('detail.modal.send_workflow_comfyui', 'ワークフローを送る')
      + '</button>'
    );
  }

  if (!promptCluster && !imageCluster && !remixCluster && !workflowCluster) return '';
  return '<span class="ctrl-div"></span>' + promptCluster + imageCluster + remixCluster + workflowCluster;
}

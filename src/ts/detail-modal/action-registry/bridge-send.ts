/**
 * detail-modal/action-registry/bridge-send.ts
 *
 * Send the modal's current image's prompt to NAI/SD/ComfyUI Bridge (txt2img),
 * or send the image itself to NAI/SD img2img.
 *
 * Reuses existing localStorage protocols:
 *   - bridge_send_prompt : { prompt, negative, characters?, source, convert_warning? }
 *   - bridge_send_image  : { base64, source }
 *
 * Payload-building (NAI<->SD convert + NAI v4 character merging) is delegated
 * to shared/bridge-payload.ts so future TS features (e.g., remix menu) reuse it.
 */

import { getAppApi } from '../../shared/browser-apis';
import { saveSendTarget } from '../../shared/bridge-server';
import { bridgeStorage } from '../../shared/bridge-storage';
import {
  buildPromptPayload as sharedBuildPromptPayload,
  isNaiSource,
  NAI_META_SOURCES,
  type BridgeTarget,
  type ImageBridgeTarget,
  type PromptPayload,
  type PromptSource,
} from '../../shared/bridge-payload';
import { showServerSelector } from '../../shared/server-selector';

let _promptInFlight = false;
let _imageInFlight = false;
let _remixInFlight = false;

// Guard-rails for pathological inputs; server-side caps still apply.
const MAX_PAYLOAD_BYTES = 60 * 1024 * 1024;
const MAX_IMAGE_BLOB_BYTES = 50 * 1024 * 1024;

const BRIDGE_URL: Record<BridgeTarget, string> = {
  nai: '/ext/nai-bridge/',
  sd: '/ext/sd-webui/',
  comfyui: '/ext/comfyui-bridge/',
};
const SUPPORTED_BRIDGE_TARGETS: BridgeTarget[] = ['nai', 'sd', 'comfyui'];
const SUPPORTED_IMAGE_TARGETS: ImageBridgeTarget[] = ['nai', 'sd', 'comfyui'];

interface ModalData extends PromptSource {
  id: number;
}

export function buildPromptPayload(
  data: ModalData,
  target: BridgeTarget,
): Promise<PromptPayload> {
  return sharedBuildPromptPayload(data, target, {
    source: 'detail-modal',
    convertFailedMessage: window.tr(
      'detail.modal.send_failed_convert',
      'プロンプト変換に失敗しました。元の文法のまま送信されています',
    ),
  });
}

async function saveOnly(
  payload: object,
  key: 'bridge_send_prompt' | 'bridge_send_image',
): Promise<boolean> {
  const serialized = JSON.stringify(payload);
  if (serialized.length > MAX_PAYLOAD_BYTES) {
    window.showToast?.(
      window.tr('detail.modal.send_failed_quota', 'データが大きすぎて送信できません'),
      true,
    );
    return false;
  }
  const ok = await bridgeStorage.set(key, payload);
  if (!ok) {
    window.showToast?.(
      window.tr('detail.modal.send_failed_quota', 'データが大きすぎて送信できません'),
      true,
    );
  }
  return ok;
}

async function saveAndNavigate(
  url: string,
  payload: object,
  key: 'bridge_send_prompt' | 'bridge_send_image',
): Promise<void> {
  if (await saveOnly(payload, key)) {
    window.location.href = url;
  }
}

function bridgeTypeForSendTarget(target: BridgeTarget): 'comfyui' | 'sd_webui' | null {
  if (target === 'comfyui') return 'comfyui';
  if (target === 'sd') return 'sd_webui';
  return null;
}

async function withServerSelection(
  target: BridgeTarget,
  send: () => Promise<void>,
): Promise<void> {
  const bridgeType = bridgeTypeForSendTarget(target);
  if (!bridgeType) {
    await send();
    return;
  }

  const anchor = (
    document.querySelector('[data-bridge-send]') ??
    document.getElementById('modalBridgePromptTrigger') ??
    document.body
  ) as HTMLElement;

  await new Promise<void>((resolve, reject) => {
    showServerSelector(anchor, bridgeType, async (serverTarget) => {
      try {
        await saveSendTarget(bridgeType, serverTarget);
        await send();
        resolve();
      } catch (e) {
        reject(e);
      }
    }, resolve).catch(reject);
  });
}

async function captureVideoFrame(video: HTMLVideoElement): Promise<Blob | null> {
  const w = video.videoWidth;
  const h = video.videoHeight;
  if (!w || !h) return null;
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  ctx.drawImage(video, 0, 0, w, h);
  return new Promise<Blob | null>((resolve) => {
    canvas.toBlob((b) => resolve(b), 'image/png');
  });
}

async function fetchImageAsBase64(): Promise<string | null> {
  const modalEl = document.getElementById('modalImage');
  if (modalEl && modalEl.tagName === 'VIDEO') {
    const video = modalEl as HTMLVideoElement;
    const blob = await captureVideoFrame(video);
    if (!blob) return null;
    if (blob.size > MAX_IMAGE_BLOB_BYTES) {
      window.showToast?.(
        window.tr('detail.modal.send_failed_quota', 'データが大きすぎて送信できません'),
        true,
      );
      return null;
    }
    const t = video.currentTime;
    const mm = Math.floor(t / 60).toString().padStart(2, '0');
    const ss = Math.floor(t % 60).toString().padStart(2, '0');
    window.showToast?.(
      window.tr('detail.modal.video_frame_captured', '動画フレームを取得しました ({pos})')
        .replace('{pos}', `${mm}:${ss}`),
    );
    const dataUrl = await blobToBase64(blob);
    return dataUrl.replace(/^data:[^;]+;base64,/, '');
  }

  const url = currentModalImageOriginalUrl();
  if (!url) return null;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error('fetch failed: ' + resp.status);
  const blob = await resp.blob();
  if (blob.size > MAX_IMAGE_BLOB_BYTES) {
    window.showToast?.(
      window.tr('detail.modal.send_failed_quota', 'データが大きすぎて送信できません'),
      true,
    );
    return null;
  }
  const dataUrl = await blobToBase64(blob);
  return dataUrl.replace(/^data:[^;]+;base64,/, '');
}

function currentModalData(): ModalData | null {
  const raw = (window as any).__currentDetailModalData;
  if (!raw || typeof raw !== 'object') return null;
  if (typeof raw.id !== 'number') return null;
  return raw as ModalData;
}

function currentModalImageOriginalUrl(): string | null {
  const img = document.getElementById('modalImage') as HTMLImageElement | null;
  if (img && img.dataset.fullSrc) return img.dataset.fullSrc;
  const data = currentModalData();
  if (data?.id != null) return getAppApi().apiUrl(`/api/original/${data.id}`);
  return null;
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

function setTriggerLoading(triggerId: string, loading: boolean, originalLabel: string): void {
  const btn = document.getElementById(triggerId) as HTMLButtonElement | null;
  if (!btn) return;
  btn.disabled = loading;
  btn.textContent = loading ? originalLabel + '…' : originalLabel + ' ▾';
  if (loading) closeBridgeMenus();
}

function closeBridgeMenus(): void {
  document.querySelectorAll('.modal-bridge-menu').forEach((el) => {
    (el as HTMLElement).style.display = 'none';
  });
}

function omitSeedFlag(checkboxId: string): boolean {
  const cb = document.getElementById(checkboxId) as HTMLInputElement | null;
  return !!(cb && cb.checked);
}

function stripSeed<T extends { seed?: number }>(p: T, omit: boolean): T {
  if (!omit) return p;
  const { seed: _drop, ...rest } = p;
  return rest as T;
}

export async function sendPromptToBridge(target: BridgeTarget): Promise<void> {
  if (_promptInFlight || _remixInFlight) return;
  const data = currentModalData();
  if (!data) return;
  _promptInFlight = true;
  const triggerId = 'modalBridgePromptTrigger';
  const label = window.tr('detail.modal.send_prompt_label', 'プロンプトを送る');
  setTriggerLoading(triggerId, true, label);
  try {
    await withServerSelection(target, async () => {
      const payload = stripSeed(await buildPromptPayload(data, target), omitSeedFlag('modalBridgeOmitSeedPrompt'));
      await saveAndNavigate(BRIDGE_URL[target], payload, 'bridge_send_prompt');
    });
  } finally {
    setTriggerLoading(triggerId, false, label);
    _promptInFlight = false;
  }
}

export async function sendImageToBridge(target: ImageBridgeTarget): Promise<void> {
  if (_imageInFlight || _remixInFlight) return;
  _imageInFlight = true;
  const triggerId = 'modalBridgeImageTrigger';
  const label = window.tr('detail.modal.send_image_label', '画像を送る (img2img)');
  setTriggerLoading(triggerId, true, label);
  try {
    await withServerSelection(target, async () => {
      const b64 = await fetchImageAsBase64();
      if (b64 === null) return;
      await saveAndNavigate(BRIDGE_URL[target], { base64: b64, source: 'detail-modal' }, 'bridge_send_image');
    });
  } catch {
    window.showToast?.(
      window.tr('detail.modal.send_failed_image', '画像の取得に失敗しました'), true,
    );
  } finally {
    setTriggerLoading(triggerId, false, label);
    _imageInFlight = false;
  }
}

/**
 * Remix: send prompt AND image to a Bridge in one click. Both localStorage
 * keys (`bridge_send_prompt` + `bridge_send_image`) are populated before
 * navigating, so the destination Bridge picks up both on load.
 */
export async function sendRemixToBridge(target: BridgeTarget): Promise<void> {
  if (_promptInFlight || _imageInFlight || _remixInFlight) return;
  const data = currentModalData();
  if (!data) return;
  _remixInFlight = true;
  const triggerId = 'modalBridgeRemixTrigger';
  const label = window.tr('detail.modal.send_remix_label', 'リミックス');
  setTriggerLoading(triggerId, true, label);
  try {
    await withServerSelection(target, async () => {
      const promptPayload = stripSeed(await buildPromptPayload(data, target), omitSeedFlag('modalBridgeOmitSeedRemix'));
      const b64 = await fetchImageAsBase64();
      if (b64 === null) {
        window.showToast?.(
          window.tr('detail.modal.send_failed_image', '画像の取得に失敗しました'), true,
        );
        return;
      }
      if (!(await saveOnly(promptPayload, 'bridge_send_prompt'))) return;
      if (!(await saveOnly({ base64: b64, source: 'detail-modal' }, 'bridge_send_image'))) {
        // Roll back the prompt key so the destination doesn't see only half.
        await bridgeStorage.remove('bridge_send_prompt');
        return;
      }
      window.location.href = BRIDGE_URL[target];
    });
  } catch {
    window.showToast?.(
      window.tr('detail.modal.send_failed_image', '画像の取得に失敗しました'), true,
    );
  } finally {
    setTriggerLoading(triggerId, false, label);
    _remixInFlight = false;
  }
}

// Expose helpers for Playwright assertions (Task 7 uses page.evaluate against these)
(window as any).__detailModalBridgeSend = {
  buildPromptPayload,
  isNaiSource,
  NAI_META_SOURCES_LIST: Array.from(NAI_META_SOURCES),
  SUPPORTED_BRIDGE_TARGETS,
  SUPPORTED_IMAGE_TARGETS,
  MAX_PAYLOAD_BYTES,
  MAX_IMAGE_BLOB_BYTES,
};

// Toggle for the dropdown menus (used by the UI in Task 5)
(window as any).toggleModalBridgeMenu = function(menuId: string): void {
  const el = document.getElementById(menuId);
  if (!el) return;
  const isOpen = el.style.display !== 'none' && el.style.display !== '';
  document.querySelectorAll('.modal-bridge-menu').forEach((other) => {
    (other as HTMLElement).style.display = 'none';
  });
  if (!isOpen) el.style.display = 'block';
};

// Close bridge menus on outside click (single global listener)
if (!(window as any).__modalBridgeMenuOutsideClickInstalled) {
  (window as any).__modalBridgeMenuOutsideClickInstalled = true;
  document.addEventListener('click', (e) => {
    const t = e.target as HTMLElement | null;
    if (!t || !t.closest('.modal-bridge-wrap')) closeBridgeMenus();
  });
}

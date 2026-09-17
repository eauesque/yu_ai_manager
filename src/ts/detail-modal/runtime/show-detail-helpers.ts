import { runtimeStateApi } from './state';
import { preloadImageById, clearPreloadCache as clearCache } from './show-detail-preload-cache';
import { updateResumeModeButtonLabel } from './controls-media';
import { getAppApi } from '../../shared/browser-apis';
import type { RuntimeState } from './state';

const RESUME_MODE_KEY = 'mediaResumeMode';
const RESUME_POS_PREFIX = 'mediaResumeSec:';

export function applyStoredModalVisibilityState(): void {
  if (localStorage.getItem('modalInfoHidden') === '1') {
    const info = document.querySelector('#modal .modal-info') as HTMLElement | null;
    const btn = document.getElementById('modalInfoToggle');
    if (info) info.style.display = 'none';
    if (btn) btn.textContent = '👁‍🗨';
  }
  // Legacy: controlsBarCollapsed is kept in localStorage for backward compat but has no effect
  // (toolbar is now always visible via .modal-toolbar)
}

export function preloadNeighborImages(s: RuntimeState, isStillImage: boolean): void {
  if (!s.currentResultIds || s.currentResultIds.length === 0 || s.currentModalIndex < 0) return;

  if (isStillImage) {
    // Still image: preload preview images
    if (s.currentModalIndex + 1 < s.currentResultIds.length) preloadImageById(s.currentResultIds[s.currentModalIndex + 1]);
    if (s.currentModalIndex - 1 >= 0) preloadImageById(s.currentResultIds[s.currentModalIndex - 1]);
  } else {
    // Video/audio: warm up server-side cache via Range request
    // (for media inside archives, triggers extraction to temp cache)
    // Not needed when using yufile:// (direct filesystem access)
    _warmupNeighborMedia(s);
  }
}

/**
 * Warm up server-side cache for neighboring media.
 * Fetches the first 2MB, triggering temp cache extraction for archived videos
 * while also storing the moov atom + playback start buffer in the browser cache.
 */
function _warmupNeighborMedia(s: RuntimeState): void {
  const targets: number[] = [];
  for (const offset of [1, -1]) {
    const idx = s.currentModalIndex + offset;
    if (idx >= 0 && idx < s.currentResultIds.length) {
      targets.push(s.currentResultIds[idx]);
    }
  }
  for (const id of targets) {
    // Fetch first 2MB — store moov atom + sufficient playback start buffer in browser cache
    fetch(getAppApi().apiUrl(`/api/original/${id}`), {
      method: 'GET',
      headers: { 'Range': 'bytes=0-2097151' },
    }).catch(() => {});
  }
}

export function clearPreloadCache(): void { clearCache(); }

export function setupViewer(storedMode: string): void {
  const viewer = runtimeStateApi.viewerApi();
  if (!viewer) return;
  viewer.installPanHandlersOnce();
  viewer.resetPan();
  viewer.setImageMode(storedMode);
  viewer.initZoomFromStorage();
  const img = runtimeStateApi.getModalImage();
  if (img) {
    img.addEventListener('load', () => {
      requestAnimationFrame(() => {
        const v = runtimeStateApi.viewerApi();
        if (!v) return;
        v.applyTransforms();
        v.updatePanAvailability();
      });
    }, { once: true });
  }
  requestAnimationFrame(() => runtimeStateApi.viewerApi()?.updatePanAvailability?.());
}

export function setupMediaResume(fileId: number): void {
  const id = Number(fileId);
  if (!Number.isFinite(id)) return;
  const media = (document.getElementById('modalAudio') || document.getElementById('modalImage')) as HTMLMediaElement | null;
  if (!(media instanceof HTMLMediaElement)) {
    updateResumeModeButtonLabel();
    return;
  }
  const mode = localStorage.getItem(RESUME_MODE_KEY) === 'start' ? 'start' : 'resume';
  const storageKey = `${RESUME_POS_PREFIX}${id}`;
  const onLoadedMeta = () => {
    if (mode !== 'resume') return;
    const raw = localStorage.getItem(storageKey);
    const saved = Number(raw);
    if (!Number.isFinite(saved) || saved <= 0.5) return;
    const dur = Number(media.duration);
    const t = Number.isFinite(dur) ? Math.min(saved, Math.max(0, dur - 0.5)) : saved;
    try { media.currentTime = t; } catch (_) { /* ignore */ }
  };
  media.addEventListener('loadedmetadata', onLoadedMeta, { once: true });
  let lastSavedSec = -1;
  media.addEventListener('timeupdate', () => {
    const sec = Math.floor(Number(media.currentTime) || 0);
    if (sec < 0 || sec === lastSavedSec) return;
    lastSavedSec = sec;
    try { localStorage.setItem(storageKey, String(sec)); } catch (_) { /* ignore */ }
  });
  media.addEventListener('ended', () => {
    try { localStorage.removeItem(storageKey); } catch (_) { /* ignore */ }
  });
  updateResumeModeButtonLabel();
}

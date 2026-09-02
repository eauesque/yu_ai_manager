import * as autoplay from './autoplay';
import { setupBackgroundFetch } from './media-background-fetch';
import { getAppApi, getNavApi } from '../../shared/browser-apis';
import { setIconSymbol, icon } from '../../shared/icon';

/**
 * Replace the inline content of an icon-bearing button with the given
 * sprite symbol, regardless of whether the button currently holds an
 * SVG (live page) or stale text content (legacy code path).
 */
function setButtonIcon(btn: HTMLElement, name: string): void {
  const svgEl = btn.querySelector('svg.icon') as SVGSVGElement | null;
  if (svgEl) {
    setIconSymbol(svgEl, name);
  } else {
    btn.replaceChildren();
    btn.insertAdjacentHTML('beforeend', icon(name));
  }
}

const REPEAT_MODE_KEY = 'mediaRepeatMode';
const VOLUME_KEY = 'mediaVolume';
const MUTED_KEY = 'mediaMuted';
const RATE_KEY = 'mediaPlaybackRate';
const RESUME_MODE_KEY = 'mediaResumeMode';

export function getModalMediaElement(): HTMLMediaElement | null {
  const audio = document.getElementById('modalAudio');
  if (audio instanceof HTMLMediaElement) return audio;
  const video = document.getElementById('modalImage');
  if (video instanceof HTMLVideoElement) return video;
  return null;
}

export function getAnimatedModalImage(): HTMLImageElement | null {
  const img = document.getElementById('modalImage');
  if (!(img instanceof HTMLImageElement)) return null;
  return img.dataset.animatedImage === '1' ? img : null;
}

export function updateResumeModeButtonLabel(): void {
  const { tr } = getAppApi();
  const btn = document.getElementById('mediaResumeToggle');
  if (!btn) return;
  const mode = localStorage.getItem(RESUME_MODE_KEY) === 'start' ? 'start' : 'resume';
  setButtonIcon(btn, mode === 'resume' ? 'undo' : 'redo');
  btn.title = mode === 'resume' ? tr('detail.modal.resume_on', 'Resume On') : tr('detail.modal.resume_off', 'Resume Off');
}

export function toggleMediaResumeMode(): void {
  const { tr } = getAppApi();
  const cur = localStorage.getItem(RESUME_MODE_KEY) === 'start' ? 'start' : 'resume';
  const next = cur === 'resume' ? 'start' : 'resume';
  localStorage.setItem(RESUME_MODE_KEY, next);
  updateResumeModeButtonLabel();
  getNavApi().showToast(next === 'resume' ? tr('detail.modal.toast_resume_on', 'Resume: ON') : tr('detail.modal.toast_resume_off', 'Resume: OFF'));
}

export function updateRepeatButtonLabel(): void {
  const { tr } = getAppApi();
  const btn = document.getElementById('modalRepeatBtn');
  if (!btn) return;
  const mode = localStorage.getItem(REPEAT_MODE_KEY) === '1' ? '1' : '0';
  (btn as HTMLElement).style.opacity = mode === '1' ? '1' : '0.45';
  btn.title = mode === '1' ? tr('detail.modal.repeat_on', 'Repeat: ON (R)') : tr('detail.modal.repeat_off', 'Repeat: OFF (R)');
}

export function toggleModalRepeat(): void {
  const { tr } = getAppApi();
  const cur = localStorage.getItem(REPEAT_MODE_KEY) === '1' ? '1' : '0';
  const next = cur === '1' ? '0' : '1';
  localStorage.setItem(REPEAT_MODE_KEY, next);
  updateRepeatButtonLabel();
  getNavApi().showToast(next === '1' ? tr('detail.modal.toast_repeat_on', 'Repeat: ON') : tr('detail.modal.toast_repeat_off', 'Repeat: OFF'));
}

function _setAnimatedStopped(img: HTMLImageElement, stopped: boolean): void {
  const animatedSrc = String(img.dataset.animatedSrc || img.getAttribute('src') || '');
  const staticSrc = String(img.dataset.staticSrc || '');
  img.dataset.animatedStopped = stopped ? '1' : '0';
  if (stopped) { if (staticSrc) img.src = staticSrc; }
  else if (animatedSrc) { img.src = animatedSrc; }
}

export function toggleModalMediaPlayback(): void {
  const media = getModalMediaElement();
  if (media) { if (media.paused) media.play().catch(() => {}); else media.pause(); return; }
  const img = getAnimatedModalImage();
  if (!img) return;
  const stopped = img.dataset.animatedStopped === '1';
  _setAnimatedStopped(img, !stopped);
}

export function rewindModalMedia(): void {
  const media = getModalMediaElement();
  if (media) { media.currentTime = Math.max(0, (Number(media.currentTime) || 0) - 10); return; }
  const img = getAnimatedModalImage();
  if (!img) return;
  const animatedSrc = String(img.dataset.animatedSrc || img.getAttribute('src') || '');
  if (!animatedSrc) return;
  img.dataset.animatedStopped = '0';
  img.src = '';
  requestAnimationFrame(() => { img.src = animatedSrc; });
}

export function forwardModalMedia(): void {
  const media = getModalMediaElement();
  if (!media) return;
  const t = Number(media.currentTime) || 0;
  const duration = Number(media.duration);
  const next = t + 10;
  media.currentTime = Number.isFinite(duration) ? Math.min(duration, next) : next;
}

export function toggleModalMute(): void {
  const media = getModalMediaElement();
  if (!media) return;
  media.muted = !media.muted;
  updateModalAudioUi();
  persistMediaPrefs(media);
}

function formatTime(sec: number): string {
  const s = Math.max(0, Math.floor(Number(sec) || 0));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return String(m).padStart(2, '0') + ':' + String(r).padStart(2, '0');
}

export function updateModalAudioUi(): void {
  const { tr } = getAppApi();
  const media = getModalMediaElement();
  const muteBtn = document.getElementById('modalMuteBtn');
  const vol = document.getElementById('modalVolume') as HTMLInputElement | null;
  if (media && muteBtn) {
    setButtonIcon(muteBtn, media.muted ? 'volume-mute' : 'volume');
    if (media.muted) muteBtn.classList.add('muted');
    else muteBtn.classList.remove('muted');
    muteBtn.title = media.muted ? tr('detail.modal.unmute', 'Unmute (M)') : tr('detail.modal.mute', 'Mute (M)');
  }
  if (media && vol) {
    const v = Math.max(0, Math.min(1, Number(media.volume) || 0));
    if (vol.dataset.dragging !== '1') vol.value = String(v);
  }
}

export function updateModalSeekUi(): void {
  const media = getModalMediaElement();
  const seek = document.getElementById('modalSeek') as HTMLInputElement | null;
  const time = document.getElementById('modalTime');
  if (!media) return;
  const cur = Number(media.currentTime) || 0;
  const dur = Number(media.duration);
  if (seek) {
    const max = 1000;
    const ratio = Number.isFinite(dur) && dur > 0 ? (cur / dur) : 0;
    const val = Math.max(0, Math.min(max, Math.round(ratio * max)));
    if (seek.dataset.dragging !== '1') seek.value = String(val);
  }
  if (time) {
    const durText = Number.isFinite(dur) ? formatTime(dur) : '--:--';
    time.textContent = formatTime(cur) + ' / ' + durText;
  }
  updateModalAudioUi();
}

function applyPersistedMediaPrefs(media: HTMLMediaElement): void {
  try {
    const v = parseFloat(localStorage.getItem(VOLUME_KEY) || '');
    if (!Number.isNaN(v)) media.volume = Math.min(1, Math.max(0, v));
    const m = localStorage.getItem(MUTED_KEY);
    if (m === '1' || m === '0') media.muted = (m === '1');
    const r = parseFloat(localStorage.getItem(RATE_KEY) || '');
    if (!Number.isNaN(r)) media.playbackRate = Math.min(4, Math.max(0.25, r));
  } catch (_) { /* ignore */ }
}

function persistMediaPrefs(media: HTMLMediaElement): void {
  try {
    localStorage.setItem(VOLUME_KEY, String(media.volume));
    localStorage.setItem(MUTED_KEY, media.muted ? '1' : '0');
    localStorage.setItem(RATE_KEY, String(media.playbackRate));
  } catch (_) { /* ignore */ }
}

export function initModalMediaUi(): void {
  const media = getModalMediaElement();
  if (!media) return;
  const seek = document.getElementById('modalSeek') as HTMLInputElement | null;
  const vol = document.getElementById('modalVolume') as HTMLInputElement | null;
  applyPersistedMediaPrefs(media);
  updateModalSeekUi();
  media.addEventListener('timeupdate', updateModalSeekUi);
  media.addEventListener('durationchange', updateModalSeekUi);
  media.addEventListener('volumechange', updateModalAudioUi);
  media.addEventListener('play', updateModalSeekUi);
  media.addEventListener('pause', updateModalSeekUi);
  media.addEventListener('ended', function () {
    const repeatOn = localStorage.getItem(REPEAT_MODE_KEY) === '1';
    if (repeatOn) { try { media.currentTime = 0; const p = media.play(); if (p && typeof p.catch === 'function') p.catch(() => {}); } catch (_) { /* ignore */ } return; }
    autoplay.onMediaEnded?.();
  });
  if (seek) {
    const onSeekInput = function () {
      if (seek.dataset.dragging !== '1') return;
      const dur = Number(media.duration);
      if (!Number.isFinite(dur) || dur <= 0) return;
      const ratio = (Number(seek.value) || 0) / 1000;
      media.currentTime = Math.max(0, Math.min(dur, ratio * dur));
    };
    seek.addEventListener('pointerdown', () => { seek.dataset.dragging = '1'; });
    seek.addEventListener('pointerup', () => { seek.dataset.dragging = '0'; onSeekInput(); });
    seek.addEventListener('input', () => { seek.dataset.dragging = '1'; onSeekInput(); });
    seek.addEventListener('change', () => { seek.dataset.dragging = '0'; onSeekInput(); });
  }
  if (vol) {
    const onVol = function () {
      const v = Math.max(0, Math.min(1, Number(vol.value) || 0));
      media.volume = v;
      if (v === 0) media.muted = true;
      else if (media.muted) media.muted = false;
      persistMediaPrefs(media);
    };
    vol.addEventListener('pointerdown', () => { vol.dataset.dragging = '1'; });
    vol.addEventListener('pointerup', () => { vol.dataset.dragging = '0'; onVol(); });
    vol.addEventListener('input', () => { vol.dataset.dragging = '1'; onVol(); });
    vol.addEventListener('change', () => { vol.dataset.dragging = '0'; onVol(); });
  }

  // After playback starts, fetch the entire file in the background to eliminate seek delays
  setupBackgroundFetch(media);
}

export function cycleModalPlaybackRate(): void {
  const { tr } = getAppApi();
  const media = getModalMediaElement();
  if (!media) return;
  const steps = [1, 1.25, 1.5, 1.75, 2];
  const current = Number(media.playbackRate) || 1;
  let idx = steps.findIndex((n) => Math.abs(n - current) < 0.01);
  if (idx < 0) idx = 0;
  const next = steps[(idx + 1) % steps.length];
  media.playbackRate = next;
  persistMediaPrefs(media);
  getNavApi().showToast(tr('detail.modal.toast_speed', 'Speed: {rate}x').replace('{rate}', String(next)));
}

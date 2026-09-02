import { getModalFocusableElements } from './focus';
import { runtimeStateApi } from '../runtime/state';
import { isFilmstripPinned, setFilmstripPinned } from '../runtime/filmstrip-state';
import { getDetailModalRuntimeHooks } from '../runtime/runtime-hooks';

function getActiveMediaElement(): HTMLMediaElement | null {
  const audio = document.getElementById('modalAudio');
  if (audio instanceof HTMLMediaElement) return audio;
  const video = document.getElementById('modalImage');
  if (video instanceof HTMLVideoElement) return video;
  return null;
}

function getAnimatedModalImage(): HTMLImageElement | null {
  const img = document.getElementById('modalImage');
  if (!(img instanceof HTMLImageElement)) return null;
  return img.dataset.animatedImage === '1' ? img : null;
}

function stepPlaybackRate(media: HTMLMediaElement, delta: number): void {
  const current = Number(media.playbackRate) || 1;
  const next = Math.min(2, Math.max(0.25, Math.round((current + delta) * 100) / 100));
  media.playbackRate = next;
}

function handleMediaShortcut(e: KeyboardEvent): boolean {
  if (e.ctrlKey || e.altKey || e.metaKey) return false;
  const runtimeHooks = getDetailModalRuntimeHooks();
  const media = getActiveMediaElement();
  const key = String(e.key || '').toLowerCase();
  if (media) {
    if (key === 'k' || key === ' ') { e.preventDefault(); if (media.paused) media.play().catch(() => {}); else media.pause(); return true; }
    if (key === 'j') { e.preventDefault(); media.currentTime = Math.max(0, (Number(media.currentTime) || 0) - 10); return true; }
    if (key === 'l') { e.preventDefault(); const duration = Number(media.duration); const next = (Number(media.currentTime) || 0) + 10; media.currentTime = Number.isFinite(duration) ? Math.min(duration, next) : next; return true; }
    if (key === 'm') { e.preventDefault(); media.muted = !media.muted; return true; }
    if (key === 'r') { e.preventDefault(); runtimeHooks.toggleModalRepeat(); return true; }
    if (e.key === '[') { e.preventDefault(); media.volume = Math.max(0, Math.round((media.volume - 0.1) * 100) / 100); return true; }
    if (e.key === ']') { e.preventDefault(); media.volume = Math.min(1, Math.round((media.volume + 0.1) * 100) / 100); return true; }
    if (e.key === '<' || (e.key === ',' && e.shiftKey)) { e.preventDefault(); stepPlaybackRate(media, -0.25); return true; }
    if (e.key === '>' || (e.key === '.' && e.shiftKey)) { e.preventDefault(); stepPlaybackRate(media, +0.25); return true; }
    if (key === '0') { e.preventDefault(); media.currentTime = 0; return true; }
    return false;
  }
  const animated = getAnimatedModalImage();
  if (animated) {
    if (key === 'k' || key === ' ') { e.preventDefault(); runtimeHooks.toggleModalMediaPlayback(); return true; }
    if (key === 'j' || key === '0') { e.preventDefault(); runtimeHooks.rewindModalMedia(); return true; }
    if (key === 'l') { e.preventDefault(); runtimeHooks.toggleModalMediaPlayback(); return true; }
  }
  return false;
}

export interface ModalApi {
  closeModal: () => void;
  navigateModal: (delta: number) => void;
  rewindModalMedia: () => void;
  toggleModalMediaPlayback: () => void;
  toggleModalInfo: () => void;
  toggleModalRepeat: () => void;
  toggleImmersiveMode: () => void;
  toggleSpreadView: () => void;
  toggleSpreadDirection: () => void;
  toggleKbGuide: () => void;
  toggleAutoplay: () => void;
}

export function handleModalKeydown(e: KeyboardEvent, api: ModalApi): boolean {
  const modal = document.getElementById('modal');
  if (!modal?.classList.contains('active')) return false;

  if (e.key === 'Tab') {
    const focusables = getModalFocusableElements();
    if (!focusables.length) { e.preventDefault(); return true; }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const active = document.activeElement;
    if (e.shiftKey) {
      if (active === first || !modal.contains(active)) { e.preventDefault(); last.focus(); }
    } else if (active === last || !modal.contains(active)) { e.preventDefault(); first.focus(); }
    return true;
  }

  // Delegate to the SNS share modal if it is open
  if (e.key === 'Escape') {
    if (document.querySelector('.sns-share-overlay')) return false;
    // Immersive: close info drawer first, then close modal
    const infoDrawer = modal.querySelector('.modal-info.info-visible') as HTMLElement | null;
    if (infoDrawer) { e.preventDefault(); infoDrawer.classList.remove('info-visible'); return true; }
    e.preventDefault(); api.closeModal(); return true;
  }

  const t = e.target as HTMLElement | null;
  const tag = t?.tagName?.toLowerCase() || '';
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
  if ((tag === 'button' || tag === 'a') && (e.key === ' ' || e.key === 'Enter')) return true;

  if (handleMediaShortcut(e)) return true;

  if ((e.key === 'b' || e.key === 'B') && !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey) {
    const scope = runtimeStateApi.getViewerScope();
    if (scope === 'folder_only' || scope === 'container_only') { e.preventDefault(); api.toggleSpreadView(); return true; }
  }
  if ((e.key === 'd' || e.key === 'D') && !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey) {
    if (localStorage.getItem('spreadViewEnabled') === '1') { e.preventDefault(); api.toggleSpreadDirection(); return true; }
  }
  if ((e.key === 'i' || e.key === 'I') && !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); api.toggleModalInfo(); return true; }
  if ((e.key === 'v' || e.key === 'V') && !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); api.toggleImmersiveMode(); return true; }
  if ((e.key === 'h' || e.key === 'H') && !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); api.toggleKbGuide(); return true; }
  if ((e.key === 'p' || e.key === 'P') && !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); api.toggleAutoplay(); return true; }
  if ((e.key === 't' || e.key === 'T') && !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey) {
    // Skip when focus is in form input
    const targetTag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
    if (targetTag !== 'input' && targetTag !== 'textarea') {
      e.preventDefault();
      void import('../content/toolbar/toolbar-collapse').then(m => m.toggleToolbar());
      return true;
    }
  }
  if ((e.key === 'f' || e.key === 'F') && !e.ctrlKey && !e.altKey && !e.metaKey && !e.shiftKey) {
    e.preventDefault();
    const strip = document.getElementById('modalFilmstrip');
    if (strip) {
      const pinned = isFilmstripPinned();
      if (pinned) { strip.classList.remove('filmstrip-visible'); setFilmstripPinned(false); }
      else { strip.classList.add('filmstrip-visible'); setFilmstripPinned(true); }
    }
    return true;
  }

  if (e.key === 'PageUp' || e.key === 'PageDown') {
    const dir = e.key === 'PageUp' ? -1 : +1;
    if (e.ctrlKey) { e.preventDefault(); api.navigateModal(dir); return true; }
    const scroller = document.getElementById('modalContent') || modal;
    if (scroller && scroller.scrollHeight > scroller.clientHeight) {
      e.preventDefault();
      const step = Math.round(scroller.clientHeight * 0.9);
      scroller.scrollBy({ top: dir * step, left: 0, behavior: 'auto' });
      return true;
    }
    return true;
  }

  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    if (e.ctrlKey && !e.altKey && !e.metaKey) { e.preventDefault(); api.navigateModal(e.key === 'ArrowLeft' ? -1 : +1); return true; }
    const media2 = getActiveMediaElement();
    if (media2 && !e.altKey && !e.metaKey) {
      e.preventDefault();
      const delta = (e.key === 'ArrowLeft') ? -5 : +5;
      const duration = Number(media2.duration);
      const next = (Number(media2.currentTime) || 0) + delta;
      media2.currentTime = Number.isFinite(duration) ? Math.min(duration, Math.max(0, next)) : Math.max(0, next);
      return true;
    }
    e.preventDefault();
    api.navigateModal(e.key === 'ArrowLeft' ? -1 : +1);
    return true;
  }

  return true;
}

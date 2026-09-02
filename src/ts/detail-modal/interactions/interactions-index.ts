import { handleModalKeydown } from './modal';
import { handleGridKeydown } from './grid';
import { focusBestInModal } from './focus';

export interface InteractionsApi {
  closeModal: () => void;
  navigateModal: (delta: number) => void;
  rewindModalMedia: () => void;
  updateModalNavButtons: () => void;
  searchByTag: (tag: string) => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  showDetail: (id: number, opts?: any) => void;
  copyToClipboard: (text: string) => Promise<boolean>;
  toggleModalInfo: () => void;
  toggleModalMediaPlayback: () => void;
  toggleModalRepeat: () => void;
  toggleImmersiveMode: () => void;
  toggleSpreadView: () => void;
  toggleSpreadDirection: () => void;
  toggleKbGuide: () => void;
  toggleAutoplay: () => void;
}

let initialized = false;

export function initInteractions(api: InteractionsApi): void {
  if (initialized) return;
  initialized = true;

  document.addEventListener('keydown', (e) => {
    if (handleModalKeydown(e, api)) {
      e.stopPropagation();
      if (typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();
      return;
    }
    handleGridKeydown(e, api);
  }, { capture: true });

  document.addEventListener('focusin', (e) => {
    const card = (e.target as HTMLElement)?.closest?.('.result-card') as HTMLElement | null;
    if (!card) return;
    window.ensureSingleTabstopOnResultCards?.(card);
    window.announceResultCardStatus?.(card);
  });

  const modalEl = document.getElementById('modal');
  if (modalEl) {
    modalEl.addEventListener('click', function (this: HTMLElement, e: MouseEvent) {
      if (e.target === this) api.closeModal();
    });

    // Swipe gesture support for mobile nav (Fix R: visual feedback)
    let touchStartX = 0;
    let touchStartY = 0;
    let swipeActive = false;
    const SWIPE_THRESHOLD = 50;
    const SWIPE_MAX_PX = 100;

    modalEl.addEventListener('touchstart', (e: TouchEvent) => {
      const t = e.touches[0];
      touchStartX = t.clientX;
      touchStartY = t.clientY;
      swipeActive = false;
      const stage = document.getElementById('modalImageStage');
      if (stage) stage.classList.add('swiping');
    }, { passive: true });

    modalEl.addEventListener('touchmove', (e: TouchEvent) => {
      if (!modalEl.classList.contains('active')) return;
      const t = e.touches[0];
      const dx = t.clientX - touchStartX;
      const dy = t.clientY - touchStartY;
      if (!swipeActive && Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy) * 1.2) {
        const startEl = document.elementFromPoint(touchStartX, touchStartY);
        if (startEl?.closest?.('.modal-info') || startEl?.closest?.('.modal-filmstrip-scroll')) return;
        swipeActive = true;
      }
      if (!swipeActive) return;
      const clamped = Math.max(-SWIPE_MAX_PX, Math.min(SWIPE_MAX_PX, dx));
      const stage = document.getElementById('modalImageStage');
      if (stage) stage.style.transform = `translateX(${clamped}px)`;
    }, { passive: true });

    modalEl.addEventListener('touchend', (e: TouchEvent) => {
      const stage = document.getElementById('modalImageStage');
      if (stage) {
        stage.classList.remove('swiping');
        stage.style.transform = '';
      }
      if (!modalEl.classList.contains('active')) return;
      const t = e.changedTouches[0];
      const dx = t.clientX - touchStartX;
      const dy = t.clientY - touchStartY;
      if (Math.abs(dx) > SWIPE_THRESHOLD && Math.abs(dx) > Math.abs(dy) * 1.5) {
        const startEl = document.elementFromPoint(touchStartX, touchStartY);
        if (startEl?.closest?.('.modal-info') || startEl?.closest?.('.modal-filmstrip-scroll')) return;
        api.navigateModal(dx < 0 ? 1 : -1);
      }
      swipeActive = false;
    }, { passive: true });

    let wheelAccum = 0;
    let wheelTimer: ReturnType<typeof setTimeout> | null = null;
    const WHEEL_THRESHOLD = 120;
    document.addEventListener('wheel', function (e) {
      if (!modalEl.classList.contains('active')) return;
      if (localStorage.getItem('modalWheelNav') === '0') return;
      const target = e.target as HTMLElement;
      if (!modalEl.contains(target)) return;
      if (target.closest?.('.modal-info')) return;
      if (target.closest?.('.modal-filmstrip-scroll')) return;
      if (target.tagName === 'INPUT' && (target as HTMLInputElement).type === 'number') return;
      e.preventDefault();
      e.stopPropagation();
      let dy = e.deltaY;
      if (e.deltaMode === 1) dy *= 40;
      else if (e.deltaMode === 2) dy *= 800;
      wheelAccum += dy;
      if (wheelTimer) clearTimeout(wheelTimer);
      wheelTimer = setTimeout(function () { wheelAccum = 0; }, 300);
      if (Math.abs(wheelAccum) >= WHEEL_THRESHOLD) {
        const delta = wheelAccum > 0 ? 1 : -1;
        wheelAccum = 0;
        api.navigateModal(delta);
      }
    }, { passive: false, capture: true });
  }
}

export function interactionsFocusBestInModal(): void {
  focusBestInModal();
}

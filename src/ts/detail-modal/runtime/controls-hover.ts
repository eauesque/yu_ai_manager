/** Filmstrip hover, keyboard guide, controls auto-hide, and modal close. */

import { getAppApi, getBossLockApi, getContainerViewApi, getNavApi, getRuntimeInitApi, getSearchResultsApi } from '../../shared/browser-apis';
import { runtimeStateApi, state } from './state';
import { releaseModalMedia } from './media-cleanup';
import * as helpers from './show-detail-helpers';
import * as autoplay from './autoplay';
import { updateFilmstripScrollButtons } from './nav-controls';
import { resetNavThrottle } from './nav';
import * as uiState from '../../runtime-pre/ui-state';
import { playSound } from '../../sound';
import { toggleImmersiveMode } from './controls';
import {
  initFilmstripPinnedFromStorage,
  isFilmstripPinned,
} from './filmstrip-state';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ui = (): any => uiState;

let _kbGuideAutoHideTimer: ReturnType<typeof setTimeout> | null = null;

export function toggleKbGuide(): void {
  const guide = document.getElementById('modalKeyboardGuide');
  if (!guide) return;
  const isDismissed = sessionStorage.getItem('kbGuideDismissed') === '1';
  if (isDismissed) {
    sessionStorage.removeItem('kbGuideDismissed');
    guide.style.display = 'block';
    guide.classList.remove('kbd-guide-dismissed');
  } else {
    sessionStorage.setItem('kbGuideDismissed', '1');
    guide.style.display = 'none';
    guide.classList.add('kbd-guide-dismissed');
    getNavApi().showToast(getAppApi().tr('keyboard.guide.dismiss_toast', 'H \u30AD\u30FC\u3067\u518D\u8868\u793A\u3067\u304D\u307E\u3059'));
  }
}

function initKbGuideDismiss(): void {
  const btn = document.getElementById('kbGuideDismissBtn');
  if (!btn) return;
  btn.addEventListener('click', () => {
    toggleKbGuide();
  });

  const guide = document.getElementById('modalKeyboardGuide');
  if (guide && sessionStorage.getItem('kbGuideDismissed') !== '1') {
    if (_kbGuideAutoHideTimer) clearTimeout(_kbGuideAutoHideTimer);
    _kbGuideAutoHideTimer = setTimeout(() => {
      if (guide.isConnected && !guide.classList.contains('kbd-guide-dismissed')) {
        sessionStorage.setItem('kbGuideDismissed', '1');
        guide.style.display = 'none';
        guide.classList.add('kbd-guide-dismissed');
      }
      _kbGuideAutoHideTimer = null;
    }, 3000);
  }
}

const TOOLBAR_IDLE_HIDE_MS = 250;
const TOOLBAR_HOVER_ZONE_PX = 140; // bottom strip where toolbar stays visible
const TOOLBAR_LEAVE_HIDE_MS = 1000;

let _filmstripHideTimer: ReturnType<typeof setTimeout> | null = null;
let _controlsHideTimer: ReturnType<typeof setTimeout> | null = null;

function _isCoarsePointer(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(pointer: coarse)').matches;
}

function _showControlsBar(): void {
  const bar = document.getElementById('modalToolbar');
  if (!bar) return;
  bar.classList.add('toolbar-hover');
  bar.classList.remove('toolbar-auto-hidden');
}

function _hideControlsBar(): void {
  const bar = document.getElementById('modalToolbar');
  if (!bar) return;
  bar.classList.remove('toolbar-hover');
  // Don't auto-hide on touch devices: there's no hover, so the toolbar
  // would become unreachable until the user taps an empty area.
  if (_isCoarsePointer()) return;
  bar.classList.add('toolbar-auto-hidden');
}

function _cancelControlsHide(): void {
  if (_controlsHideTimer) {
    clearTimeout(_controlsHideTimer);
    _controlsHideTimer = null;
  }
}

function _scheduleControlsHide(delay = TOOLBAR_IDLE_HIDE_MS): void {
  if (_isCoarsePointer()) return;
  _cancelControlsHide();
  _controlsHideTimer = setTimeout(() => {
    _hideControlsBar();
    _controlsHideTimer = null;
  }, delay);
}

export function initFilmstripHover(): void {
  const container = document.getElementById('modalImageContainer');
  if (!container) return;

  container.addEventListener('dblclick', (e) => {
    const t = e.target as HTMLElement;
    if (t.closest('button, .modal-toolbar, .modal-filmstrip, .modal-kbd-guide, video')) return;
    e.preventDefault();
    toggleImmersiveMode();
  });

  initFilmstripPinnedFromStorage();
  const strip = document.getElementById('modalFilmstrip');
  if (strip && isFilmstripPinned()) {
    strip.classList.add('filmstrip-visible');
  }

  const scrollEl = document.getElementById('modalFilmstripScroll');
  if (scrollEl) {
    scrollEl.addEventListener('scroll', () => {
      updateFilmstripScrollButtons();
    }, { passive: true });
    updateFilmstripScrollButtons();
  }

  // Prevent auto-hide while hovering directly over the toolbar.
  // Also tuck the filmstrip away (unless pinned): the toolbar sits at
  // bottom:24 and the filmstrip-visible state pushes it to bottom:80, so
  // letting the strip stay open while the user is interacting with the
  // toolbar makes the buttons jump upward — chase-the-target UX.
  const bar = document.getElementById('modalToolbar');
  if (bar) {
    bar.addEventListener('mouseenter', () => {
      _cancelControlsHide();
      _showControlsBar();
      if (!isFilmstripPinned()) {
        const s = document.getElementById('modalFilmstrip');
        if (s) s.classList.remove('filmstrip-visible');
        if (_filmstripHideTimer) { clearTimeout(_filmstripHideTimer); _filmstripHideTimer = null; }
      }
    });
    bar.addEventListener('mouseleave', () => {
      _scheduleControlsHide();
    });
    // Keep the bar alive while the user is operating it (clicks, key presses
    // on input/range, focus). Otherwise a slow user could lose the bar
    // mid-action when the idle timer fires. The `input` listener is rAF-
    // throttled so range slider drags don't churn through hundreds of
    // setTimeout swaps per second.
    const keepAlive = () => {
      _showControlsBar();
      _scheduleControlsHide();
    };
    let _inputRaf = 0;
    const keepAliveThrottled = () => {
      if (_inputRaf) return;
      _inputRaf = requestAnimationFrame(() => {
        _inputRaf = 0;
        keepAlive();
      });
    };
    bar.addEventListener('click', keepAlive);
    bar.addEventListener('input', keepAliveThrottled);
    bar.addEventListener('focusin', () => {
      _cancelControlsHide();
      _showControlsBar();
    });
  }

  // Initial visible window after the modal opens, then start the idle timer.
  _showControlsBar();
  _scheduleControlsHide();

  container.addEventListener('mousemove', (e) => {
    const rect = container.getBoundingClientRect();
    const distFromBottom = rect.bottom - e.clientY;
    // Suppress filmstrip activation while the cursor is on the toolbar
    // — otherwise the toolbar bumps from bottom:24 to bottom:80 just as
    // the user reaches a button, forcing them to chase it upward.
    const onToolbar = !!(e.target as HTMLElement | null)?.closest?.('.modal-toolbar');

    // Any movement reveals the bar; if cursor is in the bottom hover zone
    // (or directly on the toolbar), pin it open. Anywhere else, restart the
    // idle timer so it fades after TOOLBAR_IDLE_HIDE_MS.
    _showControlsBar();
    if (onToolbar || distFromBottom <= TOOLBAR_HOVER_ZONE_PX) {
      _cancelControlsHide();
    } else {
      _scheduleControlsHide();
    }

    // --- Filmstrip: show when mouse near bottom (120px) ---
    const filmstrip = document.getElementById('modalFilmstrip');
    if (filmstrip) {
      if (distFromBottom <= 120 && !onToolbar) {
        filmstrip.classList.add('filmstrip-visible');
        if (_filmstripHideTimer) { clearTimeout(_filmstripHideTimer); _filmstripHideTimer = null; }
      } else if (!isFilmstripPinned()) {
        if (!_filmstripHideTimer) {
          _filmstripHideTimer = setTimeout(() => {
            const s = document.getElementById('modalFilmstrip');
            if (s && !isFilmstripPinned()) s.classList.remove('filmstrip-visible');
            _filmstripHideTimer = null;
          }, 800);
        }
      }
    }
  });

  container.addEventListener('mouseleave', () => {
    // Hide controls bar (faster when cursor leaves the modal entirely)
    _scheduleControlsHide(TOOLBAR_LEAVE_HIDE_MS);

    // Hide filmstrip
    if (!isFilmstripPinned()) {
      if (_filmstripHideTimer) clearTimeout(_filmstripHideTimer);
      _filmstripHideTimer = setTimeout(() => {
        const s = document.getElementById('modalFilmstrip');
        if (s && !isFilmstripPinned()) s.classList.remove('filmstrip-visible');
        _filmstripHideTimer = null;
      }, 800);
    }
  });

  // Initialize keyboard guide dismiss button
  initKbGuideDismiss();
}

export function closeModal(): void {
  const bossLockApi = getBossLockApi();
  const searchResultsApi = getSearchResultsApi();
  const containerViewApi = getContainerViewApi();
  const runtimeInitApi = getRuntimeInitApi();
  playSound('modalClose');
  const modal = document.getElementById('modal');
  if (!modal) return;
  // Reset nav throttle so the next modal session starts clean.
  resetNavThrottle();
  autoplay.onModalClose();
  runtimeStateApi.invalidateDetailLoads();
  bossLockApi.stopAllMediaPlayback();
  releaseModalMedia(modal);
  helpers.clearPreloadCache();
  ui()?.closeViewer?.();
  modal.classList.remove('active');
  // Clear current modal data exposed for bridge-send
  (window as any).__currentDetailModalData = null;
  if (searchResultsApi.searchPager && typeof searchResultsApi.searchPager.getHasMore === 'function' && searchResultsApi.searchPager.getHasMore()) {
    if (!document.getElementById('loadMoreSentinel')) {
      searchResultsApi.searchPager.showLoadMoreSentinel();
    }
    searchResultsApi.searchPager.setupScrollObserver();
  }
  // Cancel pending keyboard guide auto-hide timer
  if (_kbGuideAutoHideTimer) { clearTimeout(_kbGuideAutoHideTimer); _kbGuideAutoHideTimer = null; }
  // Reset toolbar auto-hide state so the next session starts clean.
  _cancelControlsHide();
  if (_filmstripHideTimer) { clearTimeout(_filmstripHideTimer); _filmstripHideTimer = null; }
  const tb = document.getElementById('modalToolbar');
  if (tb) { tb.classList.remove('toolbar-auto-hidden', 'toolbar-hover'); }
  runtimeInitApi.hideKeyboardHint();
  const prev = state.modalLastFocusedEl;
  state.modalLastFocusedEl = null;
  // If ContainerView is open, return focus there instead of the original element
  if (containerViewApi.isContainerViewOpen()) {
    requestAnimationFrame(() => { containerViewApi.returnToContainerView(); });
  } else if (prev && prev.isConnected && typeof prev.focus === 'function') {
    requestAnimationFrame(() => { prev.focus(); });
  }
  getAppApi().updateKeyboardGuideVisibility();
  requestAnimationFrame(() => {
    if (!modal.classList.contains('active')) {
      const modalContent = modal.querySelector('.modal-content');
      if (modalContent) modalContent.innerHTML = '';
    }
  });
}

export { _kbGuideAutoHideTimer };

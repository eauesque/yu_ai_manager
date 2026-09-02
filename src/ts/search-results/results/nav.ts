import { getSavedScrollY } from '../../shared/runtime-state/navigation-state';
import { getRuntimeInitApi } from '../../shared/browser-apis';

/**
 * results/nav.ts
 *
 * Scroll-to-top and scroll-to-bottom floating navigation buttons.
 *
 * Converted from runtime-results-nav.js (self-executing IIFE -> exported init function).
 */

interface NavButton extends HTMLButtonElement {
  _mode: 'top' | 'back';
  _scrollingToTop: boolean;
  _backTimer: ReturnType<typeof setTimeout> | undefined;
}

let _navButtonsInitialized = false;

export function initNavButtons(onReady?: () => void): void {
  if (_navButtonsInitialized) return;
  _navButtonsInitialized = true;
  const runtimeInitApi = getRuntimeInitApi();
  // Prevent duplicates: skip if already exists
  if (document.getElementById('scrollToTopBtn')) return;

  // Remove globalScrollTopBtn created earlier by scan-banner/scroll.ts
  const legacy = document.getElementById('globalScrollTopBtn');
  if (legacy) legacy.remove();

  const topBtn = document.createElement('button') as NavButton;
  topBtn.id = 'scrollToTopBtn';
  topBtn.className = 'scroll-nav-btn scroll-nav-top';
  topBtn.title = window.tr('nav.top_title', 'Go to top');
  topBtn.setAttribute('aria-label', window.tr('nav.top_aria', 'Go to top'));
  topBtn.textContent = '\u2191';
  topBtn._mode = 'top';
  topBtn._scrollingToTop = false;
  // Prevent flash before CSS loads: ensure hidden inline too
  topBtn.style.opacity = '0';
  topBtn.style.pointerEvents = 'none';
  topBtn.onclick = () => {
    if (topBtn._mode === 'back') {
      if (getSavedScrollY() != null) runtimeInitApi.scrollBackToPosition();
      topBtn.textContent = '\u2191';
      topBtn.title = window.tr('nav.top_title');
      topBtn._mode = 'top';
      topBtn._scrollingToTop = false;
      const lb = document.getElementById('scrollBackBtn');
      if (lb) (lb as HTMLElement).style.display = 'none';
    } else {
      if (window.scrollY > 200) {
        runtimeInitApi.showScrollBackBtn(window.scrollY);
        topBtn.textContent = '\u21A9';
        topBtn.title = window.tr('nav.back_title');
        topBtn._mode = 'back';
        topBtn._scrollingToTop = true;
        setTimeout(() => {
          topBtn._scrollingToTop = false;
        }, 1500);
        clearTimeout(topBtn._backTimer);
        topBtn._backTimer = setTimeout(() => {
          topBtn.textContent = '\u2191';
          topBtn.title = window.tr('nav.top_title');
          topBtn._mode = 'top';
        }, 15000);
      }
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const bottomBtn = document.createElement('button');
  bottomBtn.id = 'scrollToBottomBtn';
  bottomBtn.className = 'scroll-nav-btn scroll-nav-bottom';
  bottomBtn.title = window.tr('nav.bottom_title', 'Go to bottom');
  bottomBtn.setAttribute('aria-label', window.tr('nav.bottom_aria', 'Go to bottom'));
  bottomBtn.textContent = '\u2193';
  bottomBtn.style.opacity = '0';
  bottomBtn.style.pointerEvents = 'none';
  bottomBtn.onclick = () => window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });

  document.body.appendChild(topBtn);
  document.body.appendChild(bottomBtn);

  let ticking = false;
  window.addEventListener(
    'scroll',
    () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const scrollY = window.scrollY;
        const atBottom = window.innerHeight + scrollY >= document.body.scrollHeight - 100;
        const show = scrollY > 300;

        topBtn.style.opacity = show || topBtn._mode === 'back' ? '1' : '0';
        topBtn.style.pointerEvents = show || topBtn._mode === 'back' ? 'auto' : 'none';
        if (topBtn._mode === 'back' && !topBtn._scrollingToTop && scrollY > 200) {
          topBtn.textContent = '\u2191';
          topBtn.title = window.tr('nav.top_title');
          topBtn._mode = 'top';
          clearTimeout(topBtn._backTimer);
        }

        bottomBtn.style.opacity = show && !atBottom ? '1' : '0';
        bottomBtn.style.pointerEvents = show && !atBottom ? 'auto' : 'none';
        ticking = false;
      });
    },
    { passive: true }
  );

  // Initial check to reflect browser scroll position restoration
  // (CSS alone cannot track already-restored scroll position)
  requestAnimationFrame(() => {
    const scrollY = window.scrollY;
    const atBottom = window.innerHeight + scrollY >= document.body.scrollHeight - 100;
    const show = scrollY > 300;
    topBtn.style.opacity = show ? '1' : '0';
    topBtn.style.pointerEvents = show ? 'auto' : 'none';
    bottomBtn.style.opacity = show && !atBottom ? '1' : '0';
    bottomBtn.style.pointerEvents = show && !atBottom ? 'auto' : 'none';
  });

  // Re-apply labels after i18n dictionary is loaded (async on DOMContentLoaded)
  document.addEventListener('DOMContentLoaded', () => {
    topBtn.title = window.tr('nav.top_title', 'Go to top');
    topBtn.setAttribute('aria-label', window.tr('nav.top_aria', 'Go to top'));
    bottomBtn.title = window.tr('nav.bottom_title', 'Go to bottom');
    bottomBtn.setAttribute('aria-label', window.tr('nav.bottom_aria', 'Go to bottom'));
  });

  onReady?.();
}

export function initNavButtonsOnDemand(onReady?: () => void): void {
  if (_navButtonsInitialized) return;

  const tryInit = (): void => {
    if (_navButtonsInitialized) return;
    if (window.scrollY > 280 || getSavedScrollY() != null) {
      initNavButtons(onReady);
      window.removeEventListener('scroll', onScrollBootstrap);
      document.removeEventListener('keydown', onKeyBootstrap, true);
    }
  };

  const onScrollBootstrap = (): void => {
    tryInit();
  };

  const onKeyBootstrap = (e: KeyboardEvent): void => {
    if (e.key === 'PageDown' || e.key === 'End' || e.key === 'ArrowDown' || e.key === ' ') {
      setTimeout(tryInit, 0);
    }
  };

  window.addEventListener('scroll', onScrollBootstrap, { passive: true });
  document.addEventListener('keydown', onKeyBootstrap, true);
  requestAnimationFrame(tryInit);
}

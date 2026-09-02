/**
 * Scroll restore, header info visibility, and nav search button patch.
 * Split from scroll-header.ts so the heavier search/runtime wiring can load later.
 */

import { getRuntimeInitApi, getRuntimeToolsApi } from '../../shared/browser-apis';
import { searchPager } from '../../search-results/search/pagination';

export function initScrollHeader(): void {
  const runtimeInitApi = getRuntimeInitApi();

  window.addEventListener('beforeunload', function () {
    sessionStorage.setItem('scrollY', String(window.scrollY));
  });

  document.addEventListener('click', function (e: MouseEvent) {
    const a = (e.target as HTMLElement).closest('a[href]') as HTMLAnchorElement | null;
    if (a && !a.target) {
      sessionStorage.setItem('scrollY', String(window.scrollY));
      runtimeInitApi.saveSearchState();
    }
  });

  const navBtn = document.getElementById('navSearchBtn');
  if (navBtn) {
    navBtn.onclick = function () {
      window.openSearchOrModal?.();
    };
  }

  if (localStorage.getItem('headerInfoHidden') === '1') {
    const area = document.getElementById('headerInfoArea');
    const btn = document.getElementById('toggleHeaderInfo');
    if (area) area.style.display = 'none';
    if (btn) btn.textContent = '\ud83d\udc41\u200d\ud83d\udde8';
  }

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      if (searchPager.getHasMore()) {
        searchPager.showLoadMoreSentinel();
        searchPager.setupScrollObserver();
      }
      void getRuntimeToolsApi().loadServerInfo().catch(() => {});
    }
  });
}

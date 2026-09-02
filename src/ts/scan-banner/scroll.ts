/**
 * scan-banner scroll — scroll-to-top button.
 * Converted from static/js/scan-banner/scroll.js
 */

import { getRuntimeInitApi } from '../shared/browser-apis';

export function init(): void {
  const runtimeInitApi = getRuntimeInitApi();
  const btn = document.createElement('button');
  btn.id = 'globalScrollTopBtn';
  const FALLBACK = 'ページの先頭へ';
  const trResult = typeof window.tr === 'function' ? window.tr('scan.banner.scroll_top', FALLBACK) : '';
  const _label = (trResult && trResult !== 'scan.banner.scroll_top') ? trResult : FALLBACK;
  btn.title = _label;
  btn.setAttribute('aria-label', _label);
  document.addEventListener('tr-runtime:ready', () => {
    if (typeof window.tr === 'function') {
      const updated = window.tr('scan.banner.scroll_top', FALLBACK);
      if (updated && updated !== 'scan.banner.scroll_top') {
        btn.title = updated;
        btn.setAttribute('aria-label', updated);
      }
    }
  }, { once: true });
  btn.style.cssText =
    'position:fixed;z-index:910;right:20px;bottom:20px;width:40px;height:40px;border-radius:50%;background:rgba(102,126,234,0.85);color:#fff;border:none;cursor:pointer;font-size:18px;box-shadow:0 2px 8px rgba(0,0,0,0.3);transition:opacity 0.3s;opacity:0;pointer-events:none;display:flex;align-items:center;justify-content:center;';
  btn.textContent = '\u2191';
  btn.onclick = function () {
    runtimeInitApi.showScrollBackBtn(window.scrollY);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  if (!document.getElementById('scrollToTopBtn') && !document.getElementById('globalScrollTopBtn')) {
    document.body.appendChild(btn);
    let ticking = false;
    window.addEventListener('scroll', function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        const show = window.scrollY > 300;
        btn.style.opacity = show ? '1' : '0';
        btn.style.pointerEvents = show ? 'auto' : 'none';
        ticking = false;
      });
    });
  }
}

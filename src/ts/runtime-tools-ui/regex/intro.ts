/**
 * regex/intro.ts — Regex intro overlay + copy-target / copyable-code handlers.
 * Converted from runtime-regex-intro.js
 */

import { copyWithFeedback } from '../tools/copy';
import { activate as focusTrapActivate, deactivate as focusTrapDeactivate } from '../../a11y/focus-trap';
import { getAppApi, getDetailModalApi, getNavApi } from '../../shared/browser-apis';
import { handleJsonDownloadClick } from '../../shared/json-download';

export function openRegexIntro(): void {
  const ov = document.getElementById('regexIntroOverlay');
  if (!ov) return;
  ov.style.display = 'block';
  ov.setAttribute('aria-hidden', 'false');
  const dialog = ov.querySelector('[role="dialog"]') as HTMLElement | null;
  if (dialog) focusTrapActivate(dialog, closeRegexIntro);
}

export function closeRegexIntro(): void {
  const ov = document.getElementById('regexIntroOverlay');
  if (!ov) return;
  ov.style.display = 'none';
  ov.setAttribute('aria-hidden', 'true');
  const dialog = ov.querySelector('[role="dialog"]') as HTMLElement | null;
  if (dialog) focusTrapDeactivate(dialog);
}

export function markCopyableExamples(): void {
  try {
    document.querySelectorAll('#regexCheatPanel .cheat-item code, #regexIntroOverlay code').forEach((c) => {
      c.classList.add('copyable');
      if (!c.querySelector('.ex-badge')) {
        const b = document.createElement('span');
        b.className = 'ex-badge';
        b.setAttribute('aria-hidden', 'true');
        c.appendChild(b);
      }
    });
  } catch (_) {
    // silently ignore
  }
}

/** Document-level click handler for .copy-target and code.copyable elements. */
export function initCopyableClickHandler(): void {
  document.addEventListener(
    'click',
    async (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;

      // Download branch must come before .copy-target to avoid interference.
      const dlTarget = target?.closest?.('[data-download-json-b64]') as HTMLElement | null;
      if (dlTarget) {
        handleJsonDownloadClick(dlTarget);
        return;
      }

      const copyTarget = target?.closest?.('.copy-target') as HTMLElement | null;
      if (copyTarget) {
        const b64 = copyTarget.dataset.copyB64;
        const label = copyTarget.dataset.copyLabel || '';
        if (b64) {
          try {
            const text = decodeURIComponent(escape(atob(b64)));
            await copyWithFeedback(text, copyTarget, label);
          } catch (_err) {
            getNavApi().showToast(getAppApi().tr('toast.copy_failed', 'Copy failed') || 'Copy failed', true);
          }
        }
        return;
      }

      const code = target?.closest?.('code.copyable') as HTMLElement | null;
      if (!code) return;

      if (window.getSelection && String(window.getSelection())?.length > 0) return;

      const text = (code.textContent || '').replace(/\s+$/, '').replace(/^\s+/, '');
      if (!text) return;

      let ok = false;
      try {
        ok = await getDetailModalApi().copyToClipboard(text);
      } catch (_) {
        ok = false;
      }

      const badge =
        (code.querySelector('.ex-badge') as HTMLElement) ||
        (() => {
          const b = document.createElement('span');
          b.className = 'ex-badge';
          b.setAttribute('aria-hidden', 'true');
          code.appendChild(b);
          return b;
        })();

      badge.classList.remove('ok', 'ng', 'show');
      badge.textContent = ok ? '\u2713' : '\u00d7';
      badge.classList.add(ok ? 'ok' : 'ng');
      void badge.offsetWidth; // force reflow
      badge.classList.add('show');

      try {
        getNavApi().showToast(ok ? getAppApi().tr('toast.copy_done') : getAppApi().tr('toast.copy_failed_short'));
      } catch (_) {
        // silently ignore
      }

      setTimeout(() => {
        badge.classList.remove('show');
      }, 900);
    },
    { passive: true } as AddEventListenerOptions,
  );
}

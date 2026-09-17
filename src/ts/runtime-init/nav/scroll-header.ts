/**
 * Scroll restore and header info visibility.
 */

import { getSavedScrollY, setSavedScrollY } from '../../shared/runtime-state/navigation-state';

declare global {
  interface Window {
    toggleHeaderInfo?: () => void;
  }
}

export function showScrollBackBtn(savedY: number): void {
  setSavedScrollY(savedY);
  const btn = document.getElementById('scrollBackBtn') as HTMLElement | null;
  if (btn && savedY > 200) {
    btn.style.display = 'block';
    btn.style.opacity = '1';
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    clearTimeout((btn as any)._hideTimer);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (btn as any)._hideTimer = setTimeout(() => {
      btn.style.opacity = '0';
      setTimeout(() => {
        if (btn.style.opacity === '0') btn.style.display = 'none';
      }, 500);
    }, 15000);
  }
}

export function scrollBackToPosition(): void {
  const savedScrollY = getSavedScrollY();
  if (savedScrollY != null) {
    window.scrollTo({ top: savedScrollY, behavior: 'smooth' });
    setSavedScrollY(null);
  }
  const btn = document.getElementById('scrollBackBtn');
  if (btn) btn.style.display = 'none';
}

export function toggleHeaderInfo(): void {
  const area = document.getElementById('headerInfoArea');
  const btn = document.getElementById('toggleHeaderInfo');
  if (!area) return;
  const hidden = area.style.display !== 'none';
  area.style.display = hidden ? 'none' : '';
  if (btn) btn.textContent = hidden ? '\ud83d\udc41\u200d\ud83d\udde8' : '\ud83d\udc41';
  localStorage.setItem('headerInfoHidden', hidden ? '1' : '0');
}


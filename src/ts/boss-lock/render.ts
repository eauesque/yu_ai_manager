/**
 * boss-lock / render — DOM manipulation for the boss-mode overlay.
 * Shows/hides the overlay, updates the clock, refreshes live market quotes.
 * Converted from static/js/boss-lock/runtime-render.js
 */

import { esc, tr, stopAllMediaPlayback } from './utils';
import { buildBossModeEdition } from './edition';
import { buildOverlayHtml, renderLiveQuoteRows } from './template';

/* ------------------------------------------------------------------ */
/*  Module state                                                       */
/* ------------------------------------------------------------------ */

let bossModeClockTimer: ReturnType<typeof setInterval> | null = null;
let bossModeKeyHandler: ((e: KeyboardEvent) => void) | null   = null;

/* ------------------------------------------------------------------ */
/*  Internal helpers                                                   */
/* ------------------------------------------------------------------ */

/** Update the clock element inside the boss-mode overlay. */
export function updateBossModeClock(): void {
  const ts = document.getElementById('bossModeTimestamp');
  if (!ts) return;
  const now  = new Date();
  const time = now.toLocaleTimeString('en-US', { hour12: false });
  ts.textContent = `Filed ${time}`;
}

/** Fetch live market quotes from the backend and update the overlay sidebar. */
export async function refreshBossModeMarketQuotes(): Promise<void> {
  const holder = document.getElementById('bossModeQuoteList');
  const meta   = document.getElementById('bossModeQuoteMeta');
  if (!holder) return;

  try {
    const res = await fetch('/api/market/quotes', { cache: 'no-store' });
    if (!res.ok) return;
    const data = (await res.json()) as {
      quotes?: { label: string; value: string }[];
      headlines?: string[];
      source?: string;
      updated_at?: number;
    };
    const rows = Array.isArray(data.quotes) ? data.quotes : [];
    if (!rows.length) return;

    holder.innerHTML = renderLiveQuoteRows(rows, esc);

    if (meta) {
      const src      = String(data.source || '').toLowerCase() === 'yahoo' ? 'LIVE' : 'FALLBACK';
      const srcColor = src === 'LIVE' ? 'var(--bm-green)' : 'var(--bm-red)';
      const ts       = Number(data.updated_at || 0);
      const tsText   = ts > 0 ? new Date(ts * 1000).toLocaleTimeString([], { hour12: false }) : '';
      meta.innerHTML = `<span class="bm-q-badge" style="color:${srcColor}">${src}</span>${tsText ? ` &middot; ${esc(tsText)}` : ''}`;
    }

    // Mix real headlines into Top Stories
    const realHeadlines = Array.isArray(data.headlines) ? data.headlines : [];
    if (realHeadlines.length > 0) {
      const storyList = document.querySelector('#bossModeOverlay .stories ul, #bossModeOverlay ul');
      if (storyList) {
        for (const h of realHeadlines) {
          const li = document.createElement('li');
          li.textContent = h;
          // Insert at random position
          const children = storyList.children;
          const pos = Math.floor(Math.random() * (children.length + 1));
          if (pos >= children.length) {
            storyList.appendChild(li);
          } else {
            storyList.insertBefore(li, children[pos]);
          }
        }
      }
    }
  } catch {
    // silently ignore — overlay will keep static quotes
  }
}

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */

/** Show the boss-mode financial-newspaper overlay. */
export function showBossMode(): void {
  let overlay = document.getElementById('bossModeOverlay');
  if (overlay) {
    updateBossModeClock();
    return;
  }

  stopAllMediaPlayback();
  // Fallback map for when i18n is not yet loaded (boss mode must be instant)
  const _fb: Record<string, string> = {
    'boss_mode.top_stories': 'Top Stories',
    'boss_mode.watchlist': 'Watchlist',
    'boss_mode.back': 'Back',
    'boss_mode.esc_hint': 'Press Esc to return',
  };
  const trEsc = (k: string): string => {
    const v = tr(k);
    return esc(v === k && _fb[k] ? _fb[k] : v);
  };
  const ed    = buildBossModeEdition();

  overlay = document.createElement('div');
  overlay.id = 'bossModeOverlay';
  // All visual styles are scoped within the injected <style> block in buildOverlayHtml.
  overlay.innerHTML = buildOverlayHtml(ed, trEsc, esc);
  document.body.appendChild(overlay);

  refreshBossModeMarketQuotes();
  updateBossModeClock();
  bossModeClockTimer = setInterval(updateBossModeClock, 1000);

  bossModeKeyHandler = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') {
      e.preventDefault();
      hideBossMode();
    }
  };
  document.addEventListener('keydown', bossModeKeyHandler, true);
}

/** Remove the boss-mode overlay and clean up timers / listeners. */
export function hideBossMode(): void {
  const overlay = document.getElementById('bossModeOverlay');
  if (overlay) overlay.remove();

  if (bossModeClockTimer) {
    clearInterval(bossModeClockTimer);
    bossModeClockTimer = null;
  }
  if (bossModeKeyHandler) {
    document.removeEventListener('keydown', bossModeKeyHandler, true);
    bossModeKeyHandler = null;
  }
}

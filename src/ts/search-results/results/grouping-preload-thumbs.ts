/**
 * results/grouping-preload-thumbs.ts
 *
 * Thumbnail preloading, progress bar, and batch warmup.
 */

import { getAppApi, getNavApi } from '../../shared/browser-apis';
import { rgState as S, dbg } from './grouping-utils';
import {
  setGroupButtonsDisabled, enableButtonsIfReady, fetchGroupsIndex,
} from './grouping-preload-core';

/* -- Progress bar -- */

function showThumbProgress(done: number, total: number): void {
  const bar = document.getElementById('thumbProgressBar');
  if (!bar) return;
  bar.classList.add('active');
  bar.classList.remove('complete');
  const _t = typeof window.tr === 'function' ? window.tr : function (_k: string, f?: string) { return f || ''; };

  const text = document.getElementById('thumbProgressText');
  if (text) {
    text.textContent = _t('container.preloading_thumbs', 'Generating thumbnails... ({done}/{total})')
      .replace('{done}', String(done))
      .replace('{total}', String(total));
  }
  const details = document.getElementById('thumbProgressDetails');
  if (details) details.textContent = done + ' / ' + total;

  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const fill = document.getElementById('thumbProgressFill');
  if (fill) (fill as HTMLElement).style.width = pct + '%';
  const percent = document.getElementById('thumbProgressPercent');
  if (percent) percent.textContent = pct + '%';
}

function hideThumbProgress(): void {
  const bar = document.getElementById('thumbProgressBar');
  if (!bar) return;
  bar.classList.add('complete');
  setTimeout(function () {
    if (bar.classList.contains('complete')) {
      bar.classList.remove('active', 'complete');
    }
  }, 3000);
}

/* -- Thumbnail preload -- */

function onPreloadComplete(generated: number): void {
  S.preloadAbort = null;
  S.preloadRunning = false;
  S.preloadDone = true;

  try { sessionStorage.setItem('thumbPreloadDone', '1'); } catch (_e) { /* ignore */ }

  enableButtonsIfReady();
  hideThumbProgress();

  if (generated > 0) {
    const _t = typeof window.tr === 'function' ? window.tr : function (_k: string, f?: string) { return f || ''; };
    const msg = _t('container.preload_done', 'Folder / ZIP category view is now ready');
    getNavApi().showToast(msg);
  }
}

function preloadThumbnails(thumbIds: number[], alreadyCached: number): void {
  const handle = { cancelled: false };
  S.preloadAbort = handle;

  let done = alreadyCached || 0;
  const total = thumbIds.length + done;
  showThumbProgress(done, total);

  const queue = thumbIds.slice();
  let running = 0;
  // Browser same-origin connection limit is 6 (HTTP/1.1).
  // Reserve 4 connections for user interaction, limit preloading to 2.
  const MAX_CONCURRENT = 2;

  // Pause preloading during user interaction
  let paused = false;
  const pauseEvents = ['click', 'keydown', 'scroll', 'touchstart'];
  let pauseTimer = 0;
  function onUserActivity(): void {
    paused = true;
    clearTimeout(pauseTimer);
    // Pause preloading for 1.5 seconds after user interaction
    pauseTimer = window.setTimeout(function () {
      paused = false;
      scheduleNext();
    }, 1500);
  }
  for (const evt of pauseEvents) {
    document.addEventListener(evt, onUserActivity, { passive: true, capture: true });
  }
  function cleanupListeners(): void {
    for (const evt of pauseEvents) {
      document.removeEventListener(evt, onUserActivity, true);
    }
    clearTimeout(pauseTimer);
  }

  function scheduleNext(): void {
    if (handle.cancelled) { cleanupListeners(); return; }
    if (paused) return; // Waiting during user interaction
    // Release main thread before issuing next request
    if (typeof requestIdleCallback === 'function') {
      requestIdleCallback(function () { next(); }, { timeout: 200 });
    } else {
      setTimeout(next, 50);
    }
  }

  function next(): void {
    if (handle.cancelled) { cleanupListeners(); return; }
    if (paused) return;
    while (running < MAX_CONCURRENT && queue.length > 0) {
      running++;
      const id = queue.shift()!;
      const img = new Image();
      img.onload = img.onerror = function () {
        if (handle.cancelled) { cleanupListeners(); return; }
        running--;
        done++;
        showThumbProgress(done, total);
        if (done >= total) {
          cleanupListeners();
          onPreloadComplete(thumbIds.length);
        } else {
          scheduleNext();
        }
      };
      img.src = getAppApi().apiUrl('/api/thumbnail/' + id);
    }
  }
  next();
}

export function startBackgroundPreload(): void {
  if (S.preloadStarted) return;
  S.preloadStarted = true;

  // If background-preload.js (or a previous page load) already finished, skip
  try {
    if (sessionStorage.getItem('thumbPreloadDone') === '1') {
      S.preloadDone = true;
      fetchGroupsIndex();
      return;
    }
  } catch (_e) { /* ignore */ }

  S.preloadRunning = true;
  setGroupButtonsDisabled(true);

  // Safety measure: release buttons if preload hasn't completed in 30 seconds
  setTimeout(function () {
    if (!S.preloadDone) {
      dbg('startBackgroundPreload: timeout -- enabling buttons');
      setGroupButtonsDisabled(false);
    }
  }, 30_000);

  // Fetch groups index in parallel with thumbnail preload
  fetchGroupsIndex();

  const url = getAppApi().apiUrl('/api/container-thumb-ids');

  fetch(url)
    .then(function (res) { return res.json(); })
    .then(function (data: { ids?: number[]; cached?: number }) {
      let ids = data && Array.isArray(data.ids) ? data.ids : [];
      const cached = (data && data.cached) || 0;
      if (ids.length === 0) {
        onPreloadComplete(0);
        return;
      }
      // 280K files optimization: cap preload count
      // Sequential requests for thousands of items is impractical. Limit to 200 representative thumbnails.
      const PRELOAD_CAP = 200;
      if (ids.length > PRELOAD_CAP) {
        dbg('startBackgroundPreload: capped from', ids.length, 'to', PRELOAD_CAP);
        ids = ids.slice(0, PRELOAD_CAP);
      }
      // NOTE: Previously we POSTed /api/thumbnails/warmup here and waited
      // up to 10s for the server to bulk-generate per-archive thumbnails.
      // The batch fetcher (`thumbnail-batch.ts`) and the per-archive lock
      // in `serve_thumbnail` now handle this on demand without spawning a
      // separate daemon thread. Keeping warmup added GIL/disk competition
      // and made the GUI stutter every time results were rendered.
      preloadThumbnails(ids, cached);
    })
    .catch(function (err) {
      console.warn('container-thumb-ids fetch failed:', err);
      onPreloadComplete(0);
    });
}


/**
 * background-preload — Cross-page thumbnail preload & groups-index cache.
 * Converted from static/js/shared/background-preload.js
 *
 * Loaded on ALL pages. On the search page the existing
 * runtime-results-grouping.js runs its own preload, so this becomes a no-op.
 */

import { getProgressStack } from './progress-stack';
import { getAppApi } from './browser-apis';

const SS_DONE = 'thumbPreloadDone';
const SS_GROUPS = 'groupsIndex';
const MAX_CONCURRENT = 4;

function _isDone(): boolean {
  try {
    return sessionStorage.getItem(SS_DONE) === '1';
  } catch (_e) {
    return false;
  }
}

function _isSearchPage(): boolean {
  return !!document.getElementById('results');
}

let _barEl: HTMLElement | null = null;

function _ensureProgressBar(): HTMLElement | null {
  if (_barEl) return _barEl;
  const existing = document.getElementById('thumbProgressBar');
  if (existing) {
    _barEl = existing;
    return _barEl;
  }

  const bar = document.createElement('div');
  bar.id = 'thumbProgressBar';
  bar.className = 'scan-progress-bar thumb-progress-bar';
  bar.innerHTML =
    '<div class="scan-progress-content">' +
    '<div class="scan-progress-icon">\uD83D\uDDBC</div>' +
    '<div class="scan-progress-info">' +
    '<div class="scan-progress-text" id="thumbProgressText">Generating thumbnails...</div>' +
    '<div class="scan-progress-details" id="thumbProgressDetails">0 / 0</div>' +
    '</div>' +
    '<div class="scan-progress-track">' +
    '<div class="scan-progress-fill" id="thumbProgressFill" style="width:0%"></div>' +
    '</div>' +
    '<div class="scan-progress-percent" id="thumbProgressPercent">0%</div>' +
    '</div>';

  getProgressStack().appendChild(bar);
  _barEl = bar;
  return _barEl;
}

function _showProgress(done: number, total: number): void {
  _ensureProgressBar();
  const bar = document.getElementById('thumbProgressBar');
  if (!bar) return;
  bar.classList.add('active');
  bar.classList.remove('complete');

  const _t = typeof window.tr === 'function' ? window.tr : function (_k: string, f?: unknown) { return (typeof f === 'string' ? f : '') || ''; };
  const text = document.getElementById('thumbProgressText');
  if (text) {
    text.textContent = String(_t('container.preloading_thumbs', 'Generating thumbnails... ({done}/{total})'))
      .replace('{done}', String(done))
      .replace('{total}', String(total));
  }
  const details = document.getElementById('thumbProgressDetails');
  if (details) details.textContent = done + ' / ' + total;

  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const fill = document.getElementById('thumbProgressFill');
  if (fill) fill.style.width = pct + '%';
  const percent = document.getElementById('thumbProgressPercent');
  if (percent) percent.textContent = pct + '%';
}

function _hideProgress(): void {
  const bar = document.getElementById('thumbProgressBar');
  if (!bar) return;
  bar.classList.add('complete');
  setTimeout(function () {
    if (bar.classList.contains('complete')) {
      bar.classList.remove('active', 'complete');
    }
  }, 3000);
}

function _ensureGroupsIndex(): Promise<void> {
  try {
    if (sessionStorage.getItem(SS_GROUPS)) return Promise.resolve();
  } catch (_e) {
    /* ignore */
  }

  const url = getAppApi().apiUrl('/api/groups-index');

  return fetch(url)
    .then(function (res) {
      return res.json();
    })
    .then(function (data) {
      try {
        sessionStorage.setItem(SS_GROUPS, JSON.stringify(data));
      } catch (_e) {
        /* quota */
      }
    })
    .catch(function (err) {
      console.warn('[bg-preload] groups-index fetch failed:', err);
    });
}

function _preloadImages(thumbIds: string[], alreadyCached: number): void {
  let done = alreadyCached || 0;
  const total = thumbIds.length + done;
  _showProgress(done, total);

  const queue = thumbIds.slice();
  let running = 0;

  function next(): void {
    while (running < MAX_CONCURRENT && queue.length > 0) {
      running++;
      const id = queue.shift()!;
      const img = new Image();
      img.onload = img.onerror = function () {
        running--;
        done++;
        _showProgress(done, total);
        if (done >= total) {
          _markDone();
        } else {
          next();
        }
      };
      img.src = getAppApi().apiUrl('/api/thumbnail/' + id);
    }
  }
  next();
}

function _markDone(): void {
  try {
    sessionStorage.setItem(SS_DONE, '1');
  } catch (_e) {
    /* ignore */
  }
  _hideProgress();
}

function _runPreload(): void {
  const url = getAppApi().apiUrl('/api/container-thumb-ids');

  fetch(url)
    .then(function (res) {
      return res.json();
    })
    .then(function (data) {
      let ids: string[] = data && Array.isArray(data.ids) ? data.ids : [];
      const cached: number = (data && data.cached) || 0;

      if (ids.length === 0) {
        _markDone();
        return;
      }

      // 280K files optimization: limit preloading to 100 items on non-search pages
      const BG_PRELOAD_CAP = 100;
      if (ids.length > BG_PRELOAD_CAP) {
        ids = ids.slice(0, BG_PRELOAD_CAP);
      }

      // NOTE: Warmup POST removed; serve_thumbnail's per-archive lock
      // already coalesces concurrent ZIP opens, and an extra daemon thread
      // here was competing for disk/GIL on every page load.
      _preloadImages(ids, cached);
    })
    .catch(function (err) {
      console.warn('[bg-preload] container-thumb-ids fetch failed:', err);
    });
}

function _init(): void {
  if (_isDone()) return;
  if (_isSearchPage()) return;
  _ensureGroupsIndex();
  _runPreload();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _init);
} else {
  _init();
}

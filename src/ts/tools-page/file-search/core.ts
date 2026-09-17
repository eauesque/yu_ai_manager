/**
 * file-search/core.ts -- File search UI, cache info, and theme toggle.
 * Converted from tools-ui-file-search.js
 *
 * Note: The theme toggle initialization code from the original IIFE
 * is omitted here as it is already handled by the dedicated theme module.
 * Only cache info and file search logic are included.
 */

import { getAppApi, getNavApi } from '../../shared/browser-apis';
import { apiFetch } from '../api';
import * as render from './render';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

interface CacheInfo {
  count: number;
  size_mb: number;
}

export async function loadCacheInfo(): Promise<void> {
  const el = document.getElementById('cacheInfo');
  if (!el) return;
  const ctrl = new AbortController();
  const timeoutId = setTimeout(() => ctrl.abort(), 30000);
  try {
    const res = await fetch('/api/tools/cache-info', { signal: ctrl.signal });
    const data: CacheInfo = await res.json();
    el.textContent =
      '\uD83D\uDCE6 ' +
      data.count.toLocaleString() +
      ' ' +
      _t('tools.files', 'files') +
      ' / ' +
      data.size_mb +
      ' MB';
  } catch {
    el.textContent = ctrl.signal.aborted
      ? _t('tools.cache_scan_timeout', 'Cache scan timed out \u2014 try Clear Cache')
      : _t('tools.fetch_failed', 'Fetch failed');
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function clearThumbnailCache(): Promise<void> {
  if (
    !confirm(
      _t(
        'tools.clear_cache_confirm',
        'Clear all thumbnail caches?\nThey will be regenerated on next display.',
      ),
    )
  )
    return;
  try {
    const res = await apiFetch('/api/tools/clear-cache', { method: 'POST' });
    const data: { cleared: number } = await res.json();
    getNavApi().showToast(
      data.cleared + ' ' + _t('tools.cache_cleared', 'file caches cleared'),
    );
    loadCacheInfo();
  } catch {
    getNavApi().showToast(
      _t('tools.cache_clear_failed', 'Cache clear failed'),
      true,
    );
  }
}

export async function startFaststartPrescan(): Promise<void> {
  const btn = document.getElementById('btnFaststartPrescan') as HTMLButtonElement | null;
  const status = document.getElementById('faststartPrescanStatus');
  if (btn) btn.disabled = true;
  if (status) status.textContent = _t('tools.starting', 'Starting...');
  try {
    const res = await apiFetch('/api/tools/faststart-prescan', { method: 'POST' });
    const data = await res.json();
    if (status) {
      status.textContent = data.started
        ? _t('tools.faststart_running', 'Running in background. Check logs for progress.')
        : _t('tools.already_running', 'Already running.');
    }
  } catch {
    if (status) status.textContent = _t('tools.start_failed', 'Failed to start');
  } finally {
    if (btn) setTimeout(() => { btn.disabled = false; }, 3000);
  }
}

export async function searchFiles(): Promise<void> {
  const q = (document.getElementById('fileSearchQuery') as HTMLInputElement | null)?.value.trim() || '';
  const meta = (document.getElementById('fileSearchMeta') as HTMLSelectElement | null)?.value || 'all';
  const div = document.getElementById('fileSearchResults');
  if (!div) return;

  if (!q && meta === 'all') {
    div.innerHTML = render.renderSearchPrompt();
    return;
  }

  div.innerHTML = render.renderSearching();

  try {
    const params = new URLSearchParams({ q, meta, limit: '200' });
    const res = await fetch(`/api/tools/file-search?${params}`);
    const data = await res.json();
    div.innerHTML = render.renderSearchResults(data);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    div.innerHTML = render.renderSearchError(msg);
  }
}

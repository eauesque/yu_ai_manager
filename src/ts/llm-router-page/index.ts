/**
 * Scheduler-page-style entry. Loads status from /api/llm_router/status,
 * caches it, renders it, wires up event handlers, and re-renders when the
 * i18n dictionary becomes available (so we don't end up frozen on English
 * fallback strings — the same race that bit scheduler v4.64.1).
 */

import {
  tr,
  showToast,
  fetchStatus,
  refreshAll,
  refreshOne,
  disableBackend,
  enableBackend,
  type StatusData,
} from './api';
import { renderAll } from './render';

let _lastStatus: StatusData | null = null;

async function loadAll(): Promise<void> {
  try {
    const env = await fetchStatus();
    if (!env || !env.data) {
      showToast(tr('llm_router.refresh_failed', 'Refresh failed'));
      return;
    }
    _lastStatus = env.data;
    renderAll(env.data);
  } catch (e) {
    console.error('[llm_router] load failed:', e);
    showToast(tr('llm_router.refresh_failed', 'Refresh failed'));
  }
}

function renderFromCache(): void {
  if (_lastStatus) renderAll(_lastStatus);
}

async function handleRefreshAllClick(): Promise<void> {
  const btn = document.getElementById('lrRefreshAllBtn') as HTMLButtonElement | null;
  if (btn) btn.disabled = true;
  try {
    const resp = await refreshAll();
    if (!resp || (resp as any).ok === false) {
      showToast(tr('llm_router.refresh_failed', 'Refresh failed'));
    } else {
      showToast(tr('llm_router.refreshed', 'Refreshed'));
    }
    await loadAll();
  } catch {
    showToast(tr('llm_router.refresh_failed', 'Refresh failed'));
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function handleTableClick(e: Event): Promise<void> {
  const btn = (e.target as HTMLElement).closest<HTMLButtonElement>('[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  const alias = btn.dataset.alias;
  if (!action || !alias) return;

  btn.disabled = true;
  try {
    let resp: any;
    if (action === 'refresh') {
      resp = await refreshOne(alias);
      if (resp?.ok !== false) showToast(tr('llm_router.refreshed', 'Refreshed'));
    } else if (action === 'disable') {
      resp = await disableBackend(alias);
      if (resp?.ok === false) {
        showToast(resp.error || tr('llm_router.toggle_failed', 'Failed'));
      }
    } else if (action === 'enable') {
      resp = await enableBackend(alias);
      if (resp?.ok === false) {
        showToast(resp.error || tr('llm_router.toggle_failed', 'Failed'));
      }
    } else {
      return;
    }
    await loadAll();
  } catch {
    showToast(tr('llm_router.toggle_failed', 'Failed'));
  } finally {
    btn.disabled = false;
  }
}

function init(): void {
  loadAll();
  document.getElementById('lrRefreshAllBtn')?.addEventListener('click', handleRefreshAllClick);
  document.getElementById('lrBackendsTable')?.addEventListener('click', handleTableClick);
  // Re-render when either i18n loader becomes ready:
  //  - core-shared::applyTranslations dispatches i18n:changed for [data-i18n] sweeps
  //  - tr-runtime-lite dispatches tr-runtime:ready for window.tr() lookups
  // Both can fire after initial render, so we listen to both to repaint
  // dynamically-rendered content (button labels, badges, status text).
  document.addEventListener('i18n:changed', renderFromCache);
  document.addEventListener('tr-runtime:ready', renderFromCache);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

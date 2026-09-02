import { runtimeStateApi, state } from './state';
import * as autoplay from './autoplay';
import { releaseModalMedia } from './media-cleanup';
import * as uiState from '../../runtime-pre/ui-state';
import { playSound } from '../../sound';
import { isVirtualScrollActive, vsGetAllIds } from '../../search-results/results/virtual-scroll-bridge';
import { fetchMetadata } from './metadata-prefetch';
import { renderDetailModal } from './show-detail-render';
import { syncDetailViewerScope } from './show-detail-deferred';
import { openModalShell } from './show-detail-shell';
import { getAppApi, getNavApi, getRuntimeToolsApi } from '../../shared/browser-apis';
import { createPagePerfTracker } from '../../shared/page-perf';

const ui = () => uiState;
const _perf = createPagePerfTracker('detail-modal');

function resolveScope(scopeHint?: string): string {
  if (scopeHint === 'container_only' || scopeHint === 'folder_only' || scopeHint === 'result_set') return scopeHint;
  const current = runtimeStateApi.getViewerScope();
  if (current === 'container_only' || current === 'folder_only' || current === 'result_set') return current;
  return 'result_set';
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function resolveScopeIds(scope: string, options: any): number[] {
  if (Array.isArray(options?.scopeIds) && options.scopeIds.length) {
    return options.scopeIds.map((n: number) => Number(n)).filter(Number.isFinite);
  }
  const ids = ui()?.getScopeResultIds?.(scope);
  if (Array.isArray(ids) && ids.length) return ids;
  if (state.currentResultIds.length) return state.currentResultIds.slice();
  // When virtual scroll is active, recover all IDs from the DataStore
  if (isVirtualScrollActive()) {
    const vsIds = vsGetAllIds();
    if (vsIds.length) return vsIds;
  }
  return [];
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function showDetail(id: number, options: any = {}): Promise<void> {
  _perf.mark('show_detail_start');
  const appApi = getAppApi();
  const navApi = getNavApi();
  const runtimeToolsApi = getRuntimeToolsApi();
  const s = state;
  const scope = resolveScope(options.scope);
  const scopeIds = resolveScopeIds(scope, options);
  runtimeStateApi.setScopeIds(scope, scopeIds);
  const priorContainerMeta = runtimeStateApi.getContainerMeta();
  if (scope === 'container_only') runtimeStateApi.setContainerMeta(options.containerMeta || priorContainerMeta || null);
  else runtimeStateApi.setContainerMeta(null);
  s.currentModalIndex = s.currentResultIds.indexOf(id);
  const requestSeq = ++s.detailLoadSeq;
  syncDetailViewerScope(id, s);

  const modalNow = document.getElementById('modal');
  const wasActive = !!(modalNow && modalNow.classList.contains('active'));
  if (!wasActive) {
    s.modalLastFocusedEl = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }

  const modal = document.getElementById('modal')!;
  const content = document.getElementById('modalContent')!;

  try {
    // Metadata cache support — no network wait on cache hit
    _perf.mark('fetch_start');
    const fetchPromise = fetchMetadata(id);
    void fetchPromise.then(() => {
      _perf.mark('fetch_done');
    }).catch(() => {});

    if (!wasActive) {
      playSound('modalOpen');
      await openModalShell(modal, content, id, false, () => {
        _perf.mark('shell_opened');
      });
    } else {
      playSound('navigate');
      releaseModalMedia(modal);
      await openModalShell(modal, content, id, true, () => {
        _perf.mark('shell_opened');
      });
    }

    const data = await fetchPromise;
    if (requestSeq !== s.detailLoadSeq) return;
    renderDetailModal({ data, id, requestSeq, wasActive, modal, content, state: s });
    // Expose current modal data for bridge-send (sendPromptToBridge / sendImageToBridge)
    (window as any).__currentDetailModalData = data;
    _perf.mark('render_done');
    _perf.mark('show_detail_rendered');

    autoplay.onNavigate();
    runtimeToolsApi.updateModalFavButton?.(id);
  } catch (error) {
    content.classList.remove('transitioning');
    console.error('Failed to load detail:', error);
    if (requestSeq !== s.detailLoadSeq) return;
    navApi.showToast(appApi.tr('detail.load_failed'), true);
  }
}

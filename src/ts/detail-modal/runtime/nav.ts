import { runtimeStateApi, state } from './state';
import * as navControls from './nav-controls';
import { showDetail } from './show-detail-load';
import { closeModal } from './controls';
import { getSearchResultsApi } from '../../shared/browser-apis';
import { setScopeResultIds, getScopeResultIds } from '../../runtime-pre/ui-state';
import { isVirtualScrollActive, vsGetAllIds } from '../../search-results/results/virtual-scroll-bridge';

let _groupingPromise: Promise<typeof import('../../search-results/results/grouping')> | null = null;

function _loadGrouping() {
  if (!_groupingPromise) {
    _groupingPromise = import('../../search-results/results/grouping');
  }
  return _groupingPromise;
}

// Recover currentResultIds when the modal was opened via page-return restore
// before showDetail had a chance to wire the scope IDs. Both navigateModal and
// the button-state computation need this so the prev arrow is not stuck on
// `disabled` and clicks are not silently swallowed.
function recoverScopeIdsIfEmpty(): void {
  if (state.currentResultIds && state.currentResultIds.length > 0) return;
  if (isVirtualScrollActive()) {
    const vsIds = vsGetAllIds();
    if (vsIds.length > 0) { state.currentResultIds = vsIds; return; }
  }
  const scopeIds = getScopeResultIds(state.viewerScope || 'result_set');
  if (scopeIds.length > 0) state.currentResultIds = scopeIds;
}

export function updateModalNavButtons(): void {
  const modal = document.getElementById('modal');
  if (!modal?.classList.contains('active')) return;
  recoverScopeIdsIfEmpty();
  navControls.updateButtons(modal, state, runtimeStateApi.modalSearchHasMore());
}

function resolveCurrentModalIndex(): void {
  if (state.currentModalIndex >= 0) return;
  const img = runtimeStateApi.getModalImage();
  const match = (img as HTMLImageElement)?.src?.match(/\/api\/(?:thumbnail|original)\/(\d+)/);
  if (!match) return;
  const id = parseInt(match[1], 10);
  state.currentModalIndex = state.currentResultIds.indexOf(id);
}

// Throttle rapid navigation to prevent connection pool exhaustion.
// Module-global is fine because at most one detail modal is active at a
// time, but it must be reset when the modal closes — otherwise the very
// first key press after re-opening can be silently swallowed.
let lastNavTime = 0;
const NAV_THROTTLE_MS = 120;

export function resetNavThrottle(): void {
  lastNavTime = 0;
}

export function navigateModal(delta: number): void {
  const now = Date.now();
  if (now - lastNavTime < NAV_THROTTLE_MS) return;
  lastNavTime = now;

  const modal = document.getElementById('modal');
  if (!modal?.classList.contains('active')) return;

  recoverScopeIdsIfEmpty();
  if (!state.currentResultIds || state.currentResultIds.length === 0) return;

  resolveCurrentModalIndex();
  if (state.currentModalIndex < 0) return;

  // Spread view: adjust delta for 2-page navigation
  const spreadActive = localStorage.getItem('spreadViewEnabled') === '1'
    && (state.viewerScope === 'folder_only' || state.viewerScope === 'container_only')
    && state.currentResultIds.length > 1;
  if (spreadActive) {
    const ci = state.currentModalIndex;
    if (ci === 0) {
      if (delta > 0) delta = 1;
    } else if (delta < 0) {
      if (ci <= 2) {
        delta = -ci;
      } else {
        delta = -2;
      }
    } else {
      delta = 2;
    }
  }

  const nextIndex = state.currentModalIndex + delta;
  if (localStorage.getItem('debugGroupNav') === '1') {
    console.debug('[GroupNav] navigateModal', 'delta:', delta,
      'scope:', state.viewerScope,
      'idx:', state.currentModalIndex, '->', nextIndex,
      'totalIds:', state.currentResultIds.length,
      'first5:', state.currentResultIds.slice(0, 5));
  }
  if (nextIndex < 0 || nextIndex >= state.currentResultIds.length) {
    // result_set load-more
    if (delta > 0 && runtimeStateApi.modalSearchHasMore() && !runtimeStateApi.modalSearchLoading()) {
      navControls.setLoadMorePending(modal, true);
      runtimeStateApi.modalLoadMore().then(() => {
        navControls.setLoadMorePending(modal, false);
        if (nextIndex < state.currentResultIds.length) {
          const nextId = state.currentResultIds[nextIndex];
          if (typeof nextId === 'number') showDetail(nextId, {
            scope: state.viewerScope,
            scopeIds: state.currentResultIds,
          });
        }
        updateModalNavButtons();
      }).catch(() => {
        navControls.setLoadMorePending(modal, false);
        updateModalNavButtons();
      });
      return;
    }

    // container/folder cross-group navigation
    const scope = runtimeStateApi.getViewerScope();
    if ((scope === 'folder_only' || scope === 'container_only')
        && localStorage.getItem('containerNavContinuous') === '1') {
      void _loadGrouping().then((mod) => {
        const adjIds = mod.getAdjacentGroupIds?.(
          state.currentResultIds, delta
        );
        if (adjIds && adjIds.length > 0) {
          runtimeStateApi.setScopeIds(scope, adjIds);
          setScopeResultIds(scope, adjIds);
          const targetId = delta > 0 ? adjIds[0] : adjIds[adjIds.length - 1];
          showDetail(targetId);
        }
      }).catch(() => {});
    }
    return;
  }

  const nextId = state.currentResultIds[nextIndex];
  if (typeof nextId !== 'number') return;
  showDetail(nextId, {
    scope: state.viewerScope,
    scopeIds: state.currentResultIds,
  });
}

export function searchByTag(tag: string): void {
  closeModal();
  const input = document.getElementById('tagQuery') as HTMLInputElement | null;
  if (input) input.value = tag;
  getSearchResultsApi().runSearch();
}

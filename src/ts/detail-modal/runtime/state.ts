import { detailModalViewer } from '../viewer/exports';
import * as uiState from '../../runtime-pre/ui-state';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export interface RuntimeState {
  currentResultIds: number[];
  currentModalIndex: number;
  detailLoadSeq: number;
  modalLastFocusedEl: HTMLElement | null;
  viewerScope: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  containerMeta: any;
}

export const state: RuntimeState = {
  currentResultIds: [],
  currentModalIndex: -1,
  detailLoadSeq: 0,
  modalLastFocusedEl: null,
  viewerScope: 'result_set',
  containerMeta: null,
};

const ui = () => uiState;

export const runtimeStateApi = {
  getState() { return state; },
  modalSearchHasMore(): boolean {
    if (state.viewerScope !== 'result_set') return false;
    return typeof window.modalDetailHasMore === 'function' ? !!window.modalDetailHasMore() : false;
  },
  modalSearchLoading(): boolean {
    if (state.viewerScope !== 'result_set') return false;
    return typeof window.modalDetailIsLoading === 'function' ? !!window.modalDetailIsLoading() : false;
  },
  modalLoadMore(): Promise<void> {
    if (state.viewerScope !== 'result_set') return Promise.resolve();
    return typeof window.modalDetailLoadMore === 'function' ? window.modalDetailLoadMore() : Promise.resolve();
  },
  viewerApi() { return detailModalViewer || null; },
  getModalImage(): HTMLElement | null {
    return this.viewerApi()?.getModalImage?.() || document.getElementById('modalImage');
  },
  invalidateDetailLoads() { state.detailLoadSeq += 1; },
  setViewerScope(scope: string) { state.viewerScope = scope || 'result_set'; },
  getViewerScope(): string { return state.viewerScope || 'result_set'; },
  setScopeIds(scope: string, ids: number[]) {
    state.currentResultIds = Array.isArray(ids) ? ids.map((n) => Number(n)).filter(Number.isFinite) : [];
    state.currentModalIndex = -1;
    this.setViewerScope(scope);
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  setContainerMeta(meta: any) {
    if (!meta || typeof meta !== 'object') { state.containerMeta = null; return; }
    const representatives = Array.isArray(meta.representatives)
      ? meta.representatives.map((n: number) => Number(n)).filter(Number.isFinite)
      : [];
    state.containerMeta = {
      containerPath: String(meta.containerPath || ''),
      memberCount: Number(meta.memberCount) || 0,
      representatives,
    };
  },
  getContainerMeta() {
    return state.containerMeta ? { ...state.containerMeta, representatives: state.containerMeta.representatives.slice() } : null;
  },
};

export const modalDetailStateApi = {
  setResultIds(ids: number[]) {
    state.currentResultIds = Array.isArray(ids) ? ids.map((n) => Number(n)).filter(Number.isFinite) : [];
    ui()?.setScopeResultIds?.('result_set', state.currentResultIds);
    if (state.currentModalIndex >= state.currentResultIds.length) state.currentModalIndex = -1;
  },
  appendResultIds(ids: number[]) {
    if (!Array.isArray(ids) || !ids.length) return;
    for (const id of ids) {
      const n = Number(id);
      if (Number.isFinite(n)) state.currentResultIds.push(n);
    }
    ui()?.appendScopeResultIds?.('result_set', ids);
  },
  getResultIds() { return state.currentResultIds.slice(); },
  getResultCount() { return state.currentResultIds.length; },
};

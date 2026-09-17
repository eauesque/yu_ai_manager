/* runtime-pre/ui-state.ts — Global UI state (mode, nav context, focus, viewer) */

interface NavContext {
  explorer_path: string;
  library_query: string;
  library_result_ids: number[];
  folder_result_ids: number[];
  container_result_ids: number[];
}

interface FocusState {
  selection_kind: string;
  selection_id: number | null;
}

interface ViewerState {
  open: boolean;
  scope: string;
  cursor: number;
}

interface UiState {
  mode_profile: string;
  nav_context: NavContext;
  focus: FocusState;
  viewer: ViewerState;
}

const state: UiState = {
  mode_profile: 'normal',
  nav_context: {
    explorer_path: '',
    library_query: '',
    library_result_ids: [],
    folder_result_ids: [],
    container_result_ids: [],
  },
  focus: {
    selection_kind: 'none',
    selection_id: null,
  },
  viewer: {
    open: false,
    scope: 'result_set',
    cursor: -1,
  },
};

function _toNumericIds(ids: unknown[]): number[] {
  if (!Array.isArray(ids)) return [];
  return ids.map((n) => Number(n)).filter(Number.isFinite);
}

function _scopeKey(scope: string): keyof NavContext {
  if (scope === 'folder_only') return 'folder_result_ids';
  if (scope === 'container_only') return 'container_result_ids';
  return 'library_result_ids';
}

export function setLibraryQuery(queryValue: string): void {
  state.nav_context.library_query = String(queryValue || '');
}

export function setScopeResultIds(scope: string, ids: unknown[]): void {
  (state.nav_context[_scopeKey(scope)] as number[]) = _toNumericIds(ids);
}

export function appendScopeResultIds(scope: string, ids: unknown[]): void {
  const key = _scopeKey(scope);
  const add = _toNumericIds(ids);
  if (!add.length) return;
  (state.nav_context[key] as number[]) = (state.nav_context[key] as number[]).concat(add);
}

export function getScopeResultIds(scope: string): number[] {
  return (state.nav_context[_scopeKey(scope)] as number[]).slice();
}

export function setFocus(selection_kind: string, selection_id: number | null): void {
  state.focus.selection_kind = selection_kind || 'none';
  state.focus.selection_id = selection_id == null ? null : selection_id;
}

export function openViewer(scope: string, assetId: number): void {
  const ids = getScopeResultIds(scope);
  state.viewer.open = true;
  state.viewer.scope = scope || 'result_set';
  state.viewer.cursor = ids.indexOf(Number(assetId));
}

export function closeViewer(): void {
  state.viewer.open = false;
}

export function getState(): UiState {
  return state;
}

export function getViewerScope(): string {
  return state.viewer.scope;
}

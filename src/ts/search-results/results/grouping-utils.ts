/**
 * results/grouping-utils.ts
 *
 * Shared state, mode management, path utilities, natural sort.
 *
 * Converted from runtime-results-grouping-utils.js (IIFE -> named exports).
 */

/* ---- Interfaces ---- */

export interface GroupsIndex {
  folders: Record<string, unknown>;
  zips: Record<string, unknown>;
  file_count: number;
  max_mtime: number;
}

export interface RgState {
  /** server groups-index */
  serverGroups: GroupsIndex | null;
  serverGroupsFetched: boolean;
  serverGroupsFetching: boolean;
  fetchGroupsPromise: Promise<void> | null;

  /** preload */
  preloadRunning: boolean;
  preloadDone: boolean;
  preloadAbort: { cancelled: boolean } | null;
  preloadStarted: boolean;

  /** rebuild */
  rebuildInProgress: boolean;

  /** ordered group lists (set by applyToCurrentResults) */
  orderedGroups: OrderedGroup[];
  resultOrderGroups: OrderedGroup[];

  /** saved file-tab count for restore on mode switch */
  savedFileCount: string | null;
}

export interface OrderedGroup {
  key: string;
  type: string;
  ids: number[];
  label: string;
  groupPath: string;
}

/* ---- Constants ---- */

const MODE_KEY = 'resultsGroupMode';

export const MODES: Readonly<{ all: 'all'; folder: 'folder'; zip: 'zip' }> = {
  all: 'all',
  folder: 'folder',
  zip: 'zip',
};

/* ---- Shared mutable state ---- */

export const rgState: RgState = {
  /* server groups-index */
  serverGroups: null,
  serverGroupsFetched: false,
  serverGroupsFetching: false,
  fetchGroupsPromise: null,

  /* preload */
  preloadRunning: false,
  preloadDone: false,
  preloadAbort: null,
  preloadStarted: false,

  /* rebuild */
  rebuildInProgress: false,

  /* ordered group lists (set by applyToCurrentResults) */
  orderedGroups: [],
  resultOrderGroups: [],

  /* saved file-tab count for restore on mode switch */
  savedFileCount: null,
};

/* ---- Mode ---- */

export function getMode(): string {
  const v = String(localStorage.getItem(MODE_KEY) || '').trim();
  return v === MODES.folder || v === MODES.zip ? v : MODES.all;
}

export function setMode(mode: string): void {
  const m = mode === MODES.folder || mode === MODES.zip ? mode : MODES.all;
  localStorage.setItem(MODE_KEY, m);
}

/* ---- Debug logging (enable with localStorage.debugGroupNav = '1') ---- */

export function dbg(...args: unknown[]): void {
  if (localStorage.getItem('debugGroupNav') !== '1') return;
  console.debug('[GroupNav]', ...args);
}

/**
 * results/grouping-preload.ts -- Re-export barrel for grouping preload.
 * Split into grouping-preload-core.ts (index fetch, button state, rebuild)
 * and grouping-preload-thumbs.ts (thumbnail preloading, warmup).
 */

export {
  setGroupButtonsDisabled, enableButtonsIfReady,
  fetchGroupsIndex, rebuildGroups,
} from './grouping-preload-core';
export { startBackgroundPreload } from './grouping-preload-thumbs';

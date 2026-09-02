/**
 * ai-analysis/servers.ts -- Barrel re-export for AI Server Registry.
 * Split into server-types.ts, server-list.ts, server-dialog.ts.
 */

export type { ServerEntry, DiscoveredCandidate } from './server-types';
export {
  ENGINE_LABELS, ENGINE_ICONS,
  getServers, setServers, getHasServers, getDiscoveredCandidates, setDiscoveredCandidates,
  showToast, errMsg,
  renderBatchServerCheckboxes, getSelectedBatchServerIds,
} from './server-types';

export {
  loadAiServers,
  aisActivate, aisTest, aisRemove, aisToggleEnabled,
  aisMigrateFromLegacy, aisRegisterDiscovered, aisTestDiscovered, aisMatchDiscovered, aisUnmatchDiscovered, aisIgnoreDiscovered, aisUnignoreDiscovered,
} from './server-list';

export {
  aisShowAddDialog, aisShowEditDialog,
  aisOnTypeChange, aisSaveDialog, aisRefreshModels,
} from './server-dialog';

/**
 * secrets-tab-op.ts -- Re-export barrel for 1Password CLI integration UI.
 * Split into secrets-tab-op-status.ts (status/link/unlink)
 * and secrets-tab-op-wizard.ts (bulk push wizard).
 */

export { _setRefreshOverview, loadOpStatus, showLinkOpDialog, unlinkOpSecret } from './secrets-tab-op-status';
export { showPushToOpWizard, _setRefreshOverview as _setRefreshOverviewWizard } from './secrets-tab-op-wizard';

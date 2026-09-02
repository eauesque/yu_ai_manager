import {
  exportSecrets,
  importSecrets,
  migrateToKeychain,
  showLinkOpDialog,
  unlinkOpSecret,
  showPushToOpWizard,
  unlinkBwSecret,
  showPushToBwWizard,
} from '../secrets-tab';

export function createSettingsSecretsBridgeSection() {
  return {
    exportSecrets,
    importSecrets,
    migrateToKeychain,
    showLinkOpDialog,
    unlinkOpSecret,
    showPushToOpWizard,
    unlinkBwSecret,
    showPushToBwWizard,
  };
}

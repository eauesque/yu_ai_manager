import { createSettingsCoreBridgeSection } from './core';
import { createSettingsProfilesBridgeSection } from './profiles';
import { createSettingsContentBridgeSection } from './content';
import { createSettingsUiBridgeSection } from './ui';
import { createSettingsSecretsBridgeSection } from './secrets';

export function createSettingsPageBridgeApi() {
  return {
    ...createSettingsCoreBridgeSection(),
    ...createSettingsProfilesBridgeSection(),
    ...createSettingsContentBridgeSection(),
    ...createSettingsUiBridgeSection(),
    ...createSettingsSecretsBridgeSection(),
  };
}

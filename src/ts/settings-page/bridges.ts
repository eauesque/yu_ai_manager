import { installWindowApi } from '../shared/window-api';
import { createSettingsPageBridgeApi } from './bridges/index';

/* eslint-disable @typescript-eslint/no-explicit-any */
export function installSettingsPageWindowBridges(): void {
  const api = createSettingsPageBridgeApi();
  installWindowApi('settingsPageApi', api);
}
/* eslint-enable @typescript-eslint/no-explicit-any */

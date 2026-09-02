/**
 * extensions-config-modal.ts -- Re-export barrel for extension config modal.
 * Split into extensions-config-fields.ts (form builder/collector)
 * and extensions-config-dialog.ts (modal overlay).
 */

export type { ConfigField, ConfigSchema } from './extensions-config-fields';
export { openConfigModal } from './extensions-config-dialog';

/**
 * BridgeLastParams — localStorage-based parameter save/restore for Bridge UIs.
 *
 * Each bridge provides a config with its own storageKey, getParams, and setParams.
 * Text parameters only — binary data (img2img, vibe images) are excluded.
 */

export interface BridgeLastParamsConfig {
  /** localStorage key, e.g. "sdwb_last_params" */
  storageKey: string;
  /** Collect current UI values as key-value pairs */
  getParams: () => Record<string, string>;
  /** Write saved key-value pairs back to the UI */
  setParams: (p: Record<string, string>) => void;
}

export const BridgeLastParams = {
  /** Save current UI parameters to localStorage. */
  save(config: BridgeLastParamsConfig): void {
    try {
      const params = config.getParams();
      localStorage.setItem(config.storageKey, JSON.stringify(params));
    } catch (e) {
      console.warn('[BridgeLastParams] save failed:', e);
    }
  },

  /** Restore parameters from localStorage. Returns true if data existed. */
  restore(config: BridgeLastParamsConfig): boolean {
    try {
      const raw = localStorage.getItem(config.storageKey);
      if (!raw) return false;
      const params: Record<string, string> = JSON.parse(raw);
      config.setParams(params);
      return true;
    } catch (e) {
      console.warn('[BridgeLastParams] restore failed:', e);
      return false;
    }
  },

  /** Check whether saved data exists for the given key. */
  hasSaved(storageKey: string): boolean {
    try {
      return localStorage.getItem(storageKey) !== null;
    } catch (_e) {
      return false;
    }
  },
};

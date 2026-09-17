/**
 * Bridge module index — re-exports all bridge utilities.
 */
export { BridgeSed } from './sed';
export { BridgeWildcardCache } from './wildcard-cache';
export { BridgeWildcardBrowser } from './wildcard-browser';
export { BridgeAutocomplete } from './autocomplete';
export { BridgeResultPanel, BridgeGenThumbnails } from './result-panel';
export { BridgePromptLibrary } from './prompt-library';
export { BridgeLastParams } from './last-params';
export { BridgeQualityPresets } from './quality-presets';
export { BridgeResolutionPresets } from './resolution-presets-ui';
export { BridgeAspectLock } from './aspect-lock-ui';
export { setupSyntaxBanner } from './syntax-banner';
export { openFullsize as bridgeOpenFullsize } from './fullsize-overlay';
export { BridgeFanOut } from './fan-out';
export { attachServerManagement as BridgeServerManagement } from './server-management-panel';
export { BridgeDedup } from './dedup';

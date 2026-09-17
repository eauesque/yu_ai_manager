/**
 * Bridge App — entry point that bundles all bridge utilities
 * and exposes them as window globals for inline template scripts.
 */
// Side-effect import: registers window.bridgeStorage (IDB-backed payload store)
import '../shared/bridge-storage';
import {
  BridgeSed,
  BridgeDedup,
  BridgeWildcardCache,
  BridgeWildcardBrowser,
  BridgeAutocomplete,
  BridgeResultPanel,
  BridgeGenThumbnails,
  BridgePromptLibrary,
  BridgeLastParams,
  BridgeQualityPresets,
  BridgeResolutionPresets,
  BridgeAspectLock,
  BridgeFanOut,
  BridgeServerManagement,
  setupSyntaxBanner,
  bridgeOpenFullsize,
} from '../bridge';

// Expose as window globals for template inline scripts
/* eslint-disable @typescript-eslint/no-explicit-any */
(window as any).BridgeSed = BridgeSed;
(window as any).BridgeDedup = BridgeDedup;
(window as any).BridgeWildcardCache = BridgeWildcardCache;
(window as any).BridgeWildcardBrowser = BridgeWildcardBrowser;
(window as any).BridgeAutocomplete = BridgeAutocomplete;
(window as any).BridgeResultPanel = BridgeResultPanel;
(window as any).BridgeGenThumbnails = BridgeGenThumbnails;
(window as any).BridgePromptLibrary = BridgePromptLibrary;
(window as any).BridgeLastParams = BridgeLastParams;
(window as any).BridgeQualityPresets = BridgeQualityPresets;
(window as any).BridgeResolutionPresets = BridgeResolutionPresets;
(window as any).BridgeAspectLock = BridgeAspectLock;
(window as any).BridgeFanOut = BridgeFanOut;
(window as any).BridgeServerManagement = BridgeServerManagement;
(window as any).setupSyntaxBanner = setupSyntaxBanner;
(window as any).bridgeOpenFullsize = bridgeOpenFullsize;

// Initialize Servers panel after DOM is ready (module scripts run after DOM parse)
if (typeof document !== 'undefined') {
  const _initServersPanel = () => {
    const el = document.getElementById('bridge-server-management') as HTMLElement | null;
    if (el) BridgeServerManagement(el);
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initServersPanel);
  } else {
    _initServersPanel();
  }
}

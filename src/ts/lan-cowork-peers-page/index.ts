/**
 * lan-cowork-peers-page/index.ts
 * Entry point for the peer management page (/ext/lan_cowork/peers).
 * All init functions guard on element existence — safe to include in the
 * shared lan-cowork-app.js bundle even when not on this page.
 */

import { initRequestsPanel } from './requests-panel';
import { initTokensPanel } from './tokens-panel';
import { initPairModal, openApproveFlow } from './pair-modal';
import { initPeersPageSSE } from './sse';
import { initFleetSettingsPanel } from './fleet-settings';
import { initConsentBanner } from './consent-banner';
import { initFleetPermissionsPanel } from './fleet-permissions-panel';
import { initMyPermissionsPanel } from './fleet-my-permissions-panel';

function init(): void {
  // Only activate when the peers management page elements are present
  const section = document.getElementById('lcPeersRequestsSection');
  if (!section) return;

  initPairModal();

  initRequestsPanel({
    onApproved: (requestId, pin, peerId) => {
      openApproveFlow(requestId, pin, peerId);
    },
  });

  initTokensPanel();
  initFleetSettingsPanel();
  initPeersPageSSE();
  initConsentBanner();
  initFleetPermissionsPanel();
  initMyPermissionsPanel();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

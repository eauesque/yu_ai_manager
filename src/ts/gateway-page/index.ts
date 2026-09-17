/**
 * index.ts -- gateway page entry point
 */
import { initBackendsPanel } from './backends-panel';
import { initHealthPanel } from './health-panel';
import { initScanPanel } from './scan-panel';
import { initAgentmemoryPanel } from './agentmemory-panel';
import { initHeadroomPanel } from './headroom-panel';

function init(): void {
  initBackendsPanel();
  initScanPanel();
  initHealthPanel();
  initHeadroomPanel();
  initAgentmemoryPanel();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

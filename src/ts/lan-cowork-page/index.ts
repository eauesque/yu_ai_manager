import { initPeersPanel } from './peers-panel';
import { initImportPanel } from './import-panel';
import { fetchLocalStatus } from './api';

async function maybeShowFleetLink(): Promise<void> {
  try {
    const res = await fetchLocalStatus();
    if (res.ok && res.peer?.roles?.includes('chief')) {
      const nav = document.querySelector('.lc-subnav');
      if (!nav || nav.querySelector('#lcFleetAdminLink')) return;
      const a = document.createElement('a');
      a.id = 'lcFleetAdminLink';
      a.href = '/ext/lan_cowork/fleet/ui';
      a.className = 'lc-subnav-link';
      a.setAttribute('data-i18n', 'lan_cowork.nav.fleet_admin');
      a.textContent = (window as any).tr?.('lan_cowork.nav.fleet_admin', 'Fleet 管理') ?? 'Fleet 管理';
      nav.appendChild(a);
    }
  } catch {
    // non-chief or service unavailable — silently skip
  }
}

function init(): void {
  initImportPanel(); // registers lc:peers-updated listener first
  initPeersPanel();  // triggers initial discover, fires lc:peers-updated
  maybeShowFleetLink();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

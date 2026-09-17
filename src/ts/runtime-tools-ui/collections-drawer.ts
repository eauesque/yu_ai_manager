/**
 * collections-drawer.ts -- Mobile drawer overlay for the collections
 * sidebar. Clones sidebar content into a slide-in drawer panel on
 * small screens. Split from collections-sidebar.ts.
 */

import { getSidebar } from './collections-state';
import { getRuntimeToolsUiHooks } from './hooks';

/**
 * Set up the mobile FAB + drawer. Clones sidebar content into the
 * drawer on each open so it always reflects the latest state.
 * Noop if required DOM elements are absent.
 */
export function initMobileDrawer(): void {
  const fab = document.getElementById('csMobileFab');
  const drawer = document.getElementById('csDrawer');
  const backdrop = document.getElementById('csDrawerBackdrop');
  const body = document.getElementById('csDrawerBody');
  const sidebar = getSidebar();
  if (!fab || !drawer || !backdrop || !body || !sidebar) return;

  function openDrawer(): void {
    // Clone sidebar content into drawer on each open (reflects latest state)
    body!.innerHTML = '';
    const clone = sidebar!.cloneNode(true) as HTMLElement;
    clone.style.display = 'flex';
    clone.style.position = 'static';
    clone.style.width = '100%';
    clone.style.minWidth = '0';
    clone.style.maxHeight = 'none';
    clone.style.boxShadow = 'none';
    clone.style.borderRadius = '0';
    // Remove header collapse button in drawer
    const hdr = clone.querySelector('.cs-header');
    if (hdr) (hdr as HTMLElement).style.display = 'none';
    body!.appendChild(clone);
    // Re-attach click handlers on cloned items
    clone.querySelectorAll('.cs-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        const tabName = (tab as HTMLElement).dataset.tab || 'collections';
        clone.querySelectorAll('.cs-tab').forEach((t) => {
          const isActive = (t as HTMLElement).dataset.tab === tabName;
          t.classList.toggle('active', isActive);
        });
        clone.querySelectorAll('.cs-tab-panel').forEach((p) => {
          const panelId = 'csPanel' + tabName.charAt(0).toUpperCase() + tabName.slice(1);
          p.classList.toggle('active', p.id === panelId);
        });
        if (tabName === 'folders') getRuntimeToolsUiHooks().loadFolderTree();
      });
    });
    // Clicking a collection item in drawer also triggers main sidebar & closes
    clone.querySelectorAll('.cs-item').forEach((item) => {
      item.addEventListener('click', () => {
        closeDrawer();
      });
    });
    drawer!.classList.add('open');
    backdrop!.classList.add('open');
  }

  function closeDrawer(): void {
    drawer!.classList.remove('open');
    backdrop!.classList.remove('open');
  }

  fab.addEventListener('click', openDrawer);
  backdrop.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Escape' && drawer.classList.contains('open')) {
      closeDrawer();
    }
  });
}

/**
 * modal-tabs.ts — Tab switching for the detail modal info panel.
 *
 * Provides "Info" and "AI Analysis" tabs in `.modal-info`.
 * Tab state persists via localStorage('modalActiveTab').
 */

import { safeViewTransition } from '../../shared/view-transition';

const STORAGE_KEY = 'modalActiveTab';
const DEFAULT_TAB = 'info';

type TabCallback = (tab: string) => void;
let _tabListeners: TabCallback[] = [];

/**
 * Register a one-shot listener that fires the next time a tab is activated.
 * The listener is automatically removed after it fires once.
 */
export function onTabActivated(cb: TabCallback): void {
  _tabListeners.push(cb);
}

function _switchTo(tab: string): void {
  // Target .modal-info directly without depending on DOM hierarchy
  const container = document.querySelector('.modal-info');
  if (!container) return;

  container.querySelectorAll<HTMLElement>('.mi-tab').forEach(btn => {
    const isActive = btn.dataset.tab === tab;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', String(isActive));
  });

  container.querySelectorAll<HTMLElement>('.mi-tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === `miPanel-${tab}`);
  });

  localStorage.setItem(STORAGE_KEY, tab);
}

export function switchModalTab(tab: string): void {
  safeViewTransition(() => _switchTo(tab));
  // Fire and clear one-shot tab listeners
  if (_tabListeners.length) {
    const cbs = _tabListeners;
    _tabListeners = [];
    for (const cb of cbs) cb(tab);
  }
}

export function initModalTabs(): void {
  const bar = document.querySelector('.mi-tabs');
  if (!bar) return;

  bar.addEventListener('click', (e) => {
    const btn = (e.target as HTMLElement).closest<HTMLElement>('.mi-tab');
    if (!btn?.dataset.tab) return;
    switchModalTab(btn.dataset.tab);
  });

  const saved = localStorage.getItem(STORAGE_KEY) || DEFAULT_TAB;
  // Fall back to default tab if the saved tab doesn't exist in this modal
  // (e.g. 's2t' saved from a video but current file is an image)
  const tabExists = !!document.querySelector(`.modal-info #miPanel-${saved}`);
  _switchTo(tabExists ? saved : DEFAULT_TAB);
}

export function showAiTabBadge(): void {
  const badge = document.querySelector('.mi-tab-badge');
  if (badge) (badge as HTMLElement).style.display = '';
}

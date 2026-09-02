/**
 * context-menu/index.ts — Initialization: attach contextmenu listener to #results grid.
 */

import { show, close } from './context-menu';
import { installWindowApi } from '../shared/window-api';
import { installEditorClosedListener } from './external-editor';

interface CardData {
  id: number;
  path: string;
  positive: string;
  negative: string;
}

function _init(): void {
  // Install Tauri "editor-closed" listener once per page load (no-op in web mode).
  installEditorClosedListener();

  const resultsGrid = document.getElementById('results');
  if (!resultsGrid) return;

  resultsGrid.addEventListener('contextmenu', (e: MouseEvent) => {
    const target = e.target as HTMLElement;
    const card = target.closest<HTMLElement>('.result-card');
    if (!card) return;

    e.preventDefault();

    const data: CardData = {
      id: parseInt(card.dataset.id || '0', 10),
      path: card.dataset.path || '',
      positive: card.dataset.positive || '',
      negative: card.dataset.negative || '',
    };

    if (!data.id) return;

    show(e, data);
  });
}

const showContextMenu = (e: MouseEvent, fileId: number, cardEl: HTMLElement) => {
  const data: CardData = {
    id: fileId,
    path: cardEl.dataset.path || '',
    positive: cardEl.dataset.positive || '',
    negative: cardEl.dataset.negative || '',
  };
  show(e, data);
};

installWindowApi('contextMenuApi', {
  showContextMenu,
});

function _scheduleVisibleIdleInit(timeout = 2500): void {
  const run = (): void => {
    if (document.hidden) return;
    _init();
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      if ('requestIdleCallback' in window) {
        window.requestIdleCallback(run, { timeout });
      } else {
        setTimeout(run, 1200);
      }
    }, { once: true });
    return;
  }

  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(run, { timeout });
    return;
  }

  setTimeout(run, 1200);
}

_scheduleVisibleIdleInit();

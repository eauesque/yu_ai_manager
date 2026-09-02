export interface GridApi {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  showDetail: (id: number, opts?: any) => void;
  copyToClipboard: (text: string) => Promise<boolean>;
}

import { getAppApi, getNavApi, getSearchResultsApi } from '../../shared/browser-apis';

export async function handleGridKeydown(e: KeyboardEvent, api: GridApi): Promise<boolean> {
  const appApi = getAppApi();
  const navApi = getNavApi();
  const searchResultsApi = getSearchResultsApi();
  const modal = document.getElementById('modal');
  if (modal?.classList.contains('active')) return false;

  const activeEl = document.activeElement as HTMLElement | null;
  const activeCard = activeEl?.closest?.('.result-card') as HTMLElement | null;
  if (!activeCard || activeEl !== activeCard) return false;

  const cards = searchResultsApi.getResultCards() || [];
  if (!cards.length) return false;
  const cur = cards.indexOf(activeCard);
  if (cur < 0) return false;

  const perRow = searchResultsApi.estimateCardsPerRow(cards) || 1;
  const pageStep = Math.max(perRow * 3, 1);
  let next = -1;
  if (e.key === 'ArrowRight') next = cur + 1;
  if (e.key === 'ArrowLeft') next = cur - 1;
  if (e.key === 'ArrowDown') next = cur + perRow;
  if (e.key === 'ArrowUp') next = cur - perRow;
  if (e.key === 'PageDown') next = cur + pageStep;
  if (e.key === 'PageUp') next = cur - pageStep;
  if (e.key === 'Home') next = 0;
  if (e.key === 'End') next = cards.length - 1;
  if (next >= 0 && next < cards.length) {
    e.preventDefault();
    searchResultsApi.ensureSingleTabstopOnResultCards(cards[next]);
    searchResultsApi.focusResultCardByIndex(next);
    return true;
  }

  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    const img = activeCard.querySelector('img.result-image') as HTMLImageElement | null;
    const m = img?.src?.match(/\/api\/thumbnail\/(\d+)/);
    const id = m ? parseInt(m[1], 10) : NaN;
    if (Number.isFinite(id)) api.showDetail(id, { source: 'library', scope: 'result_set' });
    return true;
  }

  if (e.key.toLowerCase() === 'c' && !e.ctrlKey && !e.altKey && !e.metaKey) {
    e.preventDefault();
    const txt = (activeCard as HTMLElement).dataset.positive || '';
    const ok = await api.copyToClipboard(txt);
    navApi.showToast(ok ? appApi.tr('toast.copy_done') : appApi.tr('toast.copy_failed'), !ok);
    return true;
  }

  // M or ContextMenu key — open context menu at card position
  const isMenuKey = (e.key.toLowerCase() === 'm' && !e.ctrlKey && !e.altKey && !e.metaKey)
    || e.key === 'ContextMenu';
  if (isMenuKey) {
    e.preventDefault();
    const rect = activeCard.getBoundingClientRect();
    const fakeEvent = { clientX: rect.left + 8, clientY: rect.bottom - 4 } as MouseEvent;
    const cardData = {
      id: parseInt(activeCard.dataset.id || '0', 10),
      path: activeCard.dataset.path || '',
      positive: activeCard.dataset.positive || '',
      negative: activeCard.dataset.negative || '',
    };
    if (cardData.id) {
      void import('../../context-menu/context-menu').then(({ show }) => show(fakeEvent, cardData));
    }
    return true;
  }

  return false;
}

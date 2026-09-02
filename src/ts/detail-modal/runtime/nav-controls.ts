import { runtimeStateApi } from './state';
import { getSpreadState } from '../content/media';
import { getAppApi } from '../../shared/browser-apis';

let _groupingPromise: Promise<typeof import('../../search-results/results/grouping')> | null = null;

function _loadGrouping() {
  if (!_groupingPromise) {
    _groupingPromise = import('../../search-results/results/grouping');
  }
  return _groupingPromise;
}

export function updateFilmstripScrollButtons(): void {
  const strip = document.getElementById('modalFilmstripScroll');
  if (!strip) return;
  const parent = strip.closest('.modal-filmstrip');
  if (!parent) return;
  const prevBtn = parent.querySelector('.modal-filmstrip-nav--prev') as HTMLButtonElement | null;
  const nextBtn = parent.querySelector('.modal-filmstrip-nav--next') as HTMLButtonElement | null;
  const atLeft = strip.scrollLeft <= 1;
  const atRight = strip.scrollLeft + strip.clientWidth >= strip.scrollWidth - 1;
  if (prevBtn) prevBtn.disabled = atLeft;
  if (nextBtn) nextBtn.disabled = atRight;
}

export function scrollFilmstripPage(direction: number): void {
  const strip = document.getElementById('modalFilmstripScroll');
  if (!strip) return;
  const step = Math.max(strip.clientWidth - 60, 60 * 5);
  strip.scrollBy({ left: direction * step, behavior: 'smooth' });
  setTimeout(updateFilmstripScrollButtons, 350);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function setLoadMorePending(modal: HTMLElement, pending: boolean): void {
  const rightNav = modal.querySelector('.modal-nav-right') as HTMLButtonElement | null;
  if (rightNav) {
    rightNav.textContent = pending ? '\u23F3' : '\u203A';
    rightNav.disabled = !!pending;
    rightNav.style.opacity = pending ? '0.3' : '1';
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function updateButtons(modal: HTMLElement, state: any, hasMore: boolean): void {
  const prevBtn = modal.querySelector('.modal-nav-arrow[data-nav="prev"]') as HTMLButtonElement | null;
  const nextBtn = modal.querySelector('.modal-nav-arrow[data-nav="next"]') as HTMLButtonElement | null;
  const has = state.currentResultIds && state.currentResultIds.length > 0;
  const i = state.currentModalIndex;
  const atStart = !(has && i > 0);
  const atEnd = has && i >= 0 && i >= state.currentResultIds.length - 1;

  let prevDisabled = atStart;
  let nextDisabled = atEnd && !hasMore;

  const scope = runtimeStateApi.getViewerScope();
  if ((scope === 'folder_only' || scope === 'container_only')
      && localStorage.getItem('containerNavContinuous') === '1') {
    if (atStart || (atEnd && !hasMore)) {
      void _loadGrouping().then((mod) => {
        const hasPrev = atStart ? mod.getAdjacentGroupIds?.(state.currentResultIds, -1) : null;
        const hasNext = (atEnd && !hasMore) ? mod.getAdjacentGroupIds?.(state.currentResultIds, 1) : null;
        if (prevBtn && hasPrev) prevBtn.disabled = false;
        if (nextBtn && hasNext) nextBtn.disabled = false;
      }).catch(() => {});
    }
  }

  if (prevBtn) prevBtn.disabled = prevDisabled;
  if (nextBtn) nextBtn.disabled = nextDisabled;

  // disabled styling is handled by CSS :disabled pseudo-class
  // Do NOT set inline opacity here — it overrides the hover-to-reveal pattern

  const strip = modal.querySelector('#modalFilmstripScroll') as HTMLElement | null;
  if (strip && has && i >= 0) {
    const currentId = state.currentResultIds[i];
    const winStart = Number(strip.dataset.windowStart || 0);
    const winEnd = Number(strip.dataset.windowEnd || 0);
    const FILMSTRIP_WINDOW = 50;
    if (winEnd > winStart && state.currentResultIds.length > FILMSTRIP_WINDOW) {
      const needRebuild = (i - winStart < 5 && winStart > 0) || (winEnd - i < 5 && winEnd < state.currentResultIds.length);
      if (needRebuild) {
        const half = Math.floor(FILMSTRIP_WINDOW / 2);
        let newStart = Math.max(0, i - half);
        let newEnd = Math.min(state.currentResultIds.length, newStart + FILMSTRIP_WINDOW);
        if (newEnd === state.currentResultIds.length) newStart = Math.max(0, newEnd - FILMSTRIP_WINDOW);
        let html = '';
        for (let wi = newStart; wi < newEnd; wi++) {
          const fid = state.currentResultIds[wi];
          const isCurrent = Number(fid) === currentId;
          html += '<button type="button" class="modal-filmstrip-thumb' + (isCurrent ? ' active' : '') + '"'
            + ' data-fid="' + fid + '"'
            + ' data-scope="' + getAppApi().escapeHtml(scope) + '"'
            + ' data-action-scope="detail-modal" data-action="detailModalShowFromThumb"'
            + ' title="#' + fid + '">'
            + '<img src="' + getAppApi().apiUrl('/api/thumbnail/' + fid) + '" loading="lazy" alt="">'
            + '</button>';
        }
        const oldThumbs = strip.querySelectorAll('.modal-filmstrip-thumb');
        oldThumbs.forEach((t) => t.remove());
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;
        while (tempDiv.firstChild) strip.appendChild(tempDiv.firstChild);
        strip.dataset.windowStart = String(newStart);
        strip.dataset.windowEnd = String(newEnd);
      }
    }

    let spreadPairId: number | null = null;
    const spreadActive = localStorage.getItem('spreadViewEnabled') === '1'
      && (scope === 'folder_only' || scope === 'container_only')
      && state.currentResultIds.length > 1;
    if (spreadActive && i > 0) {
      const spreadState = getSpreadState(state.currentResultIds, currentId, scope);
      if (spreadState && spreadState.enabled && spreadState.pairId != null) {
        spreadPairId = Number(spreadState.pairId);
      }
    }

    const thumbs = strip.querySelectorAll('.modal-filmstrip-thumb');
    let firstActiveEl: HTMLElement | null = null;
    let lastActiveEl: HTMLElement | null = null;
    thumbs.forEach((t) => {
      const fid = Number((t as HTMLElement).dataset.fid);
      const isActiveThumb = fid === currentId || (spreadPairId != null && fid === spreadPairId);
      t.classList.toggle('active', isActiveThumb);
      if (isActiveThumb) {
        if (!firstActiveEl) firstActiveEl = t as HTMLElement;
        lastActiveEl = t as HTMLElement;
      }
    });
    if (firstActiveEl) {
      if (lastActiveEl && lastActiveEl !== firstActiveEl) {
        const midLeft = ((firstActiveEl as HTMLElement).offsetLeft + (lastActiveEl as HTMLElement).offsetLeft + (lastActiveEl as HTMLElement).offsetWidth) / 2 - strip.clientWidth / 2;
        strip.scrollTo({ left: Math.max(0, midLeft), behavior: 'smooth' });
      } else {
        const left = (firstActiveEl as HTMLElement).offsetLeft - strip.clientWidth / 2 + (firstActiveEl as HTMLElement).offsetWidth / 2;
        strip.scrollTo({ left: Math.max(0, left), behavior: 'smooth' });
      }
    }
    const posEl = strip.querySelector('.modal-filmstrip-pos');
    if (posEl) posEl.textContent = (i + 1) + ' / ' + state.currentResultIds.length;
  }

  const posBadge = modal.querySelector('#modalPosBadge');
  if (posBadge && has && i >= 0) posBadge.textContent = (i + 1) + ' / ' + state.currentResultIds.length;

  updateFilmstripScrollButtons();
}

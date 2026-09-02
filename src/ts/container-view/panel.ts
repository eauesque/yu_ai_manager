/**
 * container-view/panel.ts — Full-screen overlay panel showing container members.
 * Opens when a container card (ZIP/folder) is clicked; clicking a member
 * opens the detail modal scoped to the container.
 */

import { getState, setState, resetState } from './state';
import { renderContainerGrid, highlightMember, scrollToMember, teardownContainerGrid } from './grid';
import { setScopeResultIds } from '../runtime-pre/ui-state';
import { getAppApi, getDetailModalApi } from '../shared/browser-apis';

export interface ContainerViewOpenOpts {
  containerType: 'zip' | 'folder';
  containerKey: string;
  containerPath: string;
  memberIds: number[];
  focusFileId?: number | null;
}

/* ---- Open ---- */

// CSS transition for `.cv-panel` is 200ms (opacity + transform).  We push the
// expensive grid build / teardown OUTSIDE that window so the compositor can
// finish the fade smoothly without main-thread DOM work fighting it.
const TRANSITION_MS = 220;

let _pendingRenderTimer: ReturnType<typeof setTimeout> | null = null;
let _pendingTeardownTimer: ReturnType<typeof setTimeout> | null = null;

function _cancelPendingTimers(): void {
  if (_pendingRenderTimer !== null) {
    clearTimeout(_pendingRenderTimer);
    _pendingRenderTimer = null;
  }
  if (_pendingTeardownTimer !== null) {
    clearTimeout(_pendingTeardownTimer);
    _pendingTeardownTimer = null;
  }
}

export function openContainerViewPanel(opts: ContainerViewOpenOpts): void {
  const panel = document.getElementById('containerViewPanel');
  if (!panel) return;

  const ids = opts.memberIds;
  if (!ids.length) return;

  // If close-deferred teardown is still pending from a previous panel,
  // cancel it and tear down synchronously so we don't render new cards
  // on top of stale ones (and so the deferred teardown doesn't wipe the
  // new grid out from under us 220ms later).
  if (_pendingTeardownTimer !== null) {
    clearTimeout(_pendingTeardownTimer);
    _pendingTeardownTimer = null;
    teardownContainerGrid(document.getElementById('cvGrid'));
  }
  if (_pendingRenderTimer !== null) {
    clearTimeout(_pendingRenderTimer);
    _pendingRenderTimer = null;
  }

  // Update state
  setState({
    isOpen: true,
    containerType: opts.containerType,
    containerKey: opts.containerKey,
    containerPath: opts.containerPath,
    memberIds: ids,
    focusFileId: opts.focusFileId ?? null,
  });

  // Set modal scope so ← → navigation stays within container
  const scope = opts.containerType === 'zip' ? 'container_only' : 'folder_only';
  setScopeResultIds(scope, ids);

  // Update header
  _updateHeader(panel, opts);

  // NOTE: We deliberately do NOT POST /api/thumbnails/warmup here.
  // The batch fetcher in `grid.ts` (via `thumbnail-batch.ts`) already
  // serves visible thumbnails through a single thread per request, and
  // the per-archive lock in `serve_thumbnail` keeps cache-miss generation
  // serialized to one ZIP open at a time.

  const gridEl = document.getElementById('cvGrid');

  // Show panel first (start CSS opacity/transform transition)
  panel.classList.add('active');
  document.body.classList.add('cv-panel-open');

  // Defer the heavy grid render until *after* the panel fade-in
  // finishes. Building 30+ cards (each with an IntersectionObserver
  // entry + a queued batch request) inside the same frame as the
  // CSS transition is what made the cursor stutter for the duration
  // of the animation. The user sees an empty fading-in panel for
  // 220ms, then the cards appear — much smoother than a synchronous
  // build + transition fight.
  if (gridEl) {
    _applySavedGridSettings(gridEl);
    _pendingRenderTimer = setTimeout(() => {
      _pendingRenderTimer = null;
      renderContainerGrid(gridEl, ids, _onMemberClick);
      requestAnimationFrame(() => {
        const first = gridEl.querySelector<HTMLElement>('.cv-member-card');
        first?.focus();
      });
    }, TRANSITION_MS);
  }
}

/* ---- Close ---- */

export function closeContainerViewPanel(): void {
  const panel = document.getElementById('containerViewPanel');
  if (panel) panel.classList.remove('active');  // Begin fade-out
  document.body.classList.remove('cv-panel-open');

  // If render hasn't actually run yet (user closed during the open
  // delay), cancel it so we don't paint cards into a panel that's
  // about to disappear.
  if (_pendingRenderTimer !== null) {
    clearTimeout(_pendingRenderTimer);
    _pendingRenderTimer = null;
  }

  // Defer DOM teardown until *after* the fade-out finishes. Removing
  // hundreds of <img> nodes during the 200ms opacity transition is
  // what caused the cursor to freeze right after the close button
  // was clicked. Now the user sees a smooth fade, and the heavy
  // teardown happens on an invisible panel.
  const gridEl = document.getElementById('cvGrid');
  if (_pendingTeardownTimer !== null) clearTimeout(_pendingTeardownTimer);
  _pendingTeardownTimer = setTimeout(() => {
    _pendingTeardownTimer = null;
    teardownContainerGrid(gridEl);
  }, TRANSITION_MS);

  resetState();
}

// Exported for emergency cleanup paths (e.g. page unload) so a deferred
// teardown can be flushed synchronously if needed.
export function flushContainerViewCleanup(): void {
  _cancelPendingTimers();
  teardownContainerGrid(document.getElementById('cvGrid'));
}

/* ---- Return from modal ---- */

export function returnToContainerView(): void {
  const st = getState();
  if (!st.isOpen) return;

  const panel = document.getElementById('containerViewPanel');
  if (!panel) return;

  const gridEl = document.getElementById('cvGrid');
  if (!gridEl) return;

  // Highlight & scroll to the last viewed image
  if (st.focusFileId != null) {
    highlightMember(gridEl, st.focusFileId);
    requestAnimationFrame(() => {
      scrollToMember(gridEl, st.focusFileId!);
    });
  }
}

/* ---- Internals ---- */

function _onMemberClick(fileId: number): void {
  // Track which image the user viewed last
  setState({ focusFileId: fileId });

  const st = getState();
  const scope = st.containerType === 'zip' ? 'container_only' : 'folder_only';
  getDetailModalApi().showDetail(fileId, {
    source: st.containerType,
    scope,
    scopeIds: st.memberIds,
  });
}

function _updateHeader(panel: HTMLElement, opts: ContainerViewOpenOpts): void {
  const _t = getAppApi().tr;

  // Path label
  const labelEl = panel.querySelector('.cv-header-label');
  if (labelEl) {
    const icon = opts.containerType === 'zip' ? '\uD83D\uDDDC\uFE0F ' : '\uD83D\uDCC1 ';
    const shortPath = _shortenPath(opts.containerPath || opts.containerKey);
    labelEl.textContent = icon + shortPath;
    labelEl.setAttribute('title', opts.containerPath || opts.containerKey);
  }

  // Member count
  const countEl = panel.querySelector('.cv-member-count');
  if (countEl) {
    const tmpl = _t('container_view.member_count', '{count} items');
    countEl.textContent = tmpl.replace('{count}', String(opts.memberIds.length));
  }
}

function _applySavedGridSettings(gridEl: HTMLElement): void {
  const cols = localStorage.getItem('gridColumns');
  if (cols && cols !== '0') {
    gridEl.style.setProperty('--grid-columns', cols);
  } else {
    gridEl.style.removeProperty('--grid-columns');
  }
  const minSize = localStorage.getItem('gridMinSize');
  if (minSize) {
    gridEl.style.setProperty('--grid-min-size', minSize + 'px');
  }
}

function _shortenPath(p: string): string {
  if (!p) return '';
  // Normalise separators
  const s = p.replace(/\\/g, '/');
  const parts = s.split('/').filter(Boolean);
  if (parts.length <= 3) return parts.join('/');
  return '.../' + parts.slice(-2).join('/');
}

/* ---- Panel button wiring (called once from index.ts) ---- */

export function initPanelButtons(): void {
  const panel = document.getElementById('containerViewPanel');
  if (!panel) return;

  // Back button
  const backBtn = panel.querySelector('.cv-back-btn');
  backBtn?.addEventListener('click', () => closeContainerViewPanel());

  // Close button
  const closeBtn = panel.querySelector('.cv-close-btn');
  closeBtn?.addEventListener('click', () => closeContainerViewPanel());
}

/**
 * results/grouping-cards.ts
 *
 * Container card operations: replace/restore DOM cards with grouped
 * container cards, click handler, modal opening, member cache.
 */

import { dbg } from './grouping-utils';
import { buildContainerCardInnerHtml } from './render-card';
import { setScopeResultIds } from '../../runtime-pre/ui-state';
import { getAppApi, getContainerViewApi, getDetailModalApi } from '../../shared/browser-apis';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRecord = Record<string, any>;

export interface ContainerGroupInfo {
  type: 'zip' | 'folder';
  key: string;
  label: string;
  count: number;
  memberIds?: number[] | undefined;
  representativeIds: number[];
  firstResult: AnyRecord;
}

export interface ContainerCard extends HTMLElement {
  _origContainerState?: {
    html: string;
    className: string;
  };
  _groupKey?: string;
  _groupType?: string;
  _groupReps?: number[];
}

/* ---- Member cache ---- */

let _memberCache: Record<string, number[]> = {}; // key -> ids[]

export function getMemberCache(): Record<string, number[]> {
  return _memberCache;
}

export function setMemberCacheEntry(key: string, ids: number[]): void {
  _memberCache[key] = ids;
}

export function clearMemberCache(): void {
  _memberCache = {};
}

/* ---- Card restore / replace ---- */

export function restoreCard(card: ContainerCard): void {
  if (!card._origContainerState) return;
  card.innerHTML = card._origContainerState.html;
  card.className = card._origContainerState.className;
  delete card.dataset.containerKey;
  delete card.dataset.memberCount;
  card.removeEventListener('click', onContainerClick);
  delete card._origContainerState;
}

export function replaceWithContainerCard(card: ContainerCard, groupInfo: ContainerGroupInfo): void {
  if (!card._origContainerState) {
    card._origContainerState = {
      html: card.innerHTML,
      className: card.className,
    };
  }
  card.className = 'result-card container-card container-' + groupInfo.type;
  card.innerHTML = buildContainerCardInnerHtml(groupInfo);
  card.dataset.containerKey = groupInfo.key;
  card.dataset.memberCount = String(groupInfo.count);
  card._groupKey = groupInfo.key;
  card._groupType = groupInfo.type;
  card._groupReps = groupInfo.representativeIds || [];
  card.removeEventListener('click', onContainerClick);
  card.addEventListener('click', onContainerClick);
}

/* ---- Container card click: fetch member IDs on demand, then open modal ---- */

export function onContainerClick(e: Event): void {
  e.stopPropagation();
  const card = e.currentTarget as ContainerCard;
  const type = card._groupType || (card.classList.contains('container-zip') ? 'zip' : 'folder');
  const key = card._groupKey || card.dataset.containerKey || '';
  const reps = card._groupReps || [];

  dbg('_onContainerClick', 'type:', type, 'key:', key, 'reps:', reps.length,
      'cached:', !!_memberCache[key], 'cachedLen:', _memberCache[key] ? _memberCache[key].length : 0);

  if (!key) return;

  // Show loading state
  card.classList.add('container-loading');

  // Check cache first
  if (_memberCache[key]) {
    card.classList.remove('container-loading');
    openContainerModal(type, _memberCache[key], key);
    return;
  }

  // Fetch member IDs from server
  const url = getAppApi().apiUrl('/api/group-members?key=' + encodeURIComponent(key));

  fetch(url)
    .then(function (res) { return res.json(); })
    .then(function (data: { ids?: number[] }) {
      card.classList.remove('container-loading');
      let ids = (data && Array.isArray(data.ids)) ? data.ids : [];
      if (ids.length === 0) {
        // Fallback to reps
        ids = reps.slice();
      }
      _memberCache[key] = ids;
      openContainerModal(type, ids, key);
    })
    .catch(function (err) {
      card.classList.remove('container-loading');
      console.warn('group-members fetch failed:', err);
      // Fallback to reps
      if (reps.length > 0) {
        openContainerModal(type, reps, key);
      }
    });
}

function openContainerModal(type: string, ids: number[], key?: string): void {
  if (!ids.length) return;
  const firstId = ids[0];
  const isArchive = type === 'zip' || type === 'archive';
  const scope = isArchive ? 'container_only' : 'folder_only';
  dbg('_openContainerModal', 'type:', type, 'scope:', scope,
      'ids.length:', ids.length, 'firstId:', firstId,
      'first5:', ids.slice(0, 5));
  const { openContainerViewPanel } = getContainerViewApi();
  const { showDetail } = getDetailModalApi();

  // Prefer ContainerView panel when available
  if (openContainerViewPanel) {
    const containerPath = key ? key.replace(/^(folder|zip|archive):/, '') : '';
    openContainerViewPanel({
      containerType: (isArchive ? 'zip' : 'folder') as 'zip' | 'folder',
      containerKey: key || '',
      containerPath,
      memberIds: ids,
    });
    return;
  }

  // Fallback: open modal directly
  setScopeResultIds(scope, ids);
  if (showDetail) {
    showDetail(firstId, {
      source: type,
      scope: scope,
      scopeIds: ids,
    });
  }
}

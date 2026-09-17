import { rgState as S, type OrderedGroup } from './grouping-utils';
import { searchPager } from '../search/pagination';
import { getViewerScope, setScopeResultIds } from '../../runtime-pre/ui-state';
import { restoreCard, replaceWithContainerCard, setMemberCacheEntry, type ContainerCard } from './grouping-cards';
import { scheduleAfterPaint, scheduleIdle } from './grouping-search-scheduler';
import type { GroupedSearchData } from './grouping-search';

const INITIAL_SYNC_GROUPS = 96;
const CHUNK_GROUPS = 64;
const POST_PAINT_CHUNK = 200;

export function renderGroupedResults(
  data: GroupedSearchData,
  mode: string,
  container: HTMLElement | null,
  updateUi: (mode: string, visibleCount: number, totalCount: number, totalGroups?: number, limited?: boolean) => void,
  handle: { cancelled: boolean },
  perf: { mark(name: string): void },
): void {
  if (!container) return;
  const groups = data.groups || [];
  const cards = Array.from(container.querySelectorAll<HTMLElement>('.result-card')) as ContainerCard[];
  const visibleIds = groups.map((group) => group.reps && group.reps[0] ? group.reps[0] : 0).filter((id): id is number => id > 0);

  const reusableCount = Math.min(cards.length, groups.length);
  for (let i = 0; i < reusableCount; i++) restoreCard(cards[i]);
  for (let i = 0; i < cards.length; i++) cards[i].style.display = 'none';
  searchPager.teardownScrollObserver();

  let nextIndex = 0;
  let renderDoneMarked = false;

  const renderChunk = (endExclusive: number): void => {
    if (handle.cancelled) return;
    const fragment = document.createDocumentFragment();
    for (; nextIndex < endExclusive && nextIndex < groups.length; nextIndex++) {
      const group = groups[nextIndex];
      let card: ContainerCard;
      if (nextIndex < cards.length) {
        card = cards[nextIndex];
        card.style.display = '';
      } else {
        card = document.createElement('div') as ContainerCard;
        card.className = 'result-card';
        card.dataset.id = group.reps && group.reps[0] ? String(group.reps[0]) : '0';
        fragment.appendChild(card);
      }
      replaceWithContainerCard(card, {
        type: group.type,
        key: group.key,
        label: group.label,
        count: group.count,
        memberIds: group.memberIds,
        representativeIds: (group.reps || []).slice(0, 8),
        firstResult: { id: group.reps && group.reps[0] ? group.reps[0] : 0, path: '' },
      });
    }
    if (fragment.childNodes.length > 0) container.appendChild(fragment);
  };

  const finishPostPaint = (): void => {
    if (handle.cancelled) return;
    const ordered: OrderedGroup[] = new Array(groups.length);
    let idx = 0;

    const processChunk = (): void => {
      if (handle.cancelled) return;
      const end = Math.min(idx + POST_PAINT_CHUNK, groups.length);
      for (; idx < end; idx++) {
        const group = groups[idx];
        const ids = group.memberIds || [];
        if (ids.length > 0) setMemberCacheEntry(group.key, ids);
        ordered[idx] = {
          key: group.key,
          type: group.type,
          ids,
          label: group.label,
          groupPath: group.key.replace(/^(folder|zip):/, ''),
        };
      }
      if (idx < groups.length) {
        scheduleIdle(processChunk);
        return;
      }
      S.orderedGroups = ordered;
      S.resultOrderGroups = ordered.slice();
      perf.mark('grouping_post_paint_ready');
    };
    processChunk();
  };

  const scheduleRemainingChunks = (): void => {
    if (handle.cancelled) return;
    if (nextIndex >= groups.length) {
      scheduleAfterPaint(finishPostPaint);
      return;
    }
    scheduleIdle(() => {
      renderChunk(nextIndex + CHUNK_GROUPS);
      scheduleRemainingChunks();
    });
  };

  renderChunk(Math.min(groups.length, INITIAL_SYNC_GROUPS));
  container.classList.remove('is-loading');

  scheduleAfterPaint(() => {
    if (handle.cancelled) return;
    updateUi(mode, data.returned_groups || groups.length, data.total_files || 0, data.total_groups || groups.length, !!data.limited);
    const viewerScope = getViewerScope() || 'result_set';
    if (viewerScope === 'result_set') setScopeResultIds('result_set', visibleIds);
    if (!renderDoneMarked) {
      renderDoneMarked = true;
      perf.mark('grouping_render_done');
    }
    scheduleRemainingChunks();
  });
}

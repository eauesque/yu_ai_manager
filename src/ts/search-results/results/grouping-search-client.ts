import { searchPager } from '../search/pagination';
import type { GroupedSearchData, GroupedSearchGroup } from './grouping-search';

function dirname(path: string): string {
  const normalized = path.replace(/\\/g, '/');
  const idx = normalized.lastIndexOf('/');
  return idx >= 0 ? normalized.slice(0, idx) : '';
}

function basename(path: string): string {
  if (!path) return '';
  const normalized = path.replace(/\\/g, '/').replace(/\/+$/, '');
  const idx = normalized.lastIndexOf('/');
  return idx >= 0 ? normalized.slice(idx + 1) : normalized;
}

export function buildClientGroupedResults(mode: string, container: HTMLElement | null): GroupedSearchData | null {
  if (mode !== 'folder' || !container) return null;
  if (searchPager.getHasMore()) return null;
  const totalCount = searchPager.getTotalCount();
  const cards = Array.from(container.querySelectorAll<HTMLElement>('.result-card'));
  if (totalCount <= 0 || cards.length < totalCount) return null;

  const groups = new Map<string, GroupedSearchGroup>();
  for (const card of cards) {
    const id = Number(card.dataset.id || '0');
    const path = String(card.dataset.path || '').trim();
    if (!id || !path) continue;
    const dir = dirname(path);
    if (!dir) continue;
    const key = 'folder:' + dir;
    let group = groups.get(key);
    if (!group) {
      group = { type: 'folder', key, label: basename(dir) || dir, count: 0, memberIds: [], reps: [] };
      groups.set(key, group);
    }
    group.count += 1;
    group.memberIds!.push(id);
    if (group.reps!.length < 8) group.reps!.push(id);
  }

  const resultGroups = Array.from(groups.values()).filter((group) => (group.memberIds?.length || 0) >= 2);
  if (resultGroups.length === 0) return null;
  const totalFiles = resultGroups.reduce((sum, group) => sum + (group.memberIds?.length || 0), 0);
  return {
    status: 'ok',
    groups: resultGroups,
    total_files: totalFiles,
    total_groups: resultGroups.length,
    returned_groups: resultGroups.length,
    limited: false,
    perf: { client_fast_path: 1, total_ms: 0 },
  };
}

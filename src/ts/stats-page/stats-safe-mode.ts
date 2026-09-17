import type { TagRow } from './charts/core';

const NSFW_PATTERNS = ['nsfw', 'explicit', 'nude', 'naked', 'adult', 'lewd', 'hentai', 'erotic'];

function isNsfwTag(tag: TagRow): boolean {
  const full = (tag.namespace ? `${tag.namespace}:${tag.tag}` : tag.tag).toLowerCase();
  return NSFW_PATTERNS.some((pattern) => full.includes(pattern));
}

function getSafeMode(): boolean {
  return localStorage.getItem('stats_safe_mode') === '1';
}

function setSafeMode(val: boolean): void {
  localStorage.setItem('stats_safe_mode', val ? '1' : '0');
}

export function filterSafeModeTags(tags: TagRow[]): TagRow[] {
  return tags.filter((tag) => !getSafeMode() || !isNsfwTag(tag));
}

export function initSafeModeToggle(
  getAllTopTags: () => TagRow[],
  onFiltered: (filtered: TagRow[]) => void,
): void {
  const cb = document.getElementById('statsTopTagsSafeMode') as HTMLInputElement | null;
  if (!cb) return;
  cb.checked = getSafeMode();
  if (cb.dataset.actionBound === '1') return;
  cb.dataset.actionBound = '1';
  cb.addEventListener('change', () => {
    setSafeMode(cb.checked);
    onFiltered(filterSafeModeTags(getAllTopTags()));
  });
}

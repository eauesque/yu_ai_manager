/**
 * Tag editing module: add/remove user tags from detail modal.
 */

import { getAppApi, getNavApi } from '../shared/browser-apis';
import { renderTagsSection } from '../meta-renderer/sections-content';
import { installWindowApi } from '../shared/window-api';

let _debounceTimer: ReturnType<typeof setTimeout> | null = null;

function _tr(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback) || fallback;
}

/** Add a user tag to a file via batch-set API. */
export async function addUserTag(fileId: number, tag?: string): Promise<void> {
  const input = document.getElementById('tagAddInput') as HTMLInputElement | null;
  const text = (tag || input?.value || '').trim();
  if (!text || !fileId) return;
  const { apiFetch } = getAppApi();
  const { showToast } = getNavApi();

  try {
    const res = await apiFetch('/api/tags/batch-set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: [{ file_id: fileId, add: [text], remove: [] }] }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (input) input.value = '';
    showToast(_tr('tags.added', 'Tag added'));
    await _refreshTagsInModal(fileId);
  } catch {
    showToast(_tr('tags.add_failed', 'Failed to add tag'), true);
  }
}

/** Remove a user tag from a file. */
export async function removeUserTag(fileId: number, tag: string): Promise<void> {
  if (!tag || !fileId) return;
  const { apiFetch } = getAppApi();
  const { showToast } = getNavApi();
  try {
    const res = await apiFetch('/api/tags/batch-set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: [{ file_id: fileId, add: [], remove: [tag] }] }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast(_tr('tags.removed', 'Tag removed'));
    await _refreshTagsInModal(fileId);
  } catch {
    showToast(_tr('tags.remove_failed', 'Failed to remove tag'), true);
  }
}

/** Handle keyboard events in the tag input field. */
export function handleTagInputKey(e: KeyboardEvent, fileId: number): void {
  if (e.key === 'Enter') {
    e.preventDefault();
    addUserTag(fileId);
  } else if (e.key === 'Escape') {
    const input = e.target as HTMLInputElement;
    input.value = '';
    input.blur();
  }
}

/** Refresh the tags section in the detail modal after add/remove. */
async function _refreshTagsInModal(fileId: number): Promise<void> {
  try {
    const res = await getAppApi().apiFetch(`/api/file/${fileId}`);
    if (!res.ok) return;
    const json = await res.json();
    const data = json.data || json;
    const tags = data.tags || [];

    const container = document.querySelector('.meta-tag-list')?.parentElement;
    if (!container) return;

    // Find the section wrapper (parent of all .meta-tag-list elements)
    const section = container.closest('.meta-section');
    if (!section) return;

    const html = renderTagsSection(tags, fileId);
    const header = section.querySelector('.meta-section-header');
    if (header) {
      while (header.nextSibling) {
        header.nextSibling.remove();
      }
      section.outerHTML = html;
    }
  } catch { /* silent */ }
}

/** Fetch tag suggestions for autocomplete (debounced). */
export function fetchSuggestionsForTagInput(input: HTMLInputElement): void {
  const { apiFetch } = getAppApi();
  if (_debounceTimer) clearTimeout(_debounceTimer);
  const q = input.value.trim();
  if (q.length < 2) {
    _clearDatalist(input);
    return;
  }
  _debounceTimer = setTimeout(async () => {
    try {
      const res = await apiFetch(`/api/tags/suggest?q=${encodeURIComponent(q)}&limit=10`);
      if (!res.ok) return;
      const json = await res.json();
      const tags: Array<{ tag: string }> = json.data || [];
      _updateDatalist(input, tags.map(t => t.tag));
    } catch { /* silent */ }
  }, 250);
}

function _clearDatalist(input: HTMLInputElement): void {
  const dl = document.getElementById('tagSuggestList');
  if (dl) dl.innerHTML = '';
}

function _updateDatalist(input: HTMLInputElement, suggestions: string[]): void {
  let dl = document.getElementById('tagSuggestList');
  if (!dl) {
    dl = document.createElement('datalist');
    dl.id = 'tagSuggestList';
    document.body.appendChild(dl);
    input.setAttribute('list', 'tagSuggestList');
  }
  // Build options via DOM API to prevent XSS from tag names
  dl.textContent = '';
  for (const s of suggestions) {
    const opt = document.createElement('option');
    opt.value = s;
    dl.appendChild(opt);
  }
}

/** Deduplicate a comma-separated tag string via the API. */
export async function dedupTags(text: string, keep: 'first' | 'last' = 'first'): Promise<string> {
  const { apiFetch } = getAppApi();
  try {
    const res = await apiFetch('/api/tags/dedup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: text, keep }),
    });
    if (!res.ok) return text;
    const json = await res.json();
    return (json.data?.string ?? text) as string;
  } catch {
    return text;
  }
}

installWindowApi('tagEditApi', {
  addUserTag,
  removeUserTag,
  handleTagInputKey,
  fetchSuggestionsForTagInput,
  dedupTags,
}, {
  addUserTag: 'addUserTag',
  removeUserTag: 'removeUserTag',
  handleTagInputKey: 'handleTagInputKey',
  fetchSuggestionsForTagInput: '_fetchSuggestionsForTagInput',
  dedupTags: 'dedupTags',
});

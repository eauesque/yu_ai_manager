/**
 * collections-crud.ts -- Create / rename / delete / export operations
 * for collections. Split from collections-sidebar.ts.
 */

import { type CollectionRecord, _t, getActiveValue, getAddInput, selectCollection } from './collections-state';
import { loadSidebarCollections } from './collections-sidebar';
import { getRuntimeToolsUiHooks } from './hooks';
import { getAppApi } from '../shared/browser-apis';

// --- Rename ---
export function startRename(itemDiv: HTMLElement, coll: CollectionRecord): void {
  const nameSpan = itemDiv.querySelector('.cs-item-name') as HTMLElement | null;
  if (!nameSpan) return;
  const oldName = coll.name;
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'cs-rename-input';
  input.value = oldName;

  nameSpan.replaceWith(input);
  input.focus();
  input.select();

  function finish(): void {
    const newName = input.value.trim();
    if (newName && newName !== oldName) {
      _renameCollection(coll.id, newName);
    } else {
      // Restore
      const span = document.createElement('span');
      span.className = 'cs-item-name';
      span.textContent = oldName;
      input.replaceWith(span);
    }
  }

  input.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') { e.preventDefault(); finish(); }
    if (e.key === 'Escape') {
      const span = document.createElement('span');
      span.className = 'cs-item-name';
      span.textContent = oldName;
      input.replaceWith(span);
    }
    e.stopPropagation();
  });
  input.addEventListener('blur', finish);
}

async function _renameCollection(id: number, newName: string): Promise<void> {
  try {
    const response = await getAppApi().apiFetch('/api/collections/' + id, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newName }),
    });
    if (!response.ok) return;
    loadSidebarCollections();
    getRuntimeToolsUiHooks().loadCollectionFilter();
  } catch (e) {
    console.error('renameCollection failed:', e);
  }
}

// --- Export helpers ---
function _triggerDownload(url: string): void {
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export function exportCollectionCsv(coll: CollectionRecord): void {
  _triggerDownload('/api/collections/' + coll.id + '/export/csv');
}

export function exportCollectionRecipeCsv(coll: CollectionRecord): void {
  _triggerDownload('/api/collections/' + coll.id + '/export?format=recipe_csv');
}

export function exportCollectionRecipeJson(coll: CollectionRecord): void {
  _triggerDownload('/api/collections/' + coll.id + '/export?format=recipe_json');
}

/** Show a small export format dropdown anchored to the trigger button. */
export function showExportDropdown(triggerEl: HTMLElement, coll: CollectionRecord): void {
  // Remove any existing dropdown
  document.querySelector('.cs-export-dropdown')?.remove();

  const menu = document.createElement('div');
  menu.className = 'cs-export-dropdown';

  const items: Array<{ label: string; fn: () => void }> = [
    { label: _t('collections.export_csv', 'パスCSV'), fn: () => exportCollectionCsv(coll) },
    { label: _t('collections.export_recipe_csv', 'レシピCSV'), fn: () => exportCollectionRecipeCsv(coll) },
    { label: _t('collections.export_recipe_json', 'レシピJSON'), fn: () => exportCollectionRecipeJson(coll) },
  ];

  items.forEach(({ label, fn }) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'cs-export-dropdown-item';
    item.textContent = label;
    item.addEventListener('click', (e: MouseEvent) => {
      e.stopPropagation();
      menu.remove();
      document.removeEventListener('click', outsideClick);
      fn();
    });
    menu.appendChild(item);
  });

  document.body.appendChild(menu);

  // Position below the trigger button
  const rect = triggerEl.getBoundingClientRect();
  menu.style.left = Math.max(4, rect.left) + 'px';
  menu.style.top = (rect.bottom + 2) + 'px';
  // Clamp right overflow
  const mw = menu.getBoundingClientRect().width;
  if (rect.left + mw > window.innerWidth - 4) {
    menu.style.left = Math.max(4, window.innerWidth - mw - 4) + 'px';
  }

  const outsideClick = (e: MouseEvent): void => {
    if (!menu.contains(e.target as Node)) {
      menu.remove();
      document.removeEventListener('click', outsideClick);
    }
  };
  // Defer to avoid the current click immediately closing it
  requestAnimationFrame(() => document.addEventListener('click', outsideClick));
}

// --- Delete ---
export async function deleteCollection(coll: CollectionRecord): Promise<void> {
  if (coll.id === 1) return;
  const msg = _t('collections.delete_confirm', 'Delete this collection? Files will not be deleted.');
  if (!confirm(msg)) return;
  try {
    const response = await getAppApi().apiFetch('/api/collections/' + coll.id, { method: 'DELETE' });
    if (!response.ok) return;
    // If deleted collection was active, reset to All
    if (getActiveValue() === String(coll.id)) {
      selectCollection('');
    }
    loadSidebarCollections();
    getRuntimeToolsUiHooks().loadCollectionFilter();
  } catch (e) {
    console.error('deleteCollection failed:', e);
  }
}

// --- Create new ---
export function handleCreate(): void {
  const addInput = getAddInput();
  if (!addInput) return;
  const name = addInput.value.trim();
  if (!name) return;
  _createNewCollection(name);
}

async function _createNewCollection(name: string): Promise<void> {
  try {
    const response = await getAppApi().apiFetch('/api/collections', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!response.ok) return;
    const addInput = getAddInput();
    if (addInput) addInput.value = '';
    loadSidebarCollections();
    getRuntimeToolsUiHooks().loadCollectionFilter();
  } catch (e) {
    console.error('createCollection failed:', e);
  }
}

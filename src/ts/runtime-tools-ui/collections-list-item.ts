/**
 * collections-list-item.ts -- Collection list item rendering and event delegation.
 *
 * Builds individual sidebar items with checkboxes, action buttons,
 * and handles click/keyboard event delegation on the list container.
 * Extracted from collections-sidebar.ts to keep each module under 300 lines.
 */

import {
  type CollectionRecord,
  _t,
  getActiveValue,
  selectCollection,
} from './collections-state';
import { startRename, showExportDropdown, deleteCollection } from './collections-crud';
import { onUnionCheckChange, applySmartCollection } from './collections-smart';
import { hasUnionCheckedId } from '../shared/runtime-state/union-search-state';

// -- Collection data cache for event delegation --
const _collMap = new Map<string, CollectionRecord>();

/** Clear and rebuild the collection map from fetched data. */
export function rebuildCollMap(collections: CollectionRecord[]): void {
  _collMap.clear();
  collections.forEach((c) => _collMap.set(String(c.id), c));
}

/** Build a single sidebar list item element. */
export function makeItem(
  value: string,
  label: string,
  coll: CollectionRecord | null,
  activeVal: string,
): HTMLElement {
  const div = document.createElement('div');
  div.className = 'cs-item';
  div.setAttribute('tabindex', '0');
  // Use role="row" (parent is role="grid") to allow interactive children
  // like checkboxes without nested-interactive violation
  div.setAttribute('role', 'row');
  if (coll && coll.is_smart) div.classList.add('cs-smart');
  if (value === activeVal) {
    div.classList.add('active');
    div.setAttribute('aria-selected', 'true');
  }
  if (coll) div.dataset.id = String(coll.id);

  // Wrap all content in a gridcell (aria-required-children for role="row")
  const cell = document.createElement('div');
  cell.setAttribute('role', 'gridcell');
  cell.style.display = 'contents';

  // Union checkbox (only for real collections, not "All" / "All Favorites")
  if (coll) {
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'cs-union-check';
    cb.name = 'union-checkbox';
    cb.title = _t('collections.union_check', 'Include in UNION search');
    cb.checked = hasUnionCheckedId(coll.id);
    cb.addEventListener('click', (e: MouseEvent) => e.stopPropagation());
    cb.addEventListener('change', () => {
      onUnionCheckChange(coll!.id, cb.checked);
    });
    cell.appendChild(cb);
  }

  // Name
  const nameSpan = document.createElement('span');
  nameSpan.className = 'cs-item-name';
  nameSpan.textContent = (coll && coll.is_smart ? '\uD83D\uDD0D ' : '') + label;
  cell.appendChild(nameSpan);

  // Count (only for manual collections)
  if (coll && !coll.is_smart) {
    const countSpan = document.createElement('span');
    countSpan.className = 'cs-item-count';
    countSpan.textContent = String(coll.count);
    cell.appendChild(countSpan);
  }

  // Action buttons (only for real collections)
  if (coll) {
    const actions = document.createElement('span');
    actions.className = 'cs-actions';

    // Rename
    const renameBtn = document.createElement('button');
    renameBtn.type = 'button';
    renameBtn.className = 'cs-action-btn cs-rename';
    renameBtn.textContent = '\u270F';
    renameBtn.title = _t('collections.rename', 'Rename');
    const collRef = coll;
    renameBtn.addEventListener('click', (e: MouseEvent) => {
      e.stopPropagation();
      startRename(div, collRef);
    });
    actions.appendChild(renameBtn);

    // Export CSV (manual only)
    if (!coll.is_smart) {
      const exportBtn = document.createElement('button');
      exportBtn.type = 'button';
      exportBtn.className = 'cs-action-btn cs-export';
      exportBtn.textContent = '\uD83D\uDCE5';
      exportBtn.title = _t('collections.export_csv', 'Export CSV / Recipe');
      exportBtn.addEventListener('click', (e: MouseEvent) => {
        e.stopPropagation();
        showExportDropdown(exportBtn, collRef);
      });
      actions.appendChild(exportBtn);
    }

    // Delete
    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'cs-action-btn cs-delete';
    deleteBtn.textContent = '\uD83D\uDDD1';
    deleteBtn.title = _t('collections.delete', 'Delete');
    deleteBtn.addEventListener('click', (e: MouseEvent) => {
      e.stopPropagation();
      deleteCollection(collRef);
    });
    actions.appendChild(deleteBtn);

    cell.appendChild(actions);
  }

  div.appendChild(cell);

  // data-value is referenced by the delegated handler (handleListClick)
  div.dataset.value = value;

  return div;
}

/** Event delegation handler installed once on the list container.
 *  The container itself survives DOM rebuilds, so the handler persists. */
export function handleListClick(e: MouseEvent): void {
  const target = e.target as HTMLElement;
  // Ignore clicks on action buttons (.cs-action-btn) or checkboxes
  if (target.closest('.cs-action-btn') || target.closest('.cs-union-check')) return;
  const item = target.closest('.cs-item') as HTMLElement | null;
  if (!item) return;
  const value = item.dataset.value ?? '';
  const id = item.dataset.id;
  if (id) {
    const coll = _collMap.get(id);
    if (coll && coll.is_smart && coll.query_json) {
      applySmartCollection(coll);
      return;
    }
  }
  selectCollection(value);
}

/** Keyboard handler for list items (Enter / Space triggers click). */
export function handleListKeydown(e: KeyboardEvent): void {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const target = e.target as HTMLElement;
  const item = target.closest('.cs-item') as HTMLElement | null;
  if (!item) return;
  e.preventDefault();
  item.click();  // Delegate to the click event
}

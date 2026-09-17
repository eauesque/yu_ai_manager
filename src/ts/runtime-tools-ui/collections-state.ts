/**
 * collections-state.ts -- Shared state, types, and helpers for the
 * collections sidebar module. Split from collections-sidebar.ts to
 * avoid circular dependencies between crud / smart / sidebar files.
 */

import { getAppApi, getSearchResultsApi } from '../shared/browser-apis';

export interface CollectionRecord {
  id: number;
  name: string;
  count: number;
  is_smart?: boolean;
  query_json?: string;
}

// ---- Module-level DOM references (set in initCollectionsSidebar) ----
let _sidebar: HTMLElement | null = null;
let _listEl: HTMLElement | null = null;
let _addInput: HTMLInputElement | null = null;
let _addBtn: HTMLElement | null = null;
let _unionBtn: HTMLButtonElement | null = null;
let _clearUnionBtn: HTMLButtonElement | null = null;

export function getSidebar(): HTMLElement | null { return _sidebar; }
export function getListEl(): HTMLElement | null { return _listEl; }
export function getAddInput(): HTMLInputElement | null { return _addInput; }
export function getAddBtn(): HTMLElement | null { return _addBtn; }
export function getUnionBtn(): HTMLButtonElement | null { return _unionBtn; }
export function getClearUnionBtn(): HTMLButtonElement | null { return _clearUnionBtn; }

export function setSidebar(el: HTMLElement | null): void { _sidebar = el; }
export function setListEl(el: HTMLElement | null): void { _listEl = el; }
export function setAddInput(el: HTMLInputElement | null): void { _addInput = el; }
export function setAddBtn(el: HTMLElement | null): void { _addBtn = el; }
export function setUnionBtn(el: HTMLButtonElement | null): void { _unionBtn = el; }
export function setClearUnionBtn(el: HTMLButtonElement | null): void { _clearUnionBtn = el; }

// ---- Constants ----
export const STORAGE_KEY = 'cs_collapsed';
export const STORAGE_KEY_TAB = 'cs_active_tab';

// ---- i18n helper ----
export function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

// ---- Active collection tracking ----
export function getActiveValue(): string {
  const sel = document.getElementById('collectionFilter') as HTMLSelectElement | null;
  return sel ? sel.value : '';
}

// --- Filter selection ---
export function selectCollection(value: string): void {
  const sel = document.getElementById('collectionFilter') as HTMLSelectElement | null;
  const listEl = getListEl();
  if (sel) {
    // Guard against a known recurring race: the sidebar list and the
    // <select id="collectionFilter"> options are populated by independent
    // async fetches. If the user clicks a sidebar item before
    // loadCollectionFilter() has injected the matching <option>, assigning
    // sel.value silently falls back to "" → collection_id=0 → all files,
    // which manifests as "clicking a collection just reloads the index".
    // Insert the option on the fly from sidebar data so the click works
    // regardless of populate timing.
    if (value && !Array.from(sel.options).some((o) => o.value === value)) {
      const opt = document.createElement('option');
      opt.value = value;
      let label = value;
      if (listEl) {
        const item = listEl.querySelector(`.cs-item[data-value="${CSS.escape(value)}"]`);
        const nameEl = item?.querySelector('.cs-item-name');
        if (nameEl?.textContent) label = nameEl.textContent;
      }
      opt.textContent = label;
      sel.appendChild(opt);
    }
    sel.value = value;
    // Trigger change event for condition-builder
    sel.dispatchEvent(new Event('change', { bubbles: true }));
  }
  // Update active class
  if (listEl) {
    const items = listEl.querySelectorAll('.cs-item');
    items.forEach((item) => { item.classList.remove('active'); });
    const activeItem = Array.from(items).find((item) => {
      const itemEl = item as HTMLElement;
      const itemVal = itemEl.dataset.id || '';
      const nameEl = item.querySelector('.cs-item-name');
      const nameText = nameEl ? nameEl.textContent || '' : '';
      if (value === '' && !itemEl.dataset.id && nameText === _t('collections.all_items', 'All')) return true;
      if (value === 'all' && !itemEl.dataset.id && nameText.indexOf('\u2B50') === 0) return true;
      return itemVal === value;
    });
    if (activeItem) activeItem.classList.add('active');
  }

  // Trigger search
  getSearchResultsApi().runSearch();
}

/**
 * favorites/favorites.ts — Favorite toggle, collection filter, and initialization.
 * Long-press popover logic is in favorites-popover.ts.
 */

import { initPopover, attachLongPress } from './favorites-popover';
import { playSound } from '../../sound';
import { getAppApi, getConditionBuilderApi, getRuntimeToolsApi } from '../../shared/browser-apis';
import { setIconSymbol } from '../../shared/icon';
import { fetchActiveModelState } from '../../tools-page/wd-tagger/retag-modal-active';
import { SEARCH_STATE_KEY } from '../../runtime-init/persistence/core';

/**
 * Toggle a fav button between outline and filled star symbols.
 * Works for both card-fav-btn (.card-fav-icon child) and modal-fav-btn
 * (icon may be a direct .icon child). Falls back to textContent for any
 * legacy buttons that haven't been migrated to SVG yet.
 */
function _setFavButtonState(btn: HTMLElement, isFav: boolean): void {
  const svgEl = btn.querySelector('svg.icon') as SVGSVGElement | null;
  if (svgEl) {
    setIconSymbol(svgEl, isFav ? 'star-filled' : 'star');
  } else {
    btn.textContent = isFav ? '★' : '☆';
  }
  btn.classList.toggle('active', isFav);
}

// Module-level state
const _favSet = new Set<number>();

function _tr(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

/** Toggle favorite for a file ID in a specific collection */
export async function toggleFavorite(
  fileId: number,
  collectionId?: number,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
): Promise<any> {
  collectionId = collectionId || 1;
  try {
    const response = await getAppApi().apiFetch('/api/favorites/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: fileId, collection_id: collectionId }),
    });
    if (!response.ok) return;
    const data = await response.json();
    if (collectionId === 1) {
      if (data.favorited) {
        _favSet.add(fileId);
        playSound('favorite');
      } else {
        _favSet.delete(fileId);
      }
      _updateFavButton(fileId);
      _updateCardStar(fileId, data.favorited);
    }
    getRuntimeToolsApi().refreshCollectionSidebar();
    return data;
  } catch (e) {
    console.error('toggleFavorite failed:', e);
  }
}

/** Check favorites status for a list of IDs and update UI */
export async function checkFavorites(ids: number[]): Promise<void> {
  if (!ids || ids.length === 0) return;
  try {
    const response = await getAppApi().apiFetch('/api/favorites/check?ids=' + ids.join(','));
    if (!response.ok) return;
    const data = await response.json();
    const favIds: number[] = data.favorites || [];
    const favSet = new Set(favIds);
    favIds.forEach((id) => { _favSet.add(id); });
    // Update modal button if open
    const btn = document.getElementById('modalFavBtn') as HTMLElement | null;
    if (btn) {
      const fid = parseInt(btn.dataset.fileId || '0', 10);
      _updateFavButton(fid);
    }
    // Update all card star buttons
    document.querySelectorAll<HTMLElement>('.card-fav-btn[data-file-id]').forEach((cardBtn) => {
      const cid = parseInt(cardBtn.dataset.fileId || '0', 10);
      if (isNaN(cid)) return;
      _setFavButtonState(cardBtn, favSet.has(cid));
    });
  } catch (e) {
    console.error('checkFavorites failed:', e);
  }
}

function _updateFavButton(fileId: number): void {
  const btn = document.getElementById('modalFavBtn') as HTMLElement | null;
  if (!btn) return;
  const btnFid = parseInt(btn.dataset.fileId || '0', 10);
  if (btnFid !== fileId) return;
  const isFav = _favSet.has(fileId);
  _setFavButtonState(btn, isFav);
}

function _updateCardStar(fileId: number, isFav: boolean): void {
  const card = document.querySelector(`.result-card[data-id="${fileId}"]`);
  if (!card) return;
  const btn = card.querySelector('.card-fav-btn') as HTMLElement | null;
  if (!btn) return;
  _setFavButtonState(btn, isFav);
}

/** Called after showDetail loads -- check and update the fav button */
export function updateModalFavButton(fileId: number): void {
  if (_favSet.has(fileId)) {
    _updateFavButton(fileId);
  } else {
    checkFavorites([fileId]);
  }
}

// --- Collection filter ---

interface CollectionInfo {
  id: number;
  name: string;
  count: number;
}

/** Populate collection filter select on search page */
export async function loadCollectionFilter(): Promise<void> {
  const sel = document.getElementById('collectionFilter') as HTMLSelectElement | null;
  if (!sel) return;
  try {
    const response = await getAppApi().apiFetch('/api/collections');
    if (!response.ok) return;
    const data = await response.json();
    const collections: CollectionInfo[] = data.collections || [];
    // Keep the first two static options (--- and All), remove any dynamic ones
    while (sel.options.length > 2) sel.remove(2);
    collections.forEach((coll) => {
      const opt = document.createElement('option');
      opt.value = String(coll.id);
      opt.textContent = coll.name + ' (' + coll.count + ')';
      sel.appendChild(opt);
    });
  } catch (e) {
    console.error('loadCollectionFilter failed:', e);
  }
}

/** Read the persisted wdModelFilter value, if any, from saved search state. */
function _savedWdModelValue(): string | null {
  try {
    const saved = localStorage.getItem(SEARCH_STATE_KEY);
    if (!saved) return null;
    const value = JSON.parse(saved)?.wdModelFilter;
    return typeof value === 'string' ? value : null;
  } catch {
    return null;
  }
}

/** Populate WD-tagger model filter select on search page */
export async function loadWdModelFilter(): Promise<void> {
  const sel = document.getElementById('wdModelFilter') as HTMLSelectElement | null;
  if (!sel) return;
  try {
    const payload = await fetchActiveModelState();
    const previousValue = sel.value;
    // Keep the first two static options (active model / any model), remove any dynamic ones
    while (sel.options.length > 2) sel.remove(2);
    payload.available_models.forEach((model) => {
      const opt = document.createElement('option');
      opt.value = model.model_id;
      opt.textContent = `${model.model_id} (${model.file_count})`;
      sel.appendChild(opt);
    });
    // Model options only exist from here on. Any earlier attempt to select a
    // specific model name (restoreSearchState() on page load, or a value set
    // before this fetch resolved) silently failed since the <option> didn't
    // exist yet — re-apply it now that it does.
    const desiredValue = _savedWdModelValue() ?? previousValue;
    if (desiredValue && Array.from(sel.options).some((opt) => opt.value === desiredValue)) {
      sel.value = desiredValue;
    }
    // If the WD Model condition chip is already showing, its visible <select>
    // was cloned from this element's options when the chip was rendered and
    // won't pick up newly-added model names on its own — refresh it.
    const conditionBuilderApi = getConditionBuilderApi();
    if (conditionBuilderApi.hasCondition('wdModel')) {
      conditionBuilderApi.renderActiveConditions();
    }
  } catch (e) {
    console.error('loadWdModelFilter failed:', e);
  }
}

/**
 * Initialize favorites: set up MutationObserver for modalFavBtn long-press,
 * auto-load collection filter on window.load.
 */
export function initFavorites(): void {
  // Inject toggleFavorite into the popover module (avoids circular dependency)
  initPopover(toggleFavorite);

  // Auto-load collection filter on page init.
  // initFavorites is dispatched via requestIdleCallback, which usually runs
  // AFTER the window 'load' event — so a load listener registered here would
  // never fire. Call immediately when the document is already complete, and
  // fall back to the load listener only when the page is still loading.
  if (document.getElementById('collectionFilter')) {
    if (document.readyState === 'complete') {
      void loadCollectionFilter();
    } else {
      window.addEventListener('load', () => {
        void loadCollectionFilter();
      }, { once: true });
    }
  }

  // Auto-load WD-tagger model filter options on page init (same readiness rules as above).
  if (document.getElementById('wdModelFilter')) {
    if (document.readyState === 'complete') {
      void loadWdModelFilter();
    } else {
      window.addEventListener('load', () => {
        void loadWdModelFilter();
      }, { once: true });
    }
  }

  // Observe for modalFavBtn appearing (scoped to #modal since it only appears inside the modal)
  let _observedBtn: HTMLElement | null = null;
  const modalRoot = document.getElementById('modal');
  if (modalRoot) {
    const observer = new MutationObserver(() => {
      const btn = document.getElementById('modalFavBtn');
      if (btn && btn !== _observedBtn) {
        _observedBtn = btn;
        attachLongPress(btn);
      }
    });
    observer.observe(modalRoot, { childList: true, subtree: true });
  }

  // Also attach if already present
  const existingBtn = document.getElementById('modalFavBtn');
  if (existingBtn) {
    _observedBtn = existingBtn;
    attachLongPress(existingBtn);
  }
}

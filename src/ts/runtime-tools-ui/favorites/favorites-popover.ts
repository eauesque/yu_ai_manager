/**
 * favorites/favorites-popover.ts — Long-press popover for collection selection.
 * Split from favorites.ts to keep each module under 300 lines.
 */

// Dependency injection: toggleFavorite is provided by favorites.ts via initPopover()
// to avoid circular imports.
type ToggleFavoriteFn = (fileId: number, collectionId?: number) => Promise<unknown>;
let _toggleFavoriteFn: ToggleFavoriteFn | null = null;
import { getAppApi, getRuntimeToolsApi } from '../../shared/browser-apis';

// Module-level state
let _longPressTimer: ReturnType<typeof setTimeout> | null = null;
let _longPressFired = false;
let _activePopover: HTMLElement | null = null;

function _tr(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

// --- Popover lifecycle ---

function _closePopover(): void {
  if (_activePopover) {
    _activePopover.remove();
    _activePopover = null;
    document.removeEventListener('mousedown', _onOutsideMousedown);
  }
}

function _onOutsideMousedown(e: MouseEvent): void {
  if (!_activePopover) return;
  if (_activePopover.contains(e.target as Node)) return;
  _closePopover();
}

function _createPopover(fileId: number, anchorEl: HTMLElement): void {
  _closePopover();

  const popover = document.createElement('div');
  popover.className = 'collection-popover';
  popover.style.cssText =
    'position:absolute;z-index:10000;background:var(--bg-card,#2a2a2a);' +
    'border:1px solid var(--border-color,#555);border-radius:8px;padding:8px;' +
    'min-width:200px;max-width:280px;box-shadow:0 4px 16px rgba(0,0,0,0.4);' +
    'font-size:13px;color:var(--text-primary,#eee);';

  popover.innerHTML =
    '<div style="padding:4px 0 6px;font-weight:bold;font-size:12px;opacity:0.7;">Collections</div>' +
    '<div class="collection-list" style="max-height:240px;overflow-y:auto;"></div>' +
    '<div class="collection-new" style="margin-top:6px;display:flex;gap:4px;">' +
    '<input type="text" class="collection-new-input" placeholder="' +
    _tr('collections.new_placeholder', 'New collection name') +
    '" ' +
    'style="flex:1;padding:4px 6px;border:1px solid var(--border-color,#555);border-radius:4px;background:var(--bg-input,#1a1a1a);color:inherit;font-size:12px;" />' +
    '<button class="collection-new-btn" style="padding:4px 8px;border:1px solid var(--border-color,#555);border-radius:4px;background:var(--accent-color,#4a9eff);color:#fff;cursor:pointer;font-size:12px;">' +
    _tr('collections.create', 'Create') +
    '</button>' +
    '</div>';

  // Position relative to anchor
  const rect = anchorEl.getBoundingClientRect();
  const modal = anchorEl.closest('.modal-overlay, .detail-modal, [class*="modal"]') as HTMLElement | null;
  if (modal) {
    modal.style.position = modal.style.position || 'relative';
    popover.style.position = 'fixed';
  } else {
    popover.style.position = 'fixed';
  }
  popover.style.top = (rect.bottom + 4) + 'px';
  popover.style.left = Math.max(8, rect.left - 80) + 'px';

  document.body.appendChild(popover);
  _activePopover = popover;

  // Load collections and check membership
  _loadCollectionList(popover, fileId);

  // Create new collection handler
  const newBtn = popover.querySelector('.collection-new-btn') as HTMLElement;
  const newInput = popover.querySelector('.collection-new-input') as HTMLInputElement;
  newBtn.addEventListener('click', (e: MouseEvent) => {
    e.stopPropagation();
    const name = newInput.value.trim();
    if (!name) return;
    _createCollection(name, popover, fileId);
  });
  newInput.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      const name = newInput.value.trim();
      if (!name) return;
      _createCollection(name, popover, fileId);
    }
    e.stopPropagation();
  });
  // Prevent key events from bubbling to modal
  popover.addEventListener('keydown', (e: KeyboardEvent) => { e.stopPropagation(); });

  // Close on outside mousedown
  setTimeout(() => {
    document.addEventListener('mousedown', _onOutsideMousedown);
  }, 100);
}

// --- Collection list & membership ---

interface CollectionInfo {
  id: number;
  name: string;
  count: number;
}

async function _loadCollectionList(popover: HTMLElement, fileId: number): Promise<void> {
  const listEl = popover.querySelector('.collection-list') as HTMLElement;
  try {
    const { apiFetch } = getAppApi();
    const [collRes, memberRes] = await Promise.all([
      apiFetch('/api/collections').then((r) => r.json()),
      apiFetch('/api/favorites/check_collections?file_id=' + fileId).then((r) => r.json()),
    ]);
    const collections: CollectionInfo[] = collRes.collections || [];
    const memberOf = new Set<number>(memberRes.collections || []);

    listEl.innerHTML = '';
    collections.forEach((coll) => {
      const item = document.createElement('label');
      item.style.cssText = 'display:flex;align-items:center;gap:6px;padding:4px 2px;cursor:pointer;border-radius:4px;';
      item.addEventListener('mouseenter', () => { item.style.background = 'var(--bg-hover,rgba(255,255,255,0.05))'; });
      item.addEventListener('mouseleave', () => { item.style.background = ''; });

      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = memberOf.has(coll.id);
      cb.style.cssText = 'margin:0;cursor:pointer;';
      cb.addEventListener('change', () => {
        _toggleCollectionMembership(fileId, coll.id, cb);
      });

      const nameSpan = document.createElement('span');
      nameSpan.textContent = coll.name;
      nameSpan.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';

      const countSpan = document.createElement('span');
      countSpan.textContent = String(coll.count);
      countSpan.style.cssText = 'opacity:0.5;font-size:11px;';

      item.appendChild(cb);
      item.appendChild(nameSpan);
      item.appendChild(countSpan);
      listEl.appendChild(item);
    });
  } catch (e) {
    listEl.textContent = 'Error loading collections';
    console.error('loadCollectionList failed:', e);
  }
}

async function _toggleCollectionMembership(
  fileId: number,
  collectionId: number,
  checkbox: HTMLInputElement,
): Promise<void> {
  if (!_toggleFavoriteFn) return;
  try {
    const data = await _toggleFavoriteFn(fileId, collectionId);
    if (data && typeof data === 'object' && 'favorited' in data) {
      checkbox.checked = (data as { favorited: boolean }).favorited;
      getRuntimeToolsApi().refreshCollectionSidebar();
    }
  } catch (e) {
    console.error('toggleCollectionMembership failed:', e);
  }
}

async function _createCollection(name: string, popover: HTMLElement, fileId: number): Promise<void> {
  try {
    const response = await getAppApi().apiFetch('/api/collections', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!response.ok) return;
    const input = popover.querySelector('.collection-new-input') as HTMLInputElement | null;
    if (input) input.value = '';
    _loadCollectionList(popover, fileId);
    getRuntimeToolsApi().refreshCollectionSidebar();
  } catch (e) {
    console.error('createCollection failed:', e);
  }
}

// --- Public API ---

/**
 * Initialize the popover module with the toggleFavorite function.
 * Must be called before attachLongPress.
 */
export function initPopover(toggleFavFn: ToggleFavoriteFn): void {
  _toggleFavoriteFn = toggleFavFn;
}

/**
 * Directly open the collection picker popover for a file.
 * Used by the detail modal "Add to Collection" button.
 */
export function showCollectionPickerPopover(fileId: number, anchorEl: HTMLElement): void {
  _createPopover(fileId, anchorEl);
}

/** Attach long-press handler to a favorite button element */
export function attachLongPress(btn: HTMLElement): void {
  btn.addEventListener('pointerdown', (e: PointerEvent) => {
    if (e.button !== 0) return;
    const fileId = parseInt(btn.dataset.fileId || '0', 10);
    if (!fileId) return;

    _longPressTimer = setTimeout(() => {
      _longPressTimer = null;
      _longPressFired = true;
      _createPopover(fileId, btn);
    }, 500);
  });

  btn.addEventListener('pointerup', () => {
    if (_longPressTimer) {
      clearTimeout(_longPressTimer);
      _longPressTimer = null;
    }
  });

  btn.addEventListener('pointerleave', () => {
    if (_longPressTimer) {
      clearTimeout(_longPressTimer);
      _longPressTimer = null;
    }
  });

  // Suppress the click that follows a long-press release
  btn.addEventListener(
    'click',
    (e: MouseEvent) => {
      if (_longPressFired) {
        _longPressFired = false;
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
      }
    },
    true, // capture phase to beat other click handlers
  );
}

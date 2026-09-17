/**
 * favorites/select-actions.ts -- Batch operations for favorites selection mode.
 * Handles add/remove/download/collection batch actions.
 */
import { getRuntimeToolsUiHooks } from '../hooks';

/* -- Helpers -- */

function _getSelectedIds(): number[] {
  const cbs = document.querySelectorAll<HTMLInputElement>('.fav-select-cb:checked');
  const ids: number[] = [];
  cbs.forEach((cb) => {
    ids.push(parseInt(cb.dataset.fileId || '0', 10));
  });
  return ids;
}

export function updateCount(): void {
  const ids = _getSelectedIds();
  const el = document.getElementById('favSelectCount');
  if (el) el.textContent = ids.length + ' selected';
}

function _showToast(msg: string): void {
  const existing = document.querySelector('.fav-select-toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = 'fav-select-toast';
  toast.textContent = msg;
  toast.style.cssText =
    'position:fixed;bottom:30px;left:50%;transform:translateX(-50%);' +
    'background:var(--bg-card,#1b1f2a);border:1px solid var(--border-color,#2b3240);' +
    'padding:10px 24px;border-radius:8px;font-size:13px;z-index:11000;' +
    'box-shadow:0 4px 16px rgba(0,0,0,0.3);transition:opacity 0.3s;';
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; }, 2000);
  setTimeout(() => { if (toast.parentNode) toast.remove(); }, 2500);
}

function _escapeHtml(str: string): string {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/* -- Exported getSelectedIds for use by select-init.ts -- */

export { _getSelectedIds as getSelectedIds };

/* -- Toggle / Select / Deselect -- */

let _selectMode = false;

export function isSelectMode(): boolean { return _selectMode; }
export function setSelectMode(v: boolean): void { _selectMode = v; }

/** Toggle selection mode on/off */
export function favSelectToggle(): void {
  _selectMode = !_selectMode;
  document.body.classList.toggle('fav-select-mode', _selectMode);

  const bar = document.getElementById('favSelectBar');
  const btn = document.getElementById('favSelectModeBtn');
  if (bar) bar.style.display = _selectMode ? 'flex' : 'none';
  if (btn) {
    btn.style.background = _selectMode ? 'var(--accent, #667eea)' : 'transparent';
    btn.style.color = _selectMode ? '#fff' : 'var(--muted)';
  }

  if (!_selectMode) {
    favDeselectAll();
  }
}

/** Called when a checkbox changes -- update count */
export function favSelectChanged(): void {
  updateCount();
}

/** Select all visible cards */
export function favSelectAll(): void {
  const cbs = document.querySelectorAll<HTMLInputElement>('.fav-select-cb');
  cbs.forEach((cb) => { cb.checked = true; });
  updateCount();
}

/** Deselect all */
export function favDeselectAll(): void {
  const cbs = document.querySelectorAll<HTMLInputElement>('.fav-select-cb');
  cbs.forEach((cb) => { cb.checked = false; });
  updateCount();
}

/** Batch add to default favorites */
export function favBatchAdd(): void {
  const ids = _getSelectedIds();
  if (!ids.length) return;

  fetch('/ext/favorites/api/batch-add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_ids: ids, collection_id: 1 }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok) {
        _showToast(
          'Added ' + data.added + ' to favorites' +
          (data.already_existed ? ' (' + data.already_existed + ' already existed)' : ''),
        );
        const hooks = getRuntimeToolsUiHooks();
        hooks.checkFavorites(ids);
        hooks.refreshCollectionSidebar();
      }
    })
    .catch((e) => { console.error('favBatchAdd failed:', e); });
}

/** Batch remove from favorites */
export function favBatchRemove(): void {
  const ids = _getSelectedIds();
  if (!ids.length) return;

  fetch('/ext/favorites/api/batch-remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_ids: ids }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok) {
        _showToast('Removed ' + data.removed + ' from favorites');
        const hooks = getRuntimeToolsUiHooks();
        hooks.checkFavorites(ids);
        hooks.refreshCollectionSidebar();
      }
    })
    .catch((e) => { console.error('favBatchRemove failed:', e); });
}

/** Show collection dropdown for batch-add-to-collection */
export function favShowCollDropdown(anchorBtn: HTMLElement): void {
  const dd = document.getElementById('favCollDropdown');
  if (!dd) return;

  if (dd.style.display !== 'none') {
    dd.style.display = 'none';
    return;
  }

  dd.innerHTML = '<div style="padding:6px 10px;font-size:11px;opacity:0.6;">Loading...</div>';
  dd.style.display = 'block';

  fetch('/api/collections')
    .then((r) => r.json())
    .then((data) => {
      const colls: Array<{ id: number; name: string; count: number }> = data.collections || [];
      let html = '';
      colls.forEach((c) => {
        html += '<button type="button" class="fav-coll-dd-item" data-fav-collection-id="' + String(c.id) + '">';
        html += _escapeHtml(c.name) + ' <span style="opacity:0.5;">(' + c.count + ')</span>';
        html += '</button>';
      });
      if (!colls.length) {
        html = '<div style="padding:8px 10px;font-size:12px;opacity:0.6;">No collections</div>';
      }
      dd.innerHTML = html;
      dd.querySelectorAll<HTMLElement>('[data-fav-collection-id]').forEach((item) => {
        item.addEventListener('click', () => {
          const raw = item.dataset.favCollectionId;
          const collectionId = Number(raw);
          if (!Number.isFinite(collectionId) || collectionId <= 0) return;
          favBatchAddToCollection(collectionId);
        });
      });
    })
    .catch(() => {
      dd.innerHTML = '<div style="padding:8px;color:#f66;">Error</div>';
    });

  // Close on outside click
  setTimeout(() => {
    document.addEventListener('click', function handler(e: MouseEvent) {
      if (!dd.contains(e.target as Node) && e.target !== anchorBtn) {
        dd.style.display = 'none';
        document.removeEventListener('click', handler);
      }
    });
  }, 10);
}

/** Batch download selected files as ZIP */
export function favBatchDownloadZip(): void {
  const ids = _getSelectedIds();
  if (!ids.length) return;

  _showToast('Preparing ZIP...');

  fetch('/api/download/batch-zip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_ids: ids }),
  })
    .then((r) => {
      if (!r.ok) return r.json().then((d: { error?: string }) => { throw new Error(d.error || 'Download failed'); });
      return r.blob();
    })
    .then((blob) => {
      const url = URL.createObjectURL(blob as Blob);
      const a = document.createElement('a');
      a.href = url;
      const disp = 'batch_download.zip';
      a.download = disp;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      _showToast('ZIP downloaded (' + ids.length + ' files)');
    })
    .catch((e: Error) => {
      _showToast('Download failed: ' + e.message);
      console.error('favBatchDownloadZip failed:', e);
    });
}

/** Add selected to a specific collection */
export function favBatchAddToCollection(collectionId: number): void {
  const ids = _getSelectedIds();
  if (!ids.length) return;

  const dd = document.getElementById('favCollDropdown');
  if (dd) dd.style.display = 'none';

  fetch('/ext/favorites/api/batch-add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_ids: ids, collection_id: collectionId }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok) {
        _showToast('Added ' + data.added + ' to collection');
        const hooks = getRuntimeToolsUiHooks();
        hooks.checkFavorites(ids);
        hooks.refreshCollectionSidebar();
      }
    })
    .catch((e) => { console.error('favBatchAddToCollection failed:', e); });
}

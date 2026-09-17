/**
 * tools-page/groups-manager.ts — Group index viewer.
 * Loads /api/groups-index and renders folder/zip group summaries.
 */

import { getAppApi } from '../shared/browser-apis';

interface GroupEntry {
  ids: number[];
  count?: number;
}

interface GroupsIndex {
  folders: Record<string, GroupEntry>;
  zips: Record<string, GroupEntry>;
}

let _loaded = false;

function _setText(id: string, val: string): void {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function _showError(msg: string): void {
  const el = document.getElementById('groupsError');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}

function _buildList(container: HTMLElement, groups: Record<string, GroupEntry>, label: string): void {
  const entries = Object.entries(groups).sort(([, a], [, b]) => (b.ids?.length || 0) - (a.ids?.length || 0));
  if (!entries.length) return;

  const header = document.createElement('div');
  header.style.cssText = 'font-weight:600;color:var(--muted,#888);padding:4px 0;margin-top:8px;';
  header.textContent = label;
  container.appendChild(header);

  entries.slice(0, 50).forEach(([key, entry]) => {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;justify-content:space-between;padding:2px 4px;border-bottom:1px solid rgba(128,128,128,0.08);';
    const nameEl = document.createElement('span');
    nameEl.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:80%;';
    nameEl.textContent = key.split(/[\\/]/).pop() || key;
    nameEl.title = key;
    const countEl = document.createElement('span');
    countEl.style.cssText = 'color:var(--muted,#888);flex-shrink:0;';
    countEl.textContent = String(entry.ids?.length || 0);
    row.appendChild(nameEl);
    row.appendChild(countEl);
    container.appendChild(row);
  });
}

export async function loadGroups(): Promise<void> {
  const { apiFetch } = getAppApi();
  const resultEl = document.getElementById('groupsResult');
  const errorEl = document.getElementById('groupsError');
  const listEl = document.getElementById('groupsList');
  if (errorEl) errorEl.style.display = 'none';

  try {
    const res = await apiFetch('/api/groups-index');
    const raw = await (res as Response).json() as { folders?: Record<string, GroupEntry>; zips?: Record<string, GroupEntry> };
    const data: GroupsIndex = { folders: raw.folders || {}, zips: raw.zips || {} };

    const folderCount = Object.keys(data.folders).length;
    const zipCount = Object.keys(data.zips).length;

    _setText('groupsFolderCount', folderCount.toLocaleString());
    _setText('groupsZipCount', zipCount.toLocaleString());

    if (listEl) {
      listEl.textContent = '';
      const trFn = typeof window.tr === 'function' ? window.tr : null;
      _buildList(listEl, data.folders, (trFn ? trFn('tools.groups_folders_label') : '') || 'Folders (top 50)');
      _buildList(listEl, data.zips, (trFn ? trFn('tools.groups_zips_label') : '') || 'ZIPs (top 50)');
    }

    if (resultEl) resultEl.style.display = 'block';
    _loaded = true;
  } catch (err) {
    _showError(String(err));
  }
}

export async function warmGroupsIndex(): Promise<void> {
  const { apiFetch } = getAppApi();
  const infoEl = document.getElementById('groupsInfo');
  if (infoEl) {
    const trFn = typeof window.tr === 'function' ? window.tr : null;
    infoEl.textContent = (trFn ? trFn('tools.groups_warming') : '') || 'Warming cache...';
  }
  try {
    await apiFetch('/api/groups-index/warm');
    await loadGroups();
    if (infoEl) infoEl.textContent = '';
  } catch (err) {
    if (infoEl) infoEl.textContent = '';
    const el = document.getElementById('groupsError');
    if (el) { el.textContent = String(err); el.style.display = 'block'; }
  }
}

export { _loaded as groupsLoaded };

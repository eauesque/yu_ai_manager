/**
 * dir-browser.ts -- Server directory browser + native folder picker.
 * Converted from tools-server-dir-browser.js
 */

import { getAppApi } from '../shared/browser-apis';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function _escAttr(value: unknown): string {
  return getAppApi()
    .escapeHtml(String(value ?? ''))
    .replace(/"/g, '&quot;');
}

export async function pickFolderNative(): Promise<void> {
  // 1) File System Access API (Chrome/Edge)
  if ((window as unknown as Record<string, unknown>).showDirectoryPicker) {
    try {
      await (window as unknown as { showDirectoryPicker: (opts: Record<string, string>) => Promise<{ name: string }> }).showDirectoryPicker({ mode: 'read' });
      // showDirectoryPicker returns folder name only (security limitation)
      // Full path needed -- fall through to server-side dialog
    } catch (e: unknown) {
      if ((e as { name?: string }).name === 'AbortError') return;
    }
  }

  // 2) Server-side native dialog
  const current = (document.getElementById('scanPath') as HTMLInputElement | null)?.value.trim() || '';
  try {
    const res = await fetch(
      '/api/tools/select-folder' +
        (current ? '?initial=' + encodeURIComponent(current) : ''),
    );
    const data: {
      path?: string;
      cancelled?: boolean;
      error?: string;
      message?: string;
    } = await res.json();
    if (data.path) {
      (document.getElementById('scanPath') as HTMLInputElement).value = data.path;
      return;
    }
    if (data.cancelled) return;
    if (!('cancelled' in data) && !data.error && !data.message) return;
    if (data.message) {
      alert(data.message);
      return;
    }
    if (data.error) {
      alert(
        _t(
          'tools.folder_dialog_failed',
          'Could not open folder picker dialog.\nPlease enter the path manually.',
        ),
      );
      return;
    }
  } catch {
    // fall through
  }

  // 3) Fallback: prompt manual path entry
  alert(
    _t(
      'tools.folder_dialog_failed',
      'Could not open folder picker dialog.\nPlease enter the path manually.',
    ),
  );
}

let _serverDirCurrent = '';
let _serverDirParent: string | null = null;

interface DirEntry {
  name?: string;
  path?: string;
}

interface ListDirsResponse {
  current?: string;
  parent?: string;
  hostname?: string;
  roots?: string[];
  dirs?: DirEntry[];
  error?: string;
}

export async function browseServerPath(path: string): Promise<void> {
  const listEl = document.getElementById('serverDirList');
  const pathEl = document.getElementById('serverDirPath') as HTMLInputElement | null;
  const rootsEl = document.getElementById('serverDirRoots');
  const hostEl = document.getElementById('serverDirHost');
  if (!listEl || !pathEl || !rootsEl) return;
  listEl.innerHTML =
    '<div style="color:#888;font-size:13px;">' +
    _t('tools.loading', 'Loading...') +
    '</div>';
  try {
    const q = path ? '?path=' + encodeURIComponent(path) : '';
    const res = await fetch('/api/tools/list-dirs' + q);
    const data: ListDirsResponse = await res.json();
    if (!res.ok || data.error)
      throw new Error(data.error || `HTTP ${res.status}`);

    _serverDirCurrent = data.current || '';
    _serverDirParent = data.parent || null;
    pathEl.value = _serverDirCurrent;
    if (hostEl) hostEl.textContent = data.hostname ? `(${data.hostname})` : '';

    const roots = Array.isArray(data.roots) ? data.roots : [];
    rootsEl.innerHTML = roots.length
      ? _t('tools.roots', 'Roots') +
        ': ' +
        roots
          .map(
            (r) =>
              `<button type="button" data-browse-server-path="${_escAttr(r)}" style="margin-right:6px;padding:2px 8px;border-radius:12px;border:1px solid rgba(128,128,128,0.35);background:none;color:inherit;cursor:pointer;font-size:11px;">${getAppApi().escapeHtml(r)}</button>`,
          )
          .join('')
      : '';
    rootsEl
      .querySelectorAll<HTMLElement>('[data-browse-server-path]')
      .forEach((button) => {
        button.addEventListener('click', () => {
          browseServerPath(button.dataset.browseServerPath || '');
        });
      });

    const dirs = Array.isArray(data.dirs) ? data.dirs : [];
    if (!dirs.length) {
      listEl.innerHTML =
        '<div style="color:#888;font-size:13px;">' +
        _t('tools.no_subdirs', 'No subdirectories') +
        '</div>';
      return;
    }

    let html = '';
    dirs.forEach((d) => {
      const p = String(d.path || '');
      html += `<div style="display:flex;align-items:center;gap:8px;padding:6px 4px;border-bottom:1px solid rgba(128,128,128,0.14);">
            <span>&#x1F4C1;</span>
            <button type="button" data-browse-server-path="${_escAttr(p)}" style="flex:1;text-align:left;background:none;border:none;color:inherit;cursor:pointer;padding:4px 0;">${getAppApi().escapeHtml(d.name || p)}</button>
            <button type="button" class="btn btn-secondary" data-set-scan-path="${_escAttr(p)}" style="padding:3px 8px;font-size:11px;">${_t('tools.select', 'Select')}</button>
          </div>`;
    });
    listEl.innerHTML = html;
    listEl
      .querySelectorAll<HTMLElement>('[data-browse-server-path]')
      .forEach((button) => {
        button.addEventListener('click', () => {
          browseServerPath(button.dataset.browseServerPath || '');
        });
      });
    listEl
      .querySelectorAll<HTMLElement>('[data-set-scan-path]')
      .forEach((button) => {
        button.addEventListener('click', () => {
          setScanPath(button.dataset.setScanPath || '');
        });
      });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    listEl.innerHTML = `<div style="color:#e74c3c;font-size:13px;">${msg}</div>`;
  }
}

export function setScanPath(path: string): void {
  const el = document.getElementById('scanPath') as HTMLInputElement | null;
  if (el) el.value = path;
}

export function browseServerPathFromInput(): void {
  const path =
    (document.getElementById('serverDirPath') as HTMLInputElement | null)?.value || '';
  void browseServerPath(path);
}

export function browseServerParent(): void {
  if (_serverDirParent) browseServerPath(_serverDirParent);
}

export function openServerDirBrowser(): void {
  const modal = document.getElementById('serverDirModal');
  if (!modal) return;
  modal.style.display = 'flex';
  const current =
    (document.getElementById('scanPath') as HTMLInputElement | null)?.value.trim() || '';
  browseServerPath(current || '');
}

export function closeServerDirBrowser(): void {
  const modal = document.getElementById('serverDirModal');
  if (modal) modal.style.display = 'none';
}

export function selectCurrentServerDir(): void {
  const p =
    (document.getElementById('serverDirPath') as HTMLInputElement | null)?.value?.trim() || '';
  if (p) {
    const el = document.getElementById('scanPath') as HTMLInputElement | null;
    if (el) el.value = p;
  }
  closeServerDirBrowser();
}

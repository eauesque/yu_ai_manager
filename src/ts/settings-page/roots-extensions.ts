/**
 * Settings page — scan roots management.
 */

import { getAppApi } from '../shared/browser-apis';
import * as rootsRender from './roots-render';
import type { ScanRoot } from './roots-render';
import { checkScanRootsRecovery } from '../tools-page/roots/recovery';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

/* ---- Scan Roots ---- */

export async function loadScanRoots(): Promise<void> {
  const div = document.getElementById('scanRootsList');
  if (!div) return;
  try {
    const res = await fetch('/api/scan-roots');
    const data = await res.json();
    const roots: ScanRoot[] = data.roots || [];

    if (roots.length === 0) {
      div.innerHTML = rootsRender.emptyHtml();
      void checkScanRootsRecovery(div, loadScanRoots);
      return;
    }
    div.innerHTML = rootsRender.buildRootsHtml(roots);
  } catch {
    div.innerHTML = rootsRender.errorHtml();
  }
}

let _lastAddedPath = '';

export async function addScanRoot(): Promise<void> {
  const input = document.getElementById('newRootPath') as HTMLInputElement | null;
  const commentInput = document.getElementById('newRootComment') as HTMLInputElement | null;
  const path = (input?.value || '').trim();
  if (!path) return;
  const comment = (commentInput?.value || '').trim();
  const res = await fetch('/api/scan-roots', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify({ path, recursive: true, enabled: true, comment }),
  });
  if (input) input.value = '';
  if (commentInput) commentInput.value = '';
  loadScanRoots();

  if (res.ok) {
    _lastAddedPath = path;
    const banner = document.getElementById('addRootScanBanner');
    if (banner) {
      banner.style.display = 'flex';
      const msg = document.getElementById('addRootScanMsg');
      if (msg) msg.textContent = _t('settings.root_added_msg', 'フォルダを追加しました') + ': ' + path;
    }
  }
}

export async function scanAddedRoot(): Promise<void> {
  if (!_lastAddedPath) return;
  dismissAddRootBanner();
  await fetch('/api/scan/start', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify({ root: _lastAddedPath, recursive: true }),
  });
  _lastAddedPath = '';
  // Navigate user to Tools > Scan & Config tab
  const toolsLink = document.querySelector<HTMLAnchorElement>('a[href="/tools"]');
  if (toolsLink) {
    toolsLink.click();
  }
}

export function dismissAddRootBanner(): void {
  const banner = document.getElementById('addRootScanBanner');
  if (banner) banner.style.display = 'none';
}

export async function saveRootComment(i: number): Promise<void> {
  const input = document.getElementById('rootComment' + i) as HTMLInputElement | null;
  const comment = (input?.value || '').trim();
  await fetch('/api/scan-roots/' + i, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify({ comment }),
  });
}

export async function toggleScanRoot(i: number): Promise<void> {
  await fetch('/api/scan-roots/' + i + '/toggle', {
    method: 'POST',
    headers: XHR_HEADERS,
  });
  loadScanRoots();
}

export async function removeScanRoot(i: number): Promise<void> {
  if (!confirm(_t('settings.remove_root_confirm', 'Unregister this folder?'))) return;
  await fetch('/api/scan-roots/' + i, {
    method: 'DELETE',
    headers: XHR_HEADERS,
  });
  loadScanRoots();
}

export async function saveRootPath(i: number): Promise<void> {
  const input = document.getElementById('rootPath' + i) as HTMLInputElement | null;
  const newPath = (input?.value || '').trim();
  if (!newPath) return;

  try {
    const res = await fetch('/api/scan-roots/' + i, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ path: newPath }),
    });
    const data = await res.json();
    if (data.success) {
      const status = document.getElementById('saveStatus');
      if (status) status.textContent = '\u2705 ' + _t('settings.path_updated', 'Path updated') + ': ' + data.root.path;
      if (input) {
        input.style.borderColor = '#2ecc71';
        setTimeout(() => { input.style.borderColor = ''; }, 2000);
      }
    } else {
      alert(_t('settings.error', 'Error') + ': ' + (data.error || _t('settings.unknown', 'Unknown')));
    }
  } catch (err) {
    alert(_t('settings.save_failed', 'Save failed') + ': ' + (err instanceof Error ? err.message : String(err)));
  }
}

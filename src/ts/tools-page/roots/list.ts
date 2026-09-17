/**
 * roots/list.ts -- Scan roots list loading and rendering.
 * Converted from tools-roots-list.js
 */

import { getAppApi } from '../../shared/browser-apis';
import { apiFetch } from '../api';
import {
  rootsData,
  selectedRootIdx,
  setSelectedRootIdx,
  setRootsData,
  type ScanRoot,
} from './state';
import { showRescanDialog } from './rescan';
import { checkScanRootsRecovery } from './recovery';
import {
  onRootDragStart,
  onRootDragOver,
  onRootDragEnter,
  onRootDragLeave,
  onRootDrop,
  onRootDragEnd,
  onRootKeydown,
  toggleRoot,
  removeRoot,
} from './reorder';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export async function loadScanRoots(): Promise<void> {
  try {
    const response = await apiFetch('/api/scan-roots');
    const data: { roots?: ScanRoot[] } = await response.json();
    const container = document.getElementById('rootsList');
    if (!container) return;

    setRootsData(data.roots || []);

    if (rootsData.length === 0) {
      container.innerHTML =
        '<span style="color: #666;">' +
        _t('tools.no_registered_roots', 'No registered folders') +
        '</span>';
      void checkScanRootsRecovery(container, loadScanRoots);
      return;
    }

    renderRoots();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    const el = document.getElementById('rootsList');
    if (el) {
      el.innerHTML =
        '<span style="color: #e74c3c;">' +
        _t('tools.load_failed', 'Load failed') +
        ': ' +
        msg +
        '</span>';
    }
  }
}

export function renderRoots(): void {
  const container = document.getElementById('rootsList');
  if (!container) return;

  let html =
    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">' +
    '<span style="font-size:11px;color:#555;flex:1;">' +
    _t(
      'tools.roots_drag_hint',
      'Drag to reorder | Shift+\u2191\u2193 to move | Order affects folder sort',
    ) +
    '</span>' +
    '<button type="button" class="batch-toggle-btn" data-batch-enable="true" style="font-size:11px;padding:2px 8px;border:1px solid rgba(128,128,128,0.3);border-radius:4px;background:transparent;color:var(--muted);cursor:pointer;">' +
    _t('tools.enable_all', 'Enable All') +
    '</button>' +
    '<button type="button" class="batch-toggle-btn" data-batch-enable="false" style="font-size:11px;padding:2px 8px;border:1px solid rgba(128,128,128,0.3);border-radius:4px;background:transparent;color:var(--muted);cursor:pointer;">' +
    _t('tools.disable_all', 'Disable All') +
    '</button>' +
    '</div>';

  rootsData.forEach((root, idx) => {
    const enabled = root.enabled !== false;
    const statusIcon = enabled ? '\u2705' : '\u23F8\uFE0F';
    const opacity = enabled ? '1' : '0.5';
    const comment = root.comment
      ? ` <span style="color:#666;">(${root.comment})</span>`
      : '';
    const recursive = root.recursive ? ' \uD83D\uDD04' : '';
    const notExists = root.exists === false;
    const existsWarn = notExists
      ? ` <span style="color:#e74c3c;font-size:11px;" title="${_t('tools.path_not_found', 'Path not found')}">&#x26A0; ${_t('tools.path_not_found', 'Path not found')}</span>`
      : '';
    const fc = root.file_count ?? 0;
    const fileCountBadge =
      fc > 0
        ? `<span style="color:#667eea;font-size:12px;white-space:nowrap;">${fc.toLocaleString()} ${_t('tools.items', 'items')}</span>`
        : `<span style="color:#555;font-size:12px;white-space:nowrap;">0</span>`;
    const selected = idx === selectedRootIdx;
    const border = selected
      ? 'border:1px solid #667eea;'
      : 'border:1px solid transparent;';
    const toggleTitle = enabled
      ? _t('tools.disable', 'Disable')
      : _t('tools.enable', 'Enable');

    html += `<div class="root-item" draggable="true" data-idx="${idx}" tabindex="0"
              style="padding:8px 12px;margin:3px 0;background:rgba(255,255,255,0.03);border-radius:5px;display:flex;align-items:center;gap:8px;opacity:${opacity};cursor:grab;transition:all 0.15s;${border}"
              >
            <span style="cursor:grab;color:#555;font-size:14px;" title="${_t('tools.drag_to_move', 'Drag to move')}">&#x2630;</span>
            <span style="font-size:13px;">${idx + 1}.</span>
            <span>${statusIcon}</span>
            <span style="flex:1;word-break:break-all;font-size:13px;">${root.path}${comment}${recursive}${existsWarn}</span>
            ${fileCountBadge}
            <button class="rescan-root-btn" data-idx="${idx}" title="${_t('tools.rescan', 'Rescan')}" style="background:none;border:none;cursor:pointer;font-size:14px;color:#166534;">&#x1F504;</button>
            <button class="toggle-root-btn" data-idx="${idx}" title="${toggleTitle}" style="background:none;border:none;cursor:pointer;font-size:14px;">${enabled ? '\u23F8\uFE0F' : '\u25B6\uFE0F'}</button>
            <button class="remove-root-btn" data-idx="${idx}" title="${_t('tools.delete', 'Delete')}" style="background:none;border:none;cursor:pointer;font-size:14px;">&#x1F5D1;\uFE0F</button>
          </div>`;
  });

  container.innerHTML = html;

  container.querySelectorAll<HTMLElement>('.root-item').forEach((item) => {
    const idx = parseInt(item.dataset.idx || '-1', 10);
    if (idx < 0) return;
    item.addEventListener('dragstart', (e) => onRootDragStart(e, idx));
    item.addEventListener('dragover', onRootDragOver);
    item.addEventListener('dragenter', onRootDragEnter);
    item.addEventListener('dragleave', onRootDragLeave);
    item.addEventListener('drop', (e) => onRootDrop(e, idx));
    item.addEventListener('dragend', onRootDragEnd);
    item.addEventListener('focus', () => setSelectedRootIdx(idx));
    item.addEventListener('keydown', (e) => onRootKeydown(e, idx));
  });

  container.querySelectorAll<HTMLButtonElement>('.rescan-root-btn').forEach((btn) => {
    btn.addEventListener('click', (e: MouseEvent) => {
      e.stopPropagation();
      const idx = parseInt(btn.dataset.idx || '0', 10);
      if (rootsData[idx]) showRescanDialog(rootsData[idx].path);
    });
  });

  container.querySelectorAll<HTMLButtonElement>('.toggle-root-btn').forEach((btn) => {
    btn.addEventListener('click', (e: MouseEvent) => {
      e.stopPropagation();
      const idx = parseInt(btn.dataset.idx || '-1', 10);
      if (idx >= 0) void toggleRoot(idx);
    });
  });

  container.querySelectorAll<HTMLButtonElement>('.remove-root-btn').forEach((btn) => {
    btn.addEventListener('click', (e: MouseEvent) => {
      e.stopPropagation();
      const idx = parseInt(btn.dataset.idx || '-1', 10);
      if (idx >= 0) void removeRoot(idx);
    });
  });

  // Batch enable/disable all
  container.querySelectorAll<HTMLButtonElement>('.batch-toggle-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const enabled = btn.dataset.batchEnable === 'true';
      try {
        await apiFetch('/api/scan-roots/batch-toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled }),
        });
        await loadScanRoots();
      } catch (e) {
        console.error('Batch toggle failed:', e);
      }
    });
  });
}

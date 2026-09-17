/**
 * roots/reorder.ts -- Drag-and-drop reorder + keyboard reorder + toggle/remove actions.
 * Merged from tools-roots-reorder.js and tools-roots-reorder-actions.js
 */

import { getAppApi, getNavApi } from '../../shared/browser-apis';
import { apiFetch } from '../api';
import { loadDbInfo, loadTagCount } from '../db-info';
import {
  rootsData,
  dragIdx,
  setDragIdx,
  setSelectedRootIdx,
} from './state';
import { renderRoots, loadScanRoots } from './list';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

// --- Drag-and-drop handlers ---

export function onRootDragStart(e: DragEvent, idx: number): void {
  setDragIdx(idx);
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  const target = e.target as HTMLElement;
  target.style.opacity = '0.4';
}

export function onRootDragOver(e: DragEvent): void {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
}

export function onRootDragEnter(e: DragEvent): void {
  const item = (e.target as HTMLElement).closest('.root-item') as HTMLElement | null;
  if (item) item.style.borderTop = '2px solid #667eea';
}

export function onRootDragLeave(e: DragEvent): void {
  const item = (e.target as HTMLElement).closest('.root-item') as HTMLElement | null;
  if (item) item.style.borderTop = '';
}

export function onRootDrop(e: DragEvent, dropIdx: number): void {
  e.preventDefault();
  const item = (e.target as HTMLElement).closest('.root-item') as HTMLElement | null;
  if (item) item.style.borderTop = '';

  if (dragIdx === -1 || dragIdx === dropIdx) return;

  const moved = rootsData.splice(dragIdx, 1)[0];
  rootsData.splice(dropIdx, 0, moved);
  setSelectedRootIdx(dropIdx);
  renderRoots();
  saveRootOrder();
}

export function onRootDragEnd(e: DragEvent): void {
  (e.target as HTMLElement).style.opacity = '';
  setDragIdx(-1);
  document.querySelectorAll<HTMLElement>('.root-item').forEach((el) => {
    el.style.borderTop = '';
  });
}

// --- Keyboard reorder ---

export function onRootKeydown(e: KeyboardEvent, idx: number): void {
  if (e.shiftKey && e.key === 'ArrowUp' && idx > 0) {
    e.preventDefault();
    swapRoots(idx, idx - 1);
    setSelectedRootIdx(idx - 1);
    renderRoots();
    saveRootOrder();
    setTimeout(() => {
      const items = document.querySelectorAll<HTMLElement>('.root-item');
      if (items[idx - 1]) items[idx - 1].focus();
    }, 50);
  }

  if (e.shiftKey && e.key === 'ArrowDown' && idx < rootsData.length - 1) {
    e.preventDefault();
    swapRoots(idx, idx + 1);
    setSelectedRootIdx(idx + 1);
    renderRoots();
    saveRootOrder();
    setTimeout(() => {
      const items = document.querySelectorAll<HTMLElement>('.root-item');
      if (items[idx + 1]) items[idx + 1].focus();
    }, 50);
  }

  if (!e.shiftKey && e.key === 'ArrowUp' && idx > 0) {
    e.preventDefault();
    const items = document.querySelectorAll<HTMLElement>('.root-item');
    if (items[idx - 1]) items[idx - 1].focus();
  }

  if (!e.shiftKey && e.key === 'ArrowDown' && idx < rootsData.length - 1) {
    e.preventDefault();
    const items = document.querySelectorAll<HTMLElement>('.root-item');
    if (items[idx + 1]) items[idx + 1].focus();
  }
}

// --- Swap / save / toggle / remove ---

function swapRoots(a: number, b: number): void {
  [rootsData[a], rootsData[b]] = [rootsData[b], rootsData[a]];
}

export async function saveRootOrder(): Promise<void> {
  try {
    await apiFetch('/api/scan-roots/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roots: rootsData }),
    });
  } catch (err) {
    console.error('Reorder save failed:', err);
  }
}

export async function toggleRoot(index: number): Promise<void> {
  try {
    await apiFetch(`/api/scan-roots/${index}/toggle`, { method: 'POST' });
    loadScanRoots();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    alert(_t('tools.toggle_failed', 'Toggle failed') + ': ' + msg);
  }
}

export async function removeRoot(index: number): Promise<void> {
  if (
    !confirm(
      _t(
        'tools.remove_root_confirm',
        'Unregister this folder and delete its DB records?',
      ),
    )
  )
    return;

  // Disable buttons and fade row while request is in-flight
  const row = document.querySelector<HTMLElement>(`.root-item[data-idx="${index}"]`);
  const buttons = row ? row.querySelectorAll<HTMLButtonElement>('button') : [];
  if (row) row.style.opacity = '0.4';
  buttons.forEach((b) => (b.disabled = true));

  try {
    const resp = await apiFetch(`/api/scan-roots/${index}`, { method: 'DELETE' });
    const data = await resp.json();
    const removed = data.removed || {};
    const folderName = (removed.path || '').replace(/.*[/\\]/, '') || 'folder';
    const purged = removed.purged ?? 0;

    // Remove row from DOM immediately
    if (row) row.remove();

    // Toast notification
    const toast = `Removed: ${folderName} (${purged} records purged)`;
    getNavApi().showToast(toast);

    loadScanRoots();
    loadDbInfo();
    loadTagCount();
  } catch (err: unknown) {
    // Restore row on failure
    if (row) row.style.opacity = '';
    buttons.forEach((b) => (b.disabled = false));
    const msg = err instanceof Error ? err.message : String(err);
    getNavApi().showToast(_t('tools.delete_failed', 'Delete failed') + ': ' + msg, true);
  }
}

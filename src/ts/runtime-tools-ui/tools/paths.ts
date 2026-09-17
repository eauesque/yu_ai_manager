/**
 * tools/paths.ts — File path display, copy, and checkpoint search helpers.
 * Converted from runtime-tools-paths.js
 */

import { copyWithFeedback } from './copy';
import { getRuntimeToolsUiHooks } from '../hooks';
import { getAppApi, getConditionBuilderApi, getNavApi } from '../../shared/browser-apis';

interface ZipPathInfo {
  zipPath: string | null;
  zipName: string | null;
  innerPath: string | null;
  fileName: string;
  isZip: boolean;
  fullPath: string;
}

export async function openFileDirectory(fileId: number): Promise<void> {
  if (!fileId) return;
  const { apiFetch, tr } = getAppApi();
  const { showToast } = getNavApi();
  try {
    const response = await apiFetch(`/api/open-folder/${fileId}`, { method: 'POST' });
    const data = await response.json();
    if (data.success) showToast(tr('toast.dir_opened'));
    else showToast(data.error || tr('toast.dir_open_failed'), true);
  } catch (err) {
    console.error('Error opening directory:', err);
    showToast(tr('toast.error_occurred'), true);
  }
}

export function formatZipPath(fullPath: string): ZipPathInfo {
  const zipMatch = fullPath.match(/^(.+\.zip)!(.+)$/i);
  if (zipMatch) {
    const zipPath = zipMatch[1];
    const innerPath = zipMatch[2];
    const zipName = zipPath.split(/[/\\]/).pop() || '';
    const fileName = innerPath.split(/[/\\]/).pop() || '';
    return { zipPath, zipName, innerPath, fileName, isZip: true, fullPath };
  }
  const fileName = fullPath.split(/[/\\]/).pop() || '';
  return { zipPath: null, zipName: null, innerPath: null, fileName, isZip: false, fullPath };
}

export function renderPathDisplay(fullPath: string, fileId: number): string {
  const { escapeHtml, tr } = getAppApi();
  const p = formatZipPath(fullPath);
  if (p.isZip) {
    const zipB64 = btoa(unescape(encodeURIComponent(p.zipPath!)));
    const fileB64 = btoa(unescape(encodeURIComponent(p.fileName)));
    return `
      <span class="file-path-label">${escapeHtml(tr('path.label'))}</span>
      <span class="file-path-clickable copy-target" data-copy-b64="${zipB64}" data-copy-label="${escapeHtml(tr('path.copy_label_zip'))}" title="${escapeHtml(tr('path.copy_title_zip'))}" style="position:relative;">${escapeHtml(p.zipName!)}</span>
      <span style="color:#888;margin:0 2px;">/</span>
      <span class="file-path-clickable copy-target" data-copy-b64="${fileB64}" data-copy-label="${escapeHtml(tr('path.copy_label_filename'))}" title="${escapeHtml(tr('path.copy_title_filename'))}" style="position:relative;">${escapeHtml(p.fileName)}</span>
    `;
  }
  const pathB64 = btoa(unescape(encodeURIComponent(fullPath)));
  return `
    <span class="file-path-label">${escapeHtml(tr('path.label'))}</span>
    <span class="file-path-clickable copy-target" data-copy-b64="${pathB64}" data-copy-label="${escapeHtml(tr('path.copy_label'))}" title="${escapeHtml(tr('path.copy_title'))}" style="position:relative;">${escapeHtml(fullPath)}</span>
  `;
}

export function renderFileName(fullPath: string): string {
  const { escapeHtml } = getAppApi();
  const p = formatZipPath(fullPath);
  if (p.isZip) return `${escapeHtml(p.zipName!)} / ${escapeHtml(p.fileName)}`;
  return escapeHtml(p.fileName);
}

export async function copySeed(seed: string | number, event?: Event): Promise<void> {
  await copyWithFeedback(String(seed), (event?.target as HTMLElement) || null, 'Seed ');
}

export async function searchByCheckpoint(modelName: string, event?: Event): Promise<void> {
  if (!modelName) return;
  const { tr } = getAppApi();
  const { showToast } = getNavApi();
  const { hasCondition, activateCondition } = getConditionBuilderApi();
  getRuntimeToolsUiHooks().closeModal();
  const checkpointInput = document.getElementById('checkpointFilter') as HTMLInputElement | null;
  if (checkpointInput) checkpointInput.value = modelName;

  if (!hasCondition('checkpoint')) {
    activateCondition('checkpoint');
  }

  requestAnimationFrame(() => {
    const chipInputs = document.querySelectorAll<HTMLInputElement>(
      '.condition-field[data-key="checkpoint"] input[type="text"]',
    );
    chipInputs.forEach((inp) => {
      inp.value = modelName;
    });
  });

  getRuntimeToolsUiHooks().runSearch();
  showToast(tr('toast.checkpoint_search', { model: modelName }));
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

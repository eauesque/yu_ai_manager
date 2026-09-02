/**
 * duplicates/delete.ts -- Duplicate file deletion (soft and hard).
 * Converted from tools-duplicates-delete.js
 */

import { getAppApi } from '../../shared/browser-apis';
import { getDuplicateData } from '../../shared/runtime-state/duplicate-data-state';
import { apiFetch } from '../api';
import { loadDbInfo } from '../db-info';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

interface DeletionGroup {
  files: string[];
  deleteFiles: string[];
}

function _getSelectedFilesForDeletion(): {
  groups: DeletionGroup[];
  totalSelected: number;
} {
  const selected: Record<string, string[]> = {};
  document
    .querySelectorAll<HTMLInputElement>('.dupe-check-path:checked')
    .forEach((cb) => {
      const g = cb.dataset.group || '';
      const path = cb.dataset.path || '';
      if (!selected[g]) selected[g] = [];
      selected[g].push(path);
    });

  const groups: DeletionGroup[] = [];
  let totalSelected = 0;
  for (const [gIdx, paths] of Object.entries(selected)) {
    if (paths.length > 0) {
      const origGroup = getDuplicateData()?.groups[parseInt(gIdx, 10)];
      if (!origGroup) continue;
      const keepFiles = origGroup.files.filter((f: string) => !paths.includes(f));
      groups.push({
        files: [...keepFiles, ...paths],
        deleteFiles: paths,
      });
      totalSelected += paths.length;
    }
  }
  return { groups, totalSelected };
}

export async function deleteDuplicates(): Promise<void> {
  if (!getDuplicateData()) return;
  const { groups, totalSelected } = _getSelectedFilesForDeletion();

  if (totalSelected === 0) {
    alert(_t('tools.select_files_to_delete', 'Please select files to delete'));
    return;
  }
  if (
    !confirm(
      _t(
        'tools.confirm_db_delete',
        'Delete {count} files from database.\n(Actual files will remain on disk)',
      ).replace('{count}', String(totalSelected)),
    )
  )
    return;

  await _executeDeletion('soft', groups);
}

export async function deleteDuplicatesHard(): Promise<void> {
  if (!getDuplicateData()) return;
  const { groups, totalSelected } = _getSelectedFilesForDeletion();

  if (totalSelected === 0) {
    alert(_t('tools.select_files_to_delete', 'Please select files to delete'));
    return;
  }
  if (
    !confirm(
      _t(
        'tools.confirm_hard_delete',
        'Warning: Permanently delete {count} files.\nThis cannot be undone!\n\nAre you sure?',
      ).replace('{count}', String(totalSelected)),
    )
  )
    return;

  await _executeDeletion('hard', groups);
}

async function _executeDeletion(
  mode: 'soft' | 'hard',
  groups: DeletionGroup[],
): Promise<void> {
  const resultBox = document.getElementById('duplicatesResult');
  if (!resultBox) return;
  resultBox.innerHTML =
    '<div class="spinner-overlay"><div class="spinner"></div><span class="spinner-text">' +
    _t('tools.deleting', 'Deleting...') +
    '</span></div>';

  const apiGroups = groups.map((g) => ({
    files: ['__keep__', ...g.deleteFiles],
  }));

  try {
    const response = await apiFetch('/api/tools/delete-duplicates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ groups: apiGroups, mode }),
    });

    const data: { deleted: number; errors?: string[] } = await response.json();
    let msg =
      '\u2713 ' +
      _t('tools.files_deleted', '{count} files deleted').replace(
        '{count}',
        String(data.deleted),
      );
    if (mode === 'hard')
      msg +=
        ' (' +
        _t('tools.actual_files_deleted', 'actual files also deleted') +
        ')';
    if (data.errors?.length)
      msg +=
        '<br><span style="color:#e67e22;">\u26A0 ' +
        _t('tools.deletion_errors', '{count} errors').replace(
          '{count}',
          String(data.errors.length),
        ) +
        '</span>';

    resultBox.innerHTML = `<p style="color: #2ecc71;">${msg}</p>`;
    const delBtn = document.getElementById('deleteDuplicatesBtn') as HTMLButtonElement | null;
    const delHardBtn = document.getElementById('deleteDuplicatesHardBtn') as HTMLButtonElement | null;
    if (delBtn) delBtn.disabled = true;
    if (delHardBtn) delHardBtn.disabled = true;
    loadDbInfo();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    resultBox.innerHTML =
      '<p style="color: #e74c3c;">' +
      _t('tools.error', 'Error') +
      ': ' +
      msg +
      '</p>';
  }
}

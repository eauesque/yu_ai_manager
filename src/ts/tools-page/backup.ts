/**
 * backup.ts -- Database backup download and restore.
 * Converted from tools-backup.js
 */

import { getAppApi } from '../shared/browser-apis';
import { apiFetch } from './api';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export function downloadBackup(): void {
  window.location.href = '/api/tools/backup-download';
}

export function triggerRestoreFile(): void {
  document.getElementById('restoreFileInput')?.click();
}

export function restoreBackup(input: HTMLInputElement): void {
  const file = input.files?.[0];
  if (!file) return;

  if (
    !confirm(
      _t(
        'tools.backup_restore_confirm',
        'This will replace the current database. A backup of the current DB will be created automatically. Continue?',
      ),
    )
  ) {
    input.value = '';
    return;
  }

  const statusEl = document.getElementById('backupStatus');
  if (statusEl)
    statusEl.textContent = _t('tools.backup_restoring', 'Restoring...');

  const fd = new FormData();
  fd.append('file', file);

  apiFetch('/api/tools/restore', { method: 'POST', body: fd })
    .then((r) => r.json())
    .then((data: { error?: string }) => {
      if (data.error) {
        if (statusEl) statusEl.textContent = '\u274C ' + data.error;
      } else {
        if (statusEl)
          statusEl.textContent =
            '\u2705 ' +
            _t(
              'tools.backup_restore_success',
              'Database restored successfully. Reloading...',
            );
        setTimeout(() => {
          location.reload();
        }, 1500);
      }
    })
    .catch((e: Error) => {
      if (statusEl) statusEl.textContent = '\u274C ' + e.message;
    })
    .finally(() => {
      input.value = '';
    });
}

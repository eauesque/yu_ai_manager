/**
 * backup-manager.ts -- Managed backup UI (create, list, restore, delete).
 */

import { getAppApi } from '../shared/browser-apis';
import { apiFetch } from './api';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

interface BackupEntry {
  filename: string;
  size_bytes: number;
  reason: string;
  created_at: string;
  schema_version: number | null;
}

interface BackupListResponse {
  backups: BackupEntry[];
  count: number;
}

interface BackupStatusResponse {
  enabled: boolean;
  backup_on_scan_complete: boolean;
  periodic_interval_hours: number;
  max_generations: number;
  cooldown_minutes: number;
  scheduler_running: boolean;
  last_backup_time: number | null;
  within_cooldown: boolean;
}

function _formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function _formatReason(reason: string): string {
  const map: Record<string, string> = {
    manual: 'Manual',
    scheduled: 'Scheduled',
    scan_complete: 'Scan Complete',
    pre_restore: 'Pre-Restore',
    pre_migrate: 'Pre-Migrate',
  };
  return map[reason] || reason;
}

function _formatDate(iso: string): string {
  if (!iso) return '-';
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export async function loadBackupList(): Promise<void> {
  const container = document.getElementById('backupListContainer');
  if (!container) return;

  try {
    const resp = await apiFetch('/api/tools/backup/list');
    // "Unavailable" is not "empty". The server answers 503 when the backup
    // subsystem is not running (it lives in the Python extension), and reading
    // that as an empty list told people they had no backups -- the one wrong
    // answer here that can cost data.
    if (!resp.ok) {
      // textContent, not innerHTML: this is plain text and needs no markup.
      const note = document.createElement('p');
      note.style.cssText = 'color:var(--text-muted);font-size:0.9em;';
      note.textContent = _t(
        'tools.backup_unavailable',
        'Backup management is unavailable on this server.',
      );
      container.replaceChildren(note);
      return;
    }
    const data: BackupListResponse = await resp.json();
    const backups = data.backups || [];

    if (backups.length === 0) {
      container.innerHTML =
        '<p style="color:var(--text-muted);font-size:0.9em;">' +
        _t('tools.backup_no_backups', 'No backups found.') +
        '</p>';
      return;
    }

    let html =
      '<table class="backup-table" style="width:100%;border-collapse:collapse;font-size:0.85em;">' +
      '<thead><tr>' +
      '<th style="text-align:left;padding:4px 8px;">' + _t('tools.backup_col_file', 'File') + '</th>' +
      '<th style="text-align:left;padding:4px 8px;">' + _t('tools.backup_col_date', 'Date') + '</th>' +
      '<th style="text-align:right;padding:4px 8px;">' + _t('tools.backup_col_size', 'Size') + '</th>' +
      '<th style="text-align:left;padding:4px 8px;">' + _t('tools.backup_col_reason', 'Reason') + '</th>' +
      '<th style="text-align:center;padding:4px 8px;">' + _t('tools.backup_col_actions', 'Actions') + '</th>' +
      '</tr></thead><tbody>';

    for (const b of backups) {
      html +=
        '<tr>' +
        `<td style="padding:4px 8px;word-break:break-all;">${_escHtml(b.filename)}</td>` +
        `<td style="padding:4px 8px;white-space:nowrap;">${_formatDate(b.created_at)}</td>` +
        `<td style="padding:4px 8px;text-align:right;white-space:nowrap;">${_formatSize(b.size_bytes)}</td>` +
        `<td style="padding:4px 8px;">${_escHtml(_formatReason(b.reason))}</td>` +
        '<td style="padding:4px 8px;text-align:center;white-space:nowrap;">' +
        `<button class="btn btn-sm" data-action="toolsPageApi.restoreFromBackup" data-action-arg="${_escAttr(b.filename)}" title="Restore">` +
        '<span aria-hidden="true">&#x1F504;</span></button> ' +
        `<button class="btn btn-sm btn-danger" data-action="toolsPageApi.deleteBackupFile" data-action-arg="${_escAttr(b.filename)}" title="Delete">` +
        '<span aria-hidden="true">&#x1F5D1;</span></button>' +
        '</td></tr>';
    }
    html += '</tbody></table>';
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML =
      '<p style="color:var(--danger);">' +
      _t('tools.backup_list_error', 'Failed to load backup list.') +
      '</p>';
  }
}

export async function createManualBackup(): Promise<void> {
  const statusEl = document.getElementById('backupManagedStatus');
  if (statusEl) statusEl.textContent = _t('tools.backup_creating', 'Creating backup...');

  try {
    const resp = await apiFetch('/api/tools/backup/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    const data = await resp.json();
    if (data.error) {
      if (statusEl) statusEl.textContent = '\u274C ' + data.error;
    } else {
      if (statusEl)
        statusEl.textContent =
          '\u2705 ' +
          _t('tools.backup_created', 'Backup created: ') +
          (data.filename || '');
      loadBackupList();
    }
  } catch (e: any) {
    if (statusEl) statusEl.textContent = '\u274C ' + (e.message || 'Error');
  }
}

export async function restoreFromBackup(filename: string): Promise<void> {
  if (
    !confirm(
      _t(
        'tools.backup_restore_managed_confirm',
        `Restore database from "${filename}"? A backup of the current DB will be created first.`,
      ),
    )
  )
    return;

  const statusEl = document.getElementById('backupManagedStatus');
  if (statusEl) statusEl.textContent = _t('tools.backup_restoring', 'Restoring...');

  try {
    const resp = await apiFetch('/api/tools/backup/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename }),
    });
    const data = await resp.json();
    if (data.error) {
      if (statusEl) statusEl.textContent = '\u274C ' + data.error;
    } else {
      if (statusEl)
        statusEl.textContent =
          '\u2705 ' +
          _t('tools.backup_restore_success', 'Database restored. Reloading...');
      setTimeout(() => location.reload(), 1500);
    }
  } catch (e: any) {
    if (statusEl) statusEl.textContent = '\u274C ' + (e.message || 'Error');
  }
}

export async function deleteBackupFile(filename: string): Promise<void> {
  if (
    !confirm(
      _t('tools.backup_delete_confirm', `Delete backup "${filename}"?`),
    )
  )
    return;

  const statusEl = document.getElementById('backupManagedStatus');
  try {
    const resp = await apiFetch('/api/tools/backup/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename }),
    });
    const data = await resp.json();
    if (data.error) {
      if (statusEl) statusEl.textContent = '\u274C ' + data.error;
    } else {
      if (statusEl) statusEl.textContent = '';
      loadBackupList();
    }
  } catch (e: any) {
    if (statusEl) statusEl.textContent = '\u274C ' + (e.message || 'Error');
  }
}

export async function loadBackupStatus(): Promise<void> {
  const el = document.getElementById('backupStatusInfo');
  if (!el) return;

  try {
    const resp = await apiFetch('/api/tools/backup/status');
    const data: BackupStatusResponse = await resp.json();

    const parts: string[] = [];
    if (data.scheduler_running) {
      parts.push(
        _t('tools.backup_scheduler_active', 'Scheduler: active') +
          ` (${data.periodic_interval_hours}h)`,
      );
    } else {
      parts.push(_t('tools.backup_scheduler_off', 'Scheduler: off'));
    }
    if (data.backup_on_scan_complete) {
      parts.push(_t('tools.backup_on_scan', 'Scan-complete: on'));
    }
    parts.push(
      _t('tools.backup_max_gen', 'Max generations: ') + data.max_generations,
    );
    if (data.last_backup_time) {
      const d = new Date(data.last_backup_time * 1000);
      parts.push(
        _t('tools.backup_last', 'Last backup: ') + d.toLocaleString(),
      );
    }
    el.innerHTML =
      '<span style="font-size:0.85em;color:var(--text-muted);">' +
      parts.join(' | ') +
      '</span>';
  } catch {
    el.textContent = '';
  }
}

function _escHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _escAttr(s: string): string {
  return s.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

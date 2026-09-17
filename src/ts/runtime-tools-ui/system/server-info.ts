/**
 * system/server-info.ts — Load and poll server info (uptime, DB stats, version).
 * Converted from runtime-server-info.js
 */

import { getAppApi } from '../../shared/browser-apis';
import {
  applyServerInfoPayload,
  consumeCachedServerInfo,
} from '../../shared/runtime-state/server-info-state';
import { formatElapsedHms } from '../../shared/date-format';

// Module-level state for polling
let _serverInfoPollingSetup = false;
let _serverInfoInterval: ReturnType<typeof setInterval> | null = null;
let _bootPollingActive = false;

export async function loadServerInfo(): Promise<void> {
  const { apiFetch, tr } = getAppApi();
  try {
    let data: Record<string, unknown>;
    const cached = consumeCachedServerInfo();
    if (cached) {
      data = cached;
    } else {
      const response = await apiFetch('/api/server-info');
      data = await response.json();
    }

    const serverInfoEl = document.getElementById('serverInfoText');
    if (!serverInfoEl) return;
    applyServerInfoPayload(data);
    const wrapperEl = document.getElementById('serverInfo');
    let noticeEl = document.getElementById('serverInfoNotice');
    const bootNoticeEl = document.getElementById('bootNotice');
    const bootNoticeTitleEl = document.getElementById('bootNoticeTitle');
    const bootNoticeTextEl = document.getElementById('bootNoticeText');
    if (!noticeEl && wrapperEl) {
      noticeEl = document.createElement('div');
      noticeEl.id = 'serverInfoNotice';
      noticeEl.style.marginTop = '4px';
      noticeEl.style.fontSize = '11px';
      noticeEl.style.color = 'var(--muted)';
      wrapperEl.appendChild(noticeEl);
    }

    const _t: (key: string, fallback?: string) => string = (k, f) => tr(k, f) || f || '';

    const uptimeSeconds = typeof data.uptime_seconds === 'number' ? data.uptime_seconds : 0;
    const dbSizeMb = typeof data.db_size_mb === 'number' || typeof data.db_size_mb === 'string' ? String(data.db_size_mb) : '?';
    const version = typeof data.version === 'string' ? data.version : '';
    const dbPath = typeof data.db_path === 'string' ? data.db_path : '';
    const hours = Math.floor(uptimeSeconds / 3600);
    const minutes = Math.floor((uptimeSeconds % 3600) / 60);
    const hUnit = _t('settings.unit_hours', 'h');
    const mUnit = _t('settings.unit_minutes', 'm');
    const uptime = hours > 0 ? hours + hUnit + ' ' + minutes + mUnit : minutes + mUnit;

    const pathParts: string[] = dbPath.split(/[\\/]/);
    const shortPath = pathParts.slice(-2).join('/');
    const filesLabel = _t('server_info.files', 'files');
    const tagsLabel = _t('server_info.tags', 'tags');
    // server_mode comes from trusted server API, not user input
    const serverMode = typeof data.server_mode === 'string' ? data.server_mode : 'full';

    // Build info text
    const infoParts: string[] = [];
    if (serverMode !== 'full') {
      infoParts.push(serverMode.toUpperCase());
    }
    infoParts.push(`\uD83D\uDCC1 ${shortPath} (${dbSizeMb} MB)`);
    infoParts.push(`\uD83D\uDCCA ${(data.file_count as number).toLocaleString()} ${filesLabel}`);
    infoParts.push(`\uD83C\uDFF7\uFE0F ${(data.tag_count as number).toLocaleString()} ${tagsLabel}`);
    infoParts.push(`\u23F1\uFE0F ${uptime}`);
    infoParts.push(version);

    serverInfoEl.textContent = infoParts.join(' | ');
    const startupMigration = data.startup_migration as Record<string, unknown> | undefined;
    const startupStatus = data.startup_status as Record<string, unknown> | undefined;
    const bootState = typeof data.boot_state === 'string' ? data.boot_state : 'ready';
    if (noticeEl) {
      const fromVersion = typeof startupMigration?.from_version === 'number' ? startupMigration.from_version : null;
      const toVersion = typeof startupMigration?.to_version === 'number' ? startupMigration.to_version : null;
      const elapsedMs = typeof startupMigration?.elapsed_ms === 'number' ? startupMigration.elapsed_ms : null;
      if (fromVersion != null && toVersion != null && elapsedMs != null) {
        noticeEl.textContent = `ℹ ${( _t('server_info.startup_migration', 'Startup DB upgrade') )} v${fromVersion} → v${toVersion} (${formatElapsedHms(elapsedMs / 1000)})`;
        noticeEl.style.display = '';
      } else {
        noticeEl.textContent = '';
        noticeEl.style.display = 'none';
      }
    }
    if (bootNoticeEl && bootNoticeTitleEl && bootNoticeTextEl) {
      const fromVersion = typeof startupStatus?.from_version === 'number' ? startupStatus.from_version : null;
      const toVersion = typeof startupStatus?.to_version === 'number' ? startupStatus.to_version : null;
      const stage = typeof startupStatus?.stage === 'string' ? startupStatus.stage : '';
      const kind = typeof startupStatus?.kind === 'string' ? startupStatus.kind : '';
      const totalRows = typeof startupStatus?.total_rows === 'number' ? startupStatus.total_rows : null;
      const processedRows = typeof startupStatus?.processed_rows === 'number' ? startupStatus.processed_rows : null;

      if (bootState === 'booting') {
        // Show banner whenever server is still booting — even without active migration
        const hasMigration = fromVersion != null && toVersion != null;
        const versionText = hasMigration ? ` v${fromVersion} → v${toVersion}` : '';

        let title: string;
        let detail: string;

        if (stage === 'file_cache') {
          // Post-migration (or normal startup): building file metadata cache
          title = hasMigration
            ? `${_t('server_info.startup_upgrade_in_progress', 'Database upgrade in progress')}...${versionText}`
            : `${_t('server_info.startup_initializing', 'Server initializing')}...`;
          detail = _t('server_info.startup_stage_file_cache', 'Building file metadata cache. Ready shortly.');
        } else if (stage === 'done' || kind === 'migration_done') {
          // Migration finished, finalizing startup
          title = `${_t('server_info.startup_upgrade_in_progress', 'Database upgrade in progress')}...${versionText}`;
          detail = _t('server_info.startup_stage_finalizing', 'Upgrade complete. Finalizing startup...');
        } else if (stage === 'backup') {
          title = `${_t('server_info.startup_upgrade_in_progress', 'Database upgrade in progress')}...${versionText}`;
          detail = _t('server_info.startup_stage_backup', 'Preparing a safety backup before the upgrade.');
        } else if (stage === 'backup_reused') {
          title = `${_t('server_info.startup_upgrade_in_progress', 'Database upgrade in progress')}...${versionText}`;
          detail = _t('server_info.startup_stage_backup_reused', 'Reusing an unchanged pre-upgrade backup.');
        } else if (stage === 'backup_skipped') {
          title = `${_t('server_info.startup_upgrade_in_progress', 'Database upgrade in progress')}...${versionText}`;
          detail = _t('server_info.startup_stage_backup_skipped', 'Skipping pre-upgrade backup for a large database to reduce startup time.');
        } else if (stage === 'migrate') {
          title = `${_t('server_info.startup_upgrade_in_progress', 'Database upgrade in progress')}...${versionText}`;
          detail = _t('server_info.startup_stage_migrate', 'Applying database schema updates.');
        } else if (stage === 'backfill') {
          title = `${_t('server_info.startup_upgrade_in_progress', 'Database upgrade in progress')}...${versionText}`;
          detail = totalRows != null && processedRows != null
            ? `${_t('server_info.startup_stage_backfill', 'Updating search columns for existing records.')} ${processedRows.toLocaleString()} / ${totalRows.toLocaleString()}`
            : _t('server_info.startup_stage_backfill', 'Updating search columns for existing records.');
        } else if (stage === 'rebuild_fts') {
          title = `${_t('server_info.startup_upgrade_in_progress', 'Database upgrade in progress')}...${versionText}`;
          detail = _t('server_info.startup_stage_rebuild_fts', 'Rebuilding search indexes for the new schema.');
        } else if (stage === 'prepare') {
          title = `${_t('server_info.startup_upgrade_in_progress', 'Database upgrade in progress')}...${versionText}`;
          detail = _t('server_info.startup_stage_prepare', 'Preparing database upgrade checks.');
        } else {
          // Generic booting state (no stage info available)
          title = `${_t('server_info.startup_initializing', 'Server initializing')}...`;
          detail = _t('server_info.startup_upgrade_wait', 'This may take a few minutes on large databases.');
        }

        bootNoticeTitleEl.textContent = title;
        bootNoticeTextEl.textContent = detail;
        (bootNoticeEl as HTMLElement).style.display = '';

        // Poll more frequently while booting so stage updates appear promptly
        _startBootPolling();
      } else {
        (bootNoticeEl as HTMLElement).style.display = 'none';
        _stopBootPolling();
      }
    }

    if (wrapperEl) {
      wrapperEl.classList.remove('header-info-loading');
      wrapperEl.classList.add('header-info-loaded');
      wrapperEl.style.opacity = '';
    }

    _startServerInfoPolling();
  } catch (err) {
    console.error('Failed to load server info:', err);
    const wrapperEl = document.getElementById('serverInfo');
    if (wrapperEl) {
      wrapperEl.style.opacity = '';
      const textEl = document.getElementById('serverInfoText');
      if (textEl) textEl.textContent = tr('server_info.load_failed');
    }
  }
}

let _bootPollInterval: ReturnType<typeof setInterval> | null = null;

function _startBootPolling(): void {
  if (_bootPollingActive) return;
  _bootPollingActive = true;
  _bootPollInterval = setInterval(loadServerInfo, 3000);
}

function _stopBootPolling(): void {
  if (!_bootPollingActive) return;
  _bootPollingActive = false;
  if (_bootPollInterval) {
    clearInterval(_bootPollInterval);
    _bootPollInterval = null;
  }
}

function _startServerInfoPolling(): void {
  if (_serverInfoPollingSetup) return;
  _serverInfoPollingSetup = true;

  function startInterval(): void {
    if (_serverInfoInterval) return;
    _serverInfoInterval = setInterval(loadServerInfo, 60000);
  }

  function stopInterval(): void {
    if (_serverInfoInterval) {
      clearInterval(_serverInfoInterval);
      _serverInfoInterval = null;
    }
  }

  // Start only when page is visible; stop when hidden to free resources
  if (!document.hidden) startInterval();
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      stopInterval();
    } else {
      loadServerInfo();
      startInterval();
    }
  });
}

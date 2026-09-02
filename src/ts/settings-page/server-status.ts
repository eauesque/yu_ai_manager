/**
 * Settings page — server status display and updates.
 * Converted from static/js/settings/settings-server-status.js
 */

import { getAppApi } from '../shared/browser-apis';
import { setServerInfo } from './config-form';
import { renderProfileManager } from './profiles';
import { updatePinSourceNotice } from './security-ui';
import { restartWithConfig } from './restart-with-config';
import { setRestartAvailable } from './ui-tab';
import { loadOsIsolationStatus, loadScanErrorStats, renderMetaStats } from './server-status-helpers';
import { reloadServerInfo } from '../shared/runtime-state/server-info-state';
import { formatElapsedHms } from '../shared/date-format';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function _esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

interface ServerStatusData {
  version?: string;
  uptime_seconds?: number;
  db_size_mb?: string;
  schema_version?: number;
  db_path?: string;
  file_count?: number;
  tag_count?: number;
  host?: string;
  lan_ips?: string[];
  has_pin?: boolean;
  config_has_pin?: boolean;
  pin_source?: string;
  restart_enabled?: boolean;
  restart_available_now?: boolean;
  restart_enable_source?: string;
  restart_remote_allowed?: boolean;
  restart_remote_source?: string;
  restart_remote_token_set?: boolean;
  restart_remote_token_source?: string;
  restart_blockers?: string[];
  restart_blocker_details?: Array<{ code: string; label: string; description: string; hint: string }>;
  meta_stats?: Record<string, number>;
  profiles?: Array<{ name: string; label: string; description?: string; favorite?: boolean; last_used_at?: string | null }>;
  active_profile?: string;
  active_ui?: string;
  available_uis?: Array<{ name: string; label: string; is_sample: boolean }> | string[];
  timezone?: string;
  timezone_source?: string;
  startup_migration?: {
    from_version?: number;
    to_version?: number;
    elapsed_ms?: number;
    message?: string;
  };
  stale_rebuild?: { phase?: string; message?: string; updated_at?: number } | null;
  [key: string]: unknown;
}

export async function loadServerStatus(): Promise<void> {
  const div = document.getElementById('serverStatusGrid');
  if (!div) return;

  try {
    const loaded = await reloadServerInfo();
    if (!loaded) throw new Error('server-info unavailable');
    const d = loaded as ServerStatusData;
    setServerInfo(d);

    const uptimeS = d.uptime_seconds || 0;
    const uptimeH = Math.floor(uptimeS / 3600);
    const uptimeM = Math.floor((uptimeS % 3600) / 60);
    const uptime = uptimeH > 0
      ? uptimeH + _t('settings.unit_hours', 'h') + uptimeM + _t('settings.unit_minutes', 'm')
      : uptimeM + _t('settings.unit_minutes', 'm');

    const pinBadge = d.has_pin
      ? '<span style="color:var(--status-ok,#166534);font-weight:600;">\uD83D\uDD12 ' + _t('settings.pin_active', 'PIN active') + '</span>'
      : d.config_has_pin
        ? '<span style="color:var(--status-warn,#7c4700);font-weight:600;">\uD83D\uDFE1 ' + _t('settings.pin_pending', 'PIN set (restart required)') + '</span>'
        : '<span style="color:#d32f2f;font-weight:600;">\uD83D\uDD13 ' + _t('settings.pin_disabled', 'PIN disabled') + '</span>';

    const pinSourceMap: Record<string, string> = { cli: 'CLI (--pin)', config: 'config.json', none: _t('settings.not_set', 'Not set') };
    const pinSourceText = pinSourceMap[d.pin_source || ''] || d.pin_source || _t('settings.not_set', 'Not set');
    updatePinSourceNotice(d);

    const restartEnabled = !!d.restart_enabled;
    const restartAvailableNow = !!d.restart_available_now;

    const restartSourceMap: Record<string, string> = { cli: 'CLI', env: _t('settings.env_var', 'Env var'), config: 'config.json', none: _t('settings.not_set', 'Not set') };
    const restartSourceText = restartSourceMap[d.restart_enable_source || ''] || d.restart_enable_source || _t('settings.not_set', 'Not set');
    const remoteSourceText = restartSourceMap[d.restart_remote_source || ''] || d.restart_remote_source || _t('settings.not_set', 'Not set');
    const tokenSourceText = restartSourceMap[d.restart_remote_token_source || ''] || d.restart_remote_token_source || _t('settings.not_set', 'Not set');

    const blockers: string[] = Array.isArray(d.restart_blockers) ? d.restart_blockers : [];
    const blockerDetails = Array.isArray(d.restart_blocker_details) ? d.restart_blocker_details : [];
    const blockerTextMap: Record<string, string> = {
      restart_disabled: _t('settings.blocker_restart_disabled', 'Restart API disabled (--allow-restart or TAGDB_ALLOW_RESTART=1)'),
      pin_not_active: _t('settings.blocker_pin_not_active', 'PIN auth not active (restart required)'),
      local_only: _t('settings.blocker_local_only', 'This operation is only allowed from the local machine'),
      remote_token_missing: _t('settings.blocker_token_missing', 'Remote restart token not set'),
      pin_session_required: _t('settings.blocker_pin_session', 'PIN auth session required'),
    };
    const blockerText = blockers.map((k) => blockerTextMap[k] || k).join(' / ');

    const blockerHintHtml = blockerDetails.length > 0
      ? '<ul style="margin:4px 0 0 0;padding:0;list-style:none;">' +
        blockerDetails.map(b =>
          `<li style="margin-bottom:4px;font-size:11px;">` +
          `<span style="color:var(--text);font-weight:600;">• ${_esc(b.label)}</span>` +
          `<br><span style="color:var(--muted);padding-left:12px;">${_esc(b.hint)}</span></li>`
        ).join('') + '</ul>'
      : '';

    const restartModeText = d.restart_remote_allowed
      ? _t('settings.remote_restart_on', 'Remote restart: ON') + ' (' + _t('settings.source', 'source') + ': ' + remoteSourceText + ')'
      : _t('settings.remote_restart_off', 'Remote restart: OFF');

    const restartTokenText = d.restart_remote_token_set
      ? _t('settings.token_set', 'Token: set') + ' (' + _t('settings.source', 'source') + ': ' + tokenSourceText + ')'
      : _t('settings.token_not_set', 'Token: not set');

    // Share restart availability with other tabs
    setRestartAvailable(restartAvailableNow);

    const restartBtnHtml = restartAvailableNow
      ? '<button id="restartServerBtn" data-action="settingsPageApi.restartServerFromSettings" style="padding:4px 12px;border:1px solid rgba(128,128,128,0.3);border-radius:4px;background:none;color:var(--text);cursor:pointer;font-size:12px;">\uD83D\uDD04 ' + _t('settings.restart_server', 'Restart server') + '</button>'
      : '<div style="font-size:11px;">' +
        '<span style="color:var(--muted);">' + _t('settings.restart_not_available', '再起動できない理由:') + '</span>' +
        blockerHintHtml +
        (blockerDetails.length === 0
          ? '<span style="color:var(--muted);">' + (blockerText || _t('settings.conditions_not_met', 'conditions not met')) + '</span>'
          : '') +
        '</div>';

    const lanIpList = d.lan_ips || [];
    const lanIps = lanIpList.length > 0
      ? lanIpList
          .map((ip) => '<code style="background:rgba(128,128,128,0.15);padding:2px 6px;border-radius:3px;word-break:break-all;">' + _esc(ip) + '</code>')
          .join(', ')
      : _t('settings.none_detected', 'None detected');
    const lanAriaLabel = lanIpList.length > 0
      ? 'LAN: ' + lanIpList.join(', ')
      : 'LAN: ' + _t('settings.none_detected', 'None detected');

    let metaHtml = '';
    if (d.meta_stats) {
      metaHtml = renderMetaStats(d.meta_stats);
      loadScanErrorStats().then(errors => {
        if (errors.length === 0) return;
        const errDiv = document.getElementById('scanErrorStats');
        if (!errDiv) return;
        errDiv.textContent = '';
        const hdr = document.createElement('div');
        hdr.style.cssText = 'font-size:11px;color:var(--muted);margin-top:6px;font-weight:600;';
        hdr.textContent = 'スキャンエラー上位:';
        errDiv.appendChild(hdr);
        errors.forEach(e => {
          const sp = document.createElement('span');
          sp.style.cssText = 'margin-right:10px;font-size:11px;';
          sp.textContent = e.error_type + ': ' + e.count;
          errDiv.appendChild(sp);
        });
      });
    }

    const fileCount = (d.file_count || 0).toLocaleString();
    const tagCount = (d.tag_count || 0).toLocaleString();
    const startupMigration = d.startup_migration;
    const migrationNote = startupMigration
      && typeof startupMigration.from_version === 'number'
      && typeof startupMigration.to_version === 'number'
      && typeof startupMigration.elapsed_ms === 'number'
      ? '<div style="margin-top:6px;color:var(--muted,#aaa);font-size:11px;">'
        + '\u2139 ' + _t('settings.startup_db_upgrade', 'Startup DB upgrade')
        + ': v' + startupMigration.from_version + ' \u2192 v' + startupMigration.to_version
        + ' (' + formatElapsedHms(startupMigration.elapsed_ms / 1000) + ')'
        + '</div>'
      : '';

    div.innerHTML =
      '<div role="list" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;align-items:start;">' +
      '<div class="status-card" role="listitem"><div class="status-label">' + _t('settings.version', 'Version') + '</div><div class="status-value">' + _esc(d.version || '') + '</div></div>' +
      '<div class="status-card" role="listitem"><div class="status-label">' + _t('settings.uptime', 'Uptime') + '</div><div class="status-value">' + uptime + '</div></div>' +
      '<div class="status-card" role="listitem"><div class="status-label">' + _t('settings.database', 'Database') + '</div><div class="status-value">' + (d.db_size_mb || '') + ' MB / v' + (d.schema_version || '') + '</div><div class="status-sub" title="' + _esc(d.db_path || '') + '">' + _esc(d.db_path || '') + '</div>' + migrationNote +
      (restartAvailableNow && d.is_local_request
        ? '<div style="margin-top:6px;"><button data-action="settingsPageApi.showDbPathChanger" style="padding:3px 10px;border:1px solid rgba(128,128,128,0.3);border-radius:4px;background:none;color:var(--text);cursor:pointer;font-size:11px;">' + _t('settings.db_change', 'Change DB') + '</button></div>'
        : '') +
      '</div>' +
      '<div class="status-card" role="listitem"><div class="status-label">' + _t('settings.files_tags', 'Files / Tags') + '</div><div class="status-value">' + fileCount + ' / ' + tagCount + '</div>' +
      (metaHtml ? '<div style="margin-top:8px;">' + metaHtml + '</div><div id="scanErrorStats"></div>' : '') +
      '</div>' +
      '<div class="status-card" role="listitem"><div class="status-label">' + _t('settings.active_ui', 'Active UI') + '</div><div class="status-value">' + _esc(d.active_ui || 'default') + '</div></div>' +
      '<div class="status-card" role="listitem"><div class="status-label">' + _t('settings.network', 'Network') + '</div><div class="status-value">' + _esc(d.host || '') + '</div><div class="status-sub" aria-label="' + lanAriaLabel.replace(/"/g, '&quot;') + '" style="overflow-wrap:break-word;">LAN: ' + lanIps + '</div></div>' +
      '<div class="status-card" role="listitem"><div class="status-label">' + _t('settings.security', 'Security') + '</div><div class="status-value">' + pinBadge + '</div><div class="status-sub">' + _t('settings.pin_source', 'PIN source') + ': ' + pinSourceText + '<br>' + restartModeText + '<br>' + restartTokenText + '</div>' +
      (d.has_pin
        ? '<div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;"><button data-action="settingsPageApi.quickLockFromSettings" style="padding:4px 12px;border:1px solid rgba(128,128,128,0.3);border-radius:4px;background:none;color:var(--text);cursor:pointer;font-size:12px;">\uD83D\uDD12 ' + _t('settings.screen_lock', 'Screen Lock') + '</button>' + restartBtnHtml + '</div>'
        : '<div style="margin-top:6px;">' + restartBtnHtml + '</div>') +
      '</div>' +
      '</div>' +
      '';

    // --- Timezone selector initialization ---
    const tzSelect = document.getElementById('cfg-timezone') as HTMLSelectElement | null;
    const tzNote = document.getElementById('timezoneSourceNote');
    if (tzSelect && d.timezone) {
      const opts = Array.from(tzSelect.options);
      const match = opts.find(o => o.value === d.timezone);
      if (match) tzSelect.value = match.value;
    }
    if (tzNote && d.timezone_source === 'system') {
      tzNote.textContent = `システム推定値: ${d.timezone || ''}（変更可）`;
    }

    // --- Profile section (delegated to profiles.ts) ---
    renderProfileManager(d.profiles || [], d.active_profile || '', !!d.has_pin);

    // --- OS Isolation (AppArmor) status ---
    loadOsIsolationStatus();

    // --- Fast mode: local Rust build ---
    renderFastModeBuild(d.fast_mode_build as FastModeBuild | null | undefined);
    renderStaleRebuild(d.stale_rebuild);
  } catch (err) {
    div.innerHTML = '<span style="color:#d32f2f;">' + _t('settings.load_failed', 'Load failed') + ': ' + _esc(err instanceof Error ? err.message : String(err)) + '</span>';
  }
}

/* ---- Fast mode build progress ---- */

interface FastModeBuild {
  source?: 'download' | 'build' | 'auto';
  enabled?: boolean;
  phase?: 'idle' | 'building' | 'stalled' | 'ok' | 'failed';
  elapsed_seconds?: number | null;
  finished_at?: number | null;
  failures?: number;
  max_failures?: number;
  last_line?: string | null;
  last_message?: string | null;
  decision?: {
    use_fast_mode?: boolean;
    reason?: string | null;
    needs_binary?: boolean;
    at?: number | null;
  } | null;
  config?: { read_from?: string | null; shadowed?: string[] } | null;
  blockers?: string[] | null;
}

let _fastModePoll: ReturnType<typeof setInterval> | null = null;

function idleText(s: FastModeBuild): { text: string; color: string } {
  const d = s.decision;
  // `blockers` is measured now; the verdict is a snapshot of the last launch.
  // When they disagree the live answer wins, or the screen keeps reporting a
  // staleness that a rebuild already fixed.
  const blockers = s.blockers;
  if (blockers && blockers.length > 0) {
    return {
      text: _t('settings.fast_mode_blocked', '高速モードは使われていません。取得も行いません（この端末側の状態が原因です）'),
      color: 'var(--status-warn,#7c4700)',
    };
  }
  if (!d) {
    return {
      text: _t('settings.fast_mode_no_decision', 'まだ起動時の判定がありません（次回の起動で判定します）'),
      color: 'var(--muted,#888)',
    };
  }
  if (d.use_fast_mode) {
    return { text: _t('settings.fast_mode_active', '高速モードで起動しました'), color: 'var(--status-ok,#166534)' };
  }
  if (blockers && blockers.length === 0 && d.needs_binary === false) {
    // The recorded refusal was about the checkout, and the checkout is fine
    // now -- the launch that made the verdict is simply out of date.
    return {
      text: _t('settings.fast_mode_verdict_outdated', '起動時の判定は解消済みです（次回の起動から高速モードを試みます）'),
      color: 'var(--muted,#888)',
    };
  }
  if (s.source === 'download') {
    return {
      text: _t('settings.fast_mode_will_download', '次回起動時に配布バイナリを取得します'),
      color: 'var(--muted,#888)',
    };
  }
  return {
    text: _t('settings.fast_mode_waiting', '次回起動時にビルドを開始します'),
    color: 'var(--muted,#888)',
  };
}

function renderFastModeBuild(s: FastModeBuild | null | undefined): void {
  const box = document.getElementById('fastModeBuildStatus');
  if (!box) return;

  // Absent means this server cannot answer (a remote request, or the Rust
  // server, which only runs once a binary already exists). Saying nothing is
  // the honest answer -- not "idle", which would claim knowledge.
  if (!s) {
    box.hidden = true;
    stopFastModePolling();
    return;
  }
  box.hidden = false;

  const mins = (sec: number) => Math.floor(sec / 60) + _t('settings.unit_minutes', 'm');
  let color = 'var(--muted,#888)';
  let text: string;

  switch (s.phase) {
    case 'building':
      color = 'var(--accent,#4a90d9)';
      text = _t('settings.fast_mode_building', 'ビルド中')
        + (typeof s.elapsed_seconds === 'number' ? `（${mins(s.elapsed_seconds)}）` : '');
      break;
    case 'stalled':
      color = 'var(--status-warn,#7c4700)';
      text = _t('settings.fast_mode_stalled', 'ビルドが途中で止まりました（プロセスが消えています）');
      break;
    case 'ok':
      color = 'var(--status-ok,#166534)';
      text = _t('settings.fast_mode_built', 'ビルド成功。次回起動から高速モードになります');
      break;
    case 'failed':
      color = 'var(--status-err,#d32f2f)';
      text = _t('settings.fast_mode_build_failed', 'ビルド失敗')
        + `（${s.failures ?? 0}/${s.max_failures ?? 3}）`;
      break;
    default: {
      const idle = idleText(s);
      text = idle.text;
      color = idle.color;
    }
  }

  // The launch verdict explains the idle cases and adds context to the rest,
  // so it is shown alongside whatever the build itself is doing.
  // The live blockers explain the idle cases; the recorded reason is only a
  // fallback for when they could not be measured.
  const detail = s.phase === 'failed'
    ? s.last_message
    : (s.phase === 'idle' || s.phase === undefined
      ? (s.blockers && s.blockers.length > 0 ? s.blockers.join(' / ') : (s.blockers ? null : s.decision?.reason))
      : s.last_line);

  // A settings file that nothing reads makes every saved value look ignored,
  // which is indistinguishable from a broken setting unless it is named.
  const shadowed = s.config?.shadowed ?? [];
  const shadowWarning = shadowed.length > 0
    ? `<div style="color:var(--status-warn,#7c4700);margin-top:4px;">`
      + _esc(
        _t('settings.fast_mode_config_shadowed', '設定は {read} から読まれています。{ignored} は読まれません（保存しても反映されません）')
          .replace('{read}', s.config?.read_from || '?')
          .replace('{ignored}', shadowed.join(', ')),
      )
      + '</div>'
    : '';

  box.innerHTML =
    `<span style="color:${color};font-weight:600;">${_esc(text)}</span>`
    + (detail
      ? `<div style="font-family:monospace;font-size:11px;color:var(--muted,#888);margin-top:4px;word-break:break-all;">${_esc(detail)}</div>`
      : '')
    + shadowWarning;

  // Only a running build changes on its own, so only then is polling worth
  // the request. server-info caches 5s; a shorter interval would just return
  // the same payload.
  if (s.phase === 'building') startFastModePolling();
  else stopFastModePolling();
}

function startFastModePolling(): void {
  if (_fastModePoll !== null) return;
  _fastModePoll = setInterval(() => { void loadServerStatus(); }, 5000);
}

function stopFastModePolling(): void {
  if (_fastModePoll === null) return;
  clearInterval(_fastModePoll);
  _fastModePoll = null;
}

/* ---- Stale-source background rebuild (dev-only) ---- */

const STALE_REBUILD_STALE_MS = 60 * 60 * 1000; // 60 minutes, see spec 設計4

export function renderStaleRebuild(
  s: { phase?: string; message?: string; updated_at?: number } | null | undefined,
): void {
  const box = document.getElementById('staleRebuildStatus');
  if (!box) return;

  if (!s || !s.phase) {
    box.hidden = true;
    return;
  }
  box.hidden = false;

  let color = 'var(--muted,#888)';
  let text: string;

  const stale = typeof s.updated_at === 'number'
    && (Date.now() - s.updated_at * 1000) > STALE_REBUILD_STALE_MS;

  if (s.phase === 'building' && stale) {
    color = 'var(--muted,#888)';
    text = _t('settings.stale_rebuild_unknown', '背景リビルド: 不明（前回のビルドが応答していません）');
  } else {
    switch (s.phase) {
      case 'building':
        color = 'var(--accent,#4a90d9)';
        text = _t('settings.stale_rebuild_building', '背景リビルド: 進行中');
        break;
      case 'ok':
        color = 'var(--status-ok,#166534)';
        text = _t('settings.stale_rebuild_ok', '背景リビルド: 成功（次回起動から反映）');
        break;
      case 'failed':
        color = 'var(--status-err,#d32f2f)';
        text = _t('settings.stale_rebuild_failed', '背景リビルド: 失敗');
        break;
      default:
        text = `${_t('settings.stale_rebuild_unrecognized', '背景リビルド: 未知の状態')}: ${s.phase}`;
    }
  }

  const detail = s.phase === 'failed' && s.message ? s.message : '';

  box.innerHTML =
    `<span style="color:${color};">${_esc(text)}</span>`
    + (detail
      ? `<div style="font-family:monospace;font-size:10px;color:var(--muted,#888);margin-top:2px;word-break:break-all;">${_esc(detail)}</div>`
      : '');
}

/* ---- DB path changer ---- */

export function showDbPathChanger(): void {
  const section = document.getElementById('dbPathChangeSection');
  if (!section) return;
  const opening = section.style.display === 'none';
  section.style.display = opening ? 'block' : 'none';
  if (opening) {
    // Pre-fill with current path
    const input = document.getElementById('dbPathInput') as HTMLInputElement | null;
    const current = document.getElementById('serverStatusGrid')?.querySelector('.status-sub')?.getAttribute('title');
    if (input && current && !input.value) {
      input.value = current;
    }
    // Scroll into view and focus
    section.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (input) setTimeout(() => input.focus(), 300);
  }
}

export async function browseDbPath(): Promise<void> {
  const input = document.getElementById('dbPathInput') as HTMLInputElement | null;
  if (!input) return;
  try {
    // GET with `?initial=`, like every other caller of this endpoint. The POST
    // this used to send was refused by *both* implementations -- Quart's route
    // registers GET only, and the handler reads `request.args`, never a body --
    // so the folder picker on the DB-path field did nothing at all.
    const res = await fetch(
      '/api/tools/select-folder' +
        (input.value ? '?initial=' + encodeURIComponent(input.value) : ''),
    );
    const data = await res.json();
    if (data.path) {
      // Append /tags.db if a directory was selected
      let p = data.path as string;
      if (!p.endsWith('.db')) {
        p = p.replace(/[\\/]$/, '') + '/tags.db';
      }
      input.value = p;
    }
  } catch {
    // dialog cancelled or unavailable
  }
}

export async function applyDbPathChange(): Promise<void> {
  const input = document.getElementById('dbPathInput') as HTMLInputElement | null;
  if (!input) return;
  const newPath = input.value.trim();
  if (!newPath) return;

  const msg = _t('settings.db_change_confirm', 'Change database to "{path}" and restart?').replace('{path}', newPath);
  if (!confirm(msg)) return;

  await restartWithConfig({ db: newPath }, _t('settings.db_changing', 'Changing database path'));
}

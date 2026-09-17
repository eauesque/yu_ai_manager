/** DB information display and tag count loader. */

import { getAppApi } from '../shared/browser-apis';
import { apiUrl } from '../shared/api-base';
import { apiFetch } from './api';
import { loadServerInfo } from '../shared/runtime-state/server-info-state';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function _esc(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

interface ServerInfo {
  db_path?: string;
  db_size_mb?: number;
  file_count: number;
  tag_count: number;
  schema_version: string;
  uptime_seconds: number;
}

async function _getServerInfo(): Promise<ServerInfo> {
  const data = await loadServerInfo(apiFetch);
  if (!data) throw new Error('server-info unavailable');
  return data as unknown as ServerInfo;
}

function formatUptime(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours + _t('tools.unit_hours', 'h') + ' ' + minutes + _t('tools.unit_minutes', 'm');
}

export async function loadDbInfo(): Promise<void> {
  try {
    const data = await _getServerInfo();

    const html = `
      ${data.db_path ? `<div class="stat-row">
        <span>${_t('tools.db_path', 'Database Path:')}</span>
        <span>${_esc(data.db_path)}</span>
      </div>` : ''}
      <div class="stat-row">
        <span>${_t('tools.db_size', 'Database Size:')}</span>
        <span>${data.db_size_mb != null ? data.db_size_mb.toFixed(2) + ' MB' : '—'}</span>
      </div>
      <div class="stat-row">
        <span>${_t('tools.file_count', 'File Count:')}</span>
        <span>${data.file_count.toLocaleString()}</span>
      </div>
      <div class="stat-row">
        <span>${_t('tools.tag_count', 'Tag Count:')}</span>
        <span>${data.tag_count.toLocaleString()}</span>
      </div>
      <div class="stat-row">
        <span>${_t('tools.schema_version', 'Schema Version:')}</span>
        <span>${_esc(data.schema_version)}</span>
      </div>
      <div class="stat-row">
        <span>${_t('tools.uptime', 'Uptime:')}</span>
        <span>${formatUptime(data.uptime_seconds)}</span>
      </div>
    `;

    const el = document.getElementById('dbInfo');
    if (el) el.innerHTML = html;
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    const el = document.getElementById('dbInfo');
    if (el) el.innerHTML = `<p style="color: #e74c3c;">Error: ${_esc(msg)}</p>`;
  }
}

export async function loadTagCount(): Promise<void> {
  try {
    const data = await _getServerInfo();
    const el = document.getElementById('tagsBeforeNormalize');
    if (el) el.textContent = data.tag_count.toLocaleString();
  } catch (err) {
    console.error('Failed to load tag count:', err);
  }
}

export async function loadInferenceInfo(): Promise<void> {
  const el = document.getElementById('inferenceInfo');
  if (!el) return;
  try {
    const res = await apiFetch('/api/system/inference-info');
    const d = await res.json();
    const data = d.data ?? d;
    const gpu = data.gpu_info ?? {};
    const providers = (data.available_providers ?? []) as string[];
    const selected = (data.selected_providers ?? []) as string[];
    const gpuName = _esc(String(gpu.name || 'N/A'));
    const gpuVendor = _esc(String(gpu.vendor || 'unknown'));
    const ortVersion = _esc(String(data.ort_version || 'N/A'));
    const selectedProviders = _esc(selected.length ? selected.join(', ') : 'CPU only');
    const availableProviders = _esc(providers.join(', ') || 'none');
    const recommendedPackage = gpu.recommended_ort_package
      ? _esc(String(gpu.recommended_ort_package))
      : '';
    const installedVariant = data.installed_variant
      ? _esc(String(data.installed_variant))
      : '';
    const selectedExtra = data.selected_extra
      ? _esc(String(data.selected_extra))
      : '';
    const expectedVariant = data.expected_variant
      ? _esc(String(data.expected_variant))
      : '';
    const variantMatch = data.variant_match;
    let engineLine = '';
    if (installedVariant) {
      const matchBadge =
        variantMatch === false
          ? ` <span style="color:#f59e0b" title="installed: ${installedVariant} / .onnx_extra expects: ${expectedVariant}">⚠ marker mismatch</span>`
          : '';
      const extraSuffix = selectedExtra
        ? ` <span style="color:var(--muted,#888);font-size:11px">(extra: ${selectedExtra})</span>`
        : '';
      engineLine = `<div class="stat-row"><span>${_t('tools.onnx_engine', 'ONNX Engine')}:</span><span class="mono" style="font-size:12px">${installedVariant}${extraSuffix}${matchBadge}</span></div>`;
    }

    type ActiveSession = {
      engine?: string;
      active_provider?: string | null;
      providers?: string[];
      model_path?: string | null;
    };
    const activeSessions = (data.active_sessions ?? []) as ActiveSession[];
    const hasNonCpuOption = selected.some((p) => p && p !== 'CPUExecutionProvider');
    let activeSessionsBlock = '';
    if (activeSessions.length > 0) {
      const rows = activeSessions.map((s) => {
        const engine = _esc(String(s.engine ?? '?'));
        const prov = _esc(String(s.active_provider ?? 'unknown'));
        const onCpu = s.active_provider === 'CPUExecutionProvider';
        const warn = onCpu && hasNonCpuOption
          ? ` <span style="color:#f59e0b" title="GPU provider is available but this session is on CPU">⚠</span>`
          : '';
        return `<div class="mono" style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0"><span>${engine}</span><span>${prov}${warn}</span></div>`;
      }).join('');
      activeSessionsBlock = `<div class="stat-row" style="flex-direction:column;align-items:stretch;gap:2px"><span>${_t('tools.active_sessions', 'Active Sessions')}:</span><div style="margin-left:8px">${rows}</div></div>`;
    }

    el.innerHTML = `
      <div class="stat-row"><span>GPU:</span><span>${gpuName} (${gpuVendor})</span></div>
      ${engineLine}
      <div class="stat-row"><span>ORT Version:</span><span>${ortVersion}</span></div>
      <div class="stat-row"><span>${_t('tools.ort_providers', 'ORT Providers')}:</span><span>${selectedProviders}</span></div>
      <div class="stat-row"><span>${_t('tools.available_providers', 'Available')}:</span><span style="font-size:11px;color:var(--muted,#888)">${availableProviders}</span></div>
      ${recommendedPackage ? `<div class="stat-row"><span>Recommended:</span><span class="mono" style="font-size:12px">${recommendedPackage}</span></div>` : ''}
      ${activeSessionsBlock}
    `;
  } catch {
    el.innerHTML = '<span style="color:var(--muted,#888)">Inference info unavailable</span>';
  }
}

export async function loadScanErrors(): Promise<void> {
  const el = document.getElementById('scanErrorsList');
  if (!el) return;
  try {
    const res = await apiFetch('/api/scan-errors?resolved=false&limit=50');
    const d = await res.json();
    const data = d.data ?? d;
    const errors = data.errors ?? [];
    const total = data.unresolved_count ?? errors.length;

    if (!errors.length) {
      el.innerHTML = '<div style="color:var(--muted,#888);font-size:13px">' + _t('tools.no_scan_errors', 'No unresolved scan errors') + '</div>';
      return;
    }

    el.innerHTML = `<div style="margin-bottom:8px;font-size:13px;color:var(--muted,#888)">${_t('tools.unresolved_errors_count', '{total} unresolved errors').replace('{total}', String(total))}</div>`
      + errors.map((e: Record<string, unknown>) => `
        <div class="scan-error-row" style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border,#333);font-size:12px;">
          <div style="flex:1;min-width:0">
            <span class="scan-error-type" style="background:rgba(239,68,68,0.15);color:#ef4444;border-radius:4px;padding:1px 6px;font-size:11px;margin-right:6px">${_esc(String(e.error_type ?? ''))}</span>
            <span style="word-break:break-all">${_esc(String(e.path ?? '').substring(0, 80))}</span>
            <div style="color:var(--muted,#888);margin-top:2px">${_esc(String(e.error_detail ?? '').substring(0, 120))}</div>
          </div>
          <button class="btn btn-secondary" style="padding:3px 8px;font-size:11px;white-space:nowrap;margin-left:8px" data-action="toolsPageApi.resolveScanError" data-action-arg="${e.id}">${_t('tools.resolve', 'Resolve')}</button>
        </div>
      `).join('');
  } catch {
    el.innerHTML = '<span style="color:var(--muted,#888)">' + _t('tools.scan_errors_fetch_failed', 'Failed to fetch scan errors') + '</span>';
  }
}

export async function resolveScanError(errorId: number): Promise<void> {
  try {
    await apiFetch(`/api/scan-errors/${errorId}/resolve`, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    loadScanErrors();
  } catch {
    // ignore
  }
}

export async function loadWdUntaggedCount(): Promise<void> {
  const el = document.getElementById('wtUntaggedInfo');
  if (!el) return;
  try {
    const res = await apiFetch('/api/wd-tagger/stats');
    const d = await res.json();
    const data = d.data ?? d;
    const tagged = data.tagged_count ?? 0;
    const total = data.total_files ?? 0;
    const untagged = total - tagged;
    el.innerHTML = untagged > 0
      ? `<span style="color:#b45309">${_t('tools.untagged_count', '{count} untagged files / {total} total').replace('{count}', untagged.toLocaleString()).replace('{total}', total.toLocaleString())}</span>`
      : `<span style="color:#166534">${_t('tools.all_tagged', 'All files tagged ({total})').replace('{total}', total.toLocaleString())}</span>`;
  } catch {
    el.innerHTML = '';
  }
}

export async function checkDebugMode(): Promise<void> {
  const section = document.getElementById('debugSqlSection');
  if (!section) return;
  try {
    const res = await fetch(apiUrl('/api/debug/enabled'), {
      method: 'GET',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (!res.ok) return;
    const d = await res.json();
    const data = d.data ?? d;
    if (data.enabled === true) {
      section.style.display = '';
    }
  } catch {
  }
}

export async function executeDebugSql(): Promise<void> {
  const input = document.getElementById('debugSqlInput') as HTMLTextAreaElement | null;
  const resultEl = document.getElementById('debugSqlResult');
  const statusEl = document.getElementById('debugSqlStatus');
  if (!input || !resultEl) return;

  const sql = input.value.trim();
  if (!sql) return;

  if (statusEl) statusEl.textContent = 'Executing...';

  try {
    const res = await apiFetch('/api/debug/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sql, limit: 500 }),
    });
    const d = await res.json();
    const data = d.data ?? d;

    if (data.error) {
      resultEl.innerHTML = `<p style="color:#ef4444">${_esc(data.error)}</p>`;
      if (statusEl) statusEl.textContent = '';
      return;
    }

    const cols = data.columns || [];
    const rows = data.rows || [];
    if (statusEl) statusEl.textContent = `${data.row_count ?? rows.length} rows${data.truncated ? ' (truncated)' : ''}`;

    if (!rows.length) {
      resultEl.innerHTML = '<p style="color:var(--muted,#888)">No results</p>';
      return;
    }

    let html = '<table style="width:100%;border-collapse:collapse;font-size:11px;"><thead><tr>';
    for (const c of cols) html += `<th style="text-align:left;padding:4px 6px;border-bottom:1px solid var(--border,#444);white-space:nowrap;">${_esc(c)}</th>`;
    html += '</tr></thead><tbody>';
    for (const row of rows) {
      html += '<tr>';
      for (const c of cols) {
        const val = row[c];
        html += `<td style="padding:3px 6px;border-bottom:1px solid var(--border,#333);max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(val == null ? 'NULL' : String(val))}</td>`;
      }
      html += '</tr>';
    }
    html += '</tbody></table>';
    resultEl.innerHTML = html;
  } catch (err) {
    resultEl.innerHTML = `<p style="color:#ef4444">${_esc(err instanceof Error ? err.message : String(err))}</p>`;
    if (statusEl) statusEl.textContent = '';
  }
}

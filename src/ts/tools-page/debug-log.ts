/**
 * debug-log.ts -- Debug log viewer with auto-refresh and filtering.
 * Converted from tools-debug-log.js
 */

import { getAppApi } from '../shared/browser-apis';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

let _debugLogAutoTimer: ReturnType<typeof setInterval> | null = null;
let _debugLogAllLines: string[] = [];

interface DebugLogResponse {
  enabled?: boolean;
  lines?: string[];
  total_lines?: number;
  log_size_kb?: number;
  log_path?: string;
}

export function loadDebugLog(autoScroll: boolean): void {
  fetch('/api/tools/debug-log?limit=200')
    .then((r) => r.json())
    .then((data: DebugLogResponse) => {
      const disabledEl = document.getElementById('debugLogDisabled');
      const enabledEl = document.getElementById('debugLogEnabled');
      if (!data.enabled) {
        if (disabledEl) disabledEl.style.display = '';
        if (enabledEl) enabledEl.style.display = 'none';
        return;
      }
      if (disabledEl) disabledEl.style.display = 'none';
      if (enabledEl) enabledEl.style.display = '';

      _debugLogAllLines = data.lines || [];
      filterDebugLogClient();

      const statusEl = document.getElementById('debugLogStatus');
      if (statusEl) {
        statusEl.textContent = _t(
          'tools.debug_log_status_tpl',
          '{total} lines / {size} KB / {path}',
        )
          .replace('{total}', (data.total_lines || 0).toLocaleString())
          .replace('{size}', String(data.log_size_kb || 0))
          .replace('{path}', data.log_path || '');
      }

      if (autoScroll) {
        const pre = document.getElementById('debugLogContent');
        if (pre) pre.scrollTop = pre.scrollHeight;
      }
    })
    .catch((e: Error) => {
      const pre = document.getElementById('debugLogContent');
      if (pre) pre.textContent = 'Error: ' + e.message;
    });
}

export function filterDebugLogClient(): void {
  const input = document.getElementById('debugLogFilterInput') as HTMLInputElement | null;
  const filter = input ? input.value.trim().toLowerCase() : '';
  const pre = document.getElementById('debugLogContent');
  if (!pre) return;

  let lines = _debugLogAllLines;
  if (filter) {
    lines = lines.filter((ln) => ln.toLowerCase().indexOf(filter) !== -1);
  }
  pre.textContent = lines.join('\n');
}

export function toggleDebugLogAuto(): void {
  const btn = document.getElementById('debugLogAutoBtn');

  if (_debugLogAutoTimer) {
    clearInterval(_debugLogAutoTimer);
    _debugLogAutoTimer = null;
    if (btn)
      btn.innerHTML =
        '<span aria-hidden="true">\u25B6</span> <span data-i18n="tools.debug_log_auto">' +
        _t('tools.debug_log_auto', 'Auto') +
        '</span>';
  } else {
    _debugLogAutoTimer = setInterval(() => {
      loadDebugLog(true);
    }, 5000);
    if (btn)
      btn.innerHTML =
        '<span aria-hidden="true">\u23F8</span> <span data-i18n="tools.debug_log_auto_stop">' +
        _t('tools.debug_log_auto_stop', 'Stop') +
        '</span>';
    loadDebugLog(true);
  }
}

export function downloadDebugLog(): void {
  window.location.href = '/api/tools/debug-log/download';
}

export function clearDebugLog(): void {
  if (
    !confirm(
      _t(
        'tools.debug_log_clear_confirm',
        'Clear all debug log contents?',
      ),
    )
  )
    return;

  fetch('/api/tools/debug-log/clear', { method: 'POST', headers: XHR_HEADERS })
    .then((r) => r.json())
    .then((data: { error?: string }) => {
      if (data.error) {
        alert('Error: ' + data.error);
      } else {
        loadDebugLog(false);
      }
    })
    .catch((e: Error) => {
      alert('Error: ' + e.message);
    });
}

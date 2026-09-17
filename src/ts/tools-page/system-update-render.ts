import { getAppApi } from '../shared/browser-apis';
import type { UnifiedCheckResult } from './system-update-types';

const STATUS_BADGE: Record<string, { label: string; i18nKey: string; bg: string; color: string }> = {
  up_to_date: { label: 'Up to date', i18nKey: 'tools.unified_up_to_date', bg: 'rgba(46,204,113,0.15)', color: '#2ecc71' },
  update_available: { label: 'Update available', i18nKey: 'tools.unified_update_available', bg: 'rgba(241,196,15,0.15)', color: '#f1c40f' },
  unknown: { label: 'Unknown', i18nKey: 'tools.unified_unknown', bg: 'rgba(149,165,166,0.15)', color: '#95a5a6' },
  builtin: { label: 'Bundled', i18nKey: 'tools.unified_bundled', bg: 'rgba(102,126,234,0.15)', color: 'var(--muted)' },
  system: { label: 'System', i18nKey: 'tools.unified_system', bg: 'rgba(155,89,182,0.15)', color: '#9b59b6' },
};

export const STEP_LABELS: Record<string, string> = {
  backup: 'Backup',
  fetch: 'Fetching',
  pull: 'Pulling',
  pip_install: 'Installing dependencies',
  ts_build: 'Building frontend',
  complete: 'Complete',
  error: 'Error',
  ext_config_backup: 'Extension config backup',
};

export const STATUS_ICONS: Record<string, string> = {
  running: '...',
  done: '[OK]',
  error: '[!]',
};

function _tr(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback) || fallback;
}

function _setCellPadding(cell: HTMLElement, bold = false): void {
  cell.style.padding = '6px 8px';
  if (bold) cell.style.fontWeight = '600';
}

function _createBadge(statusKey: string): HTMLSpanElement {
  const spec = STATUS_BADGE[statusKey] || STATUS_BADGE.unknown;
  const badge = document.createElement('span');
  badge.style.display = 'inline-block';
  badge.style.padding = '2px 8px';
  badge.style.borderRadius = '8px';
  badge.style.fontSize = '11px';
  badge.style.background = spec.bg;
  badge.style.color = spec.color;
  badge.textContent = _tr(spec.i18nKey, spec.label);
  return badge;
}

function _createMutedText(text: string): HTMLSpanElement {
  const span = document.createElement('span');
  span.style.fontSize = '10px';
  span.style.color = 'var(--muted)';
  span.textContent = text;
  return span;
}

function _createCode(text: string): HTMLElement {
  const code = document.createElement('code');
  code.style.fontSize = '11px';
  code.textContent = text;
  return code;
}

function _createActionButton(label: string, onClick: () => void): HTMLButtonElement {
  const button = document.createElement('button');
  button.className = 'btn btn-primary';
  button.style.padding = '3px 10px';
  button.style.fontSize = '11px';
  button.textContent = label;
  button.addEventListener('click', onClick);
  return button;
}

function _createRow(): HTMLTableRowElement {
  const row = document.createElement('tr');
  row.style.borderBottom = '1px solid var(--border)';
  return row;
}

export function renderUnifiedSummary(summaryEl: HTMLElement, result: UnifiedCheckResult): void {
  const parts: string[] = [];
  if (result.system.update_available) parts.push(`System: v${result.system.latest}`);
  if (result.summary.update_available > 0) parts.push(`${result.summary.update_available} ext update(s)`);
  if (parts.length === 0) parts.push(_tr('tools.up_to_date', 'All up to date'));

  const hasUpdates = result.system.update_available || result.summary.update_available > 0;
  summaryEl.textContent = parts.join(' | ');
  summaryEl.style.background = hasUpdates ? 'rgba(241,196,15,0.15)' : 'rgba(46,204,113,0.15)';
  summaryEl.style.color = hasUpdates ? '#f1c40f' : '#2ecc71';
}

export function renderUnifiedTable(
  bodyEl: HTMLElement,
  result: UnifiedCheckResult,
  handlers: { onApplySystemUpdate: () => void; onUpdateExtension: (name: string) => void; },
): void {
  const fragment = document.createDocumentFragment();

  const systemRow = _createRow();
  const systemName = document.createElement('td');
  _setCellPadding(systemName, true);
  systemName.textContent = 'YU AI Manager';
  systemRow.appendChild(systemName);

  const systemVersion = document.createElement('td');
  _setCellPadding(systemVersion);
  systemVersion.appendChild(_createCode(`v${result.system.current}`));
  if (result.system.update_available) {
    systemVersion.append(' ', '→', ' ');
    systemVersion.appendChild(_createCode(`v${result.system.latest}`));
  }
  systemRow.appendChild(systemVersion);

  const systemSource = document.createElement('td');
  _setCellPadding(systemSource);
  systemSource.appendChild(_createBadge('system'));
  systemRow.appendChild(systemSource);

  const systemStatus = document.createElement('td');
  _setCellPadding(systemStatus);
  systemStatus.appendChild(_createBadge(result.system.error ? 'unknown' : (result.system.update_available ? 'update_available' : 'up_to_date')));
  systemRow.appendChild(systemStatus);

  const systemAction = document.createElement('td');
  _setCellPadding(systemAction);
  const canApplySystem = result.system.update_available
    && result.system.install_type !== 'docker'
    && result.system.install_type !== 'tauri';
  if (canApplySystem) {
    systemAction.appendChild(_createActionButton(_tr('tools.apply_update', 'Update'), handlers.onApplySystemUpdate));
  } else {
    systemAction.appendChild(_createMutedText('-'));
  }
  systemRow.appendChild(systemAction);
  fragment.appendChild(systemRow);

  for (const ext of result.extensions) {
    const row = _createRow();

    const nameCell = document.createElement('td');
    _setCellPadding(nameCell);
    nameCell.textContent = ext.name;
    if (!ext.enabled) {
      nameCell.append(' ');
      const off = _createMutedText('(off)');
      off.title = 'disabled';
      nameCell.appendChild(off);
    }
    row.appendChild(nameCell);

    const versionCell = document.createElement('td');
    _setCellPadding(versionCell);
    versionCell.appendChild(_createCode(ext.version || '-'));
    if (ext.status === 'update_available' && ext.commits_behind) {
      versionCell.append(' ');
      versionCell.appendChild(_createMutedText(`(${Number(ext.commits_behind)} behind)`));
    }
    row.appendChild(versionCell);

    const sourceCell = document.createElement('td');
    _setCellPadding(sourceCell);
    if (ext.source === 'git') {
      sourceCell.appendChild(_createMutedText('git'));
    } else if (ext.source === 'builtin') {
      sourceCell.appendChild(_createMutedText(_tr('tools.unified_bundled', 'Bundled')));
    } else {
      sourceCell.appendChild(_createMutedText(ext.source));
    }
    row.appendChild(sourceCell);

    const statusCell = document.createElement('td');
    _setCellPadding(statusCell);
    statusCell.appendChild(_createBadge(ext.status));
    row.appendChild(statusCell);

    const actionCell = document.createElement('td');
    _setCellPadding(actionCell);
    if (ext.status === 'update_available') {
      actionCell.appendChild(_createActionButton(_tr('tools.apply_update', 'Update'), () => handlers.onUpdateExtension(ext.name)));
    } else {
      actionCell.appendChild(_createMutedText('-'));
    }
    row.appendChild(actionCell);

    fragment.appendChild(row);
  }

  bodyEl.replaceChildren(fragment);
}

export function renderUnifiedError(bodyEl: HTMLElement, summaryEl: HTMLElement | null, message: string): void {
  const row = document.createElement('tr');
  const cell = document.createElement('td');
  cell.colSpan = 5;
  cell.style.padding = '10px';
  cell.style.color = '#d32f2f';
  cell.textContent = `Failed: ${message}`;
  row.appendChild(cell);
  bodyEl.replaceChildren(row);

  if (summaryEl) {
    summaryEl.textContent = 'Error';
    summaryEl.style.background = 'rgba(231,76,60,0.15)';
    summaryEl.style.color = '#e74c3c';
  }
}

export function upsertProgressRow(stepsEl: HTMLElement, step: string, text: string): HTMLElement {
  let row = stepsEl.querySelector<HTMLElement>(`[data-step="${step}"]`);
  if (!row) {
    row = document.createElement('div');
    row.dataset.step = step;
    row.style.cssText = 'padding:4px 0;';
    stepsEl.appendChild(row);
  }
  row.textContent = text;
  return row;
}

export function appendProgressMessage(stepsEl: HTMLElement, message: string, color = '#d32f2f'): HTMLElement {
  const row = document.createElement('div');
  row.style.cssText = `color:${color};margin-top:8px;`;
  row.textContent = message;
  stepsEl.appendChild(row);
  return row;
}

export function appendRestartingMessage(stepsEl: HTMLElement): void {
  const msg = document.createElement('div');
  msg.style.cssText = 'margin-top:8px;color:var(--success,#2e7d32);font-weight:600;';
  msg.textContent = _tr('tools.update_restarting', 'Update complete. Restarting...');
  stepsEl.appendChild(msg);
}

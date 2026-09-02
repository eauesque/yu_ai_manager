/**
 * llm-router-page/render.ts — DOM rendering for the LLM Router dashboard.
 *
 * Important: any element whose textContent is dynamic must have its
 * data-i18n attribute removed before writing, otherwise the i18n runtime
 * (src/ts/i18n/core-shared.ts::applyTranslations) will overwrite the
 * dynamic value with the dictionary entry on its async post-load sweep.
 * This is the same trap that bit the scheduler page (v4.64.1).
 */

import { tr, type Backend, type StatusData } from './api';

function escapeHtmlInline(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function formatTime(iso: string | null): string {
  if (!iso) return '-';
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function _setText(id: string, value: string): void {
  const el = document.getElementById(id);
  if (!el) return;
  el.removeAttribute('data-i18n');
  el.textContent = value;
}

export function renderSummary(data: StatusData): void {
  const backends = data.backends ?? [];
  const totalModels = backends.reduce((sum, b) => sum + (b.model_count ?? 0), 0);
  const enabled = backends.filter((b) => !b.disabled).length;
  _setText('lrSummaryBackends', String(backends.length));
  _setText('lrSummaryEnabled', String(enabled));
  _setText('lrSummaryModels', String(totalModels));
  _setText('lrSummaryAliases', String(Object.keys(data.aliases ?? {}).length));
}

function _statusClass(status: string): string {
  if (status === 'ready' || status === 'ok') return 'ok';
  if (status === 'unreachable') return 'unreachable';
  if (status === 'error') return 'error';
  return '';
}

function _statusLabel(status: string): string {
  const key = `llm_router.status.${status === 'ready' ? 'ok' : status}`;
  return tr(key, status);
}

function _backendRow(b: Backend): string {
  const sourceBadge = `<span class="lr-badge ${escapeHtmlInline(b.source)}">${escapeHtmlInline(tr(`llm_router.source.${b.source}`, b.source))}</span>`;
  const disabledClass = b.disabled ? ' class="disabled"' : '';
  const disabledBadge = b.disabled
    ? `<span class="lr-badge disabled">${escapeHtmlInline(tr('llm_router.disabled_badge', '[DISABLED]'))}</span>`
    : '';
  const statusCell = `<span class="lr-status ${_statusClass(b.status)}">${escapeHtmlInline(_statusLabel(b.status))}</span>${disabledBadge}`;
  const alias = escapeHtmlInline(b.alias);
  const baseUrl = escapeHtmlInline(b.base_url);
  const slo = escapeHtmlInline(b.slo_state ?? '-');
  const lastSeen = escapeHtmlInline(formatTime(b.last_seen));
  const toggleAction = b.disabled ? 'enable' : 'disable';
  const toggleLabel = b.disabled
    ? escapeHtmlInline(tr('llm_router.enable', 'Enable'))
    : escapeHtmlInline(tr('llm_router.disable', 'Disable'));
  return `<tr${disabledClass}>
    <td><strong>${alias}</strong>${sourceBadge}</td>
    <td><code>${baseUrl}</code></td>
    <td>${statusCell}</td>
    <td>${slo}</td>
    <td>${b.model_count}</td>
    <td>${lastSeen}</td>
    <td><div class="lr-actions">
      <button type="button" class="lr-btn" data-action="refresh" data-alias="${alias}">${escapeHtmlInline(tr('llm_router.refresh', 'Refresh'))}</button>
      <button type="button" class="lr-btn ${b.disabled ? 'primary' : 'danger'}" data-action="${toggleAction}" data-alias="${alias}">${toggleLabel}</button>
    </div></td>
  </tr>`;
}

export function renderBackends(data: StatusData): void {
  const tbody = document.getElementById('lrBackendsBody');
  if (!tbody) return;
  const backends = data.backends ?? [];
  if (backends.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="lr-empty">${escapeHtmlInline(tr('llm_router.no_backends', 'No backends registered'))}</td></tr>`;
    return;
  }
  tbody.innerHTML = backends.map(_backendRow).join('');
}

export function renderAliases(data: StatusData): void {
  const tbody = document.getElementById('lrAliasesBody');
  if (!tbody) return;
  const aliases = data.aliases ?? {};
  const entries = Object.entries(aliases);
  if (entries.length === 0) {
    tbody.innerHTML = `<tr><td colspan="2" class="lr-empty">${escapeHtmlInline(tr('llm_router.no_aliases', 'No routing aliases configured'))}</td></tr>`;
    return;
  }
  tbody.innerHTML = entries.map(([alias, target]) => `<tr>
    <td><strong>${escapeHtmlInline(alias)}</strong></td>
    <td><code>${escapeHtmlInline(target)}</code></td>
  </tr>`).join('');
}

export function renderAll(data: StatusData): void {
  renderSummary(data);
  renderBackends(data);
  renderAliases(data);
}

import { _esc, _t } from './helpers';
import {
  DiscoveredCandidate,
  ENGINE_ICONS,
  ENGINE_LABELS,
  getDiscoveredCandidates,
  getServers,
} from './server-types';

function renderEmptyState(): string {
  return `
    <div style="text-align:center;padding:16px;color:var(--muted);">
      <p style="margin:0 0 8px;">${_t('tools.no_servers', 'No AI servers registered.')}</p>
      <p style="font-size:12px;margin:0 0 12px;">${_t('tools.servers_hint', 'Add servers to enable priority-based fallback and flexible switching.')}</p>
      <button class="btn btn-secondary btn-sm" data-action="toolsPageApi.aisMigrateFromLegacy" style="margin-right:8px;">${_t('tools.migrate_legacy', 'Import from current config')}</button>
      <button class="btn btn-primary btn-sm" data-action="toolsPageApi.aisShowAddDialog">+ ${_t('tools.add_server', 'Add Server')}</button>
    </div>`;
}

function renderDiscoveredCandidate(candidate: DiscoveredCandidate): string {
  const icon = candidate.provider === 'hailo_genai'
    ? ENGINE_ICONS.hailo_vlm
    : candidate.provider === 'openai_compat'
      ? ENGINE_ICONS.openai_compat
      : ENGINE_ICONS.ollama;
  const label = candidate.provider === 'hailo_genai'
    ? ENGINE_LABELS.hailo_vlm
    : candidate.provider === 'openai_compat'
      ? ENGINE_LABELS.openai_compat
      : ENGINE_LABELS.ollama;
  const statusText = candidate.suppressed_reason === 'policy_hidden'
    ? _t('tools.local_only_candidate', 'Local-only candidate')
    : candidate.suppressed_reason === 'matched_existing'
      ? _t('tools.matched_existing', 'Matched to existing server')
      : candidate.suppressed_reason === 'auth_required'
        ? _t('tools.auth_required', 'Auth required')
        : candidate.reachable
          ? _t('tools.reachable', 'Reachable')
          : _t('tools.unreachable', 'Unreachable');
  const matchable = candidate.matchable_servers || [];
  const selectId = `aisMatchSelect-${btoa(candidate.base_url).replace(/[^a-zA-Z0-9]/g, '')}`;
  return `
    <div class="ais-card">
      <div class="ais-card-header">
        <span class="ais-icon">${icon}</span>
        <div class="ais-card-info">
          <span class="ais-name">${_esc(candidate.display_preferred_url)}</span>
          <span class="ais-type">${_esc(label)}</span>
        </div>
        ${candidate.already_registered ? `<span class="ais-badge ais-badge-disabled">${_t('tools.already_registered', 'Already registered')}</span>` : candidate.matched_existing_server_name ? `<span class="ais-badge ais-badge-disabled">${_t('tools.matched_existing', 'Matched to existing server')}</span>` : `<span class="ais-badge ais-badge-active">${_t('tools.discovered', 'Discovered')}</span>`}
      </div>
      <div class="ais-card-details">
        <span class="ais-detail">${_t('tools.url', 'URL')}: ${_esc(candidate.base_url)}</span>
        <span class="ais-detail">${_t('tools.scope', 'Scope')}: ${_esc(candidate.scope)}</span>
        ${(candidate.model_name || candidate.model) ? `<span class="ais-detail">${_t('tools.model', 'Model')}: ${_esc(candidate.model_name || candidate.model || '')}</span>` : ''}
        <span class="ais-detail">${_t('tools.status', 'Status')}: ${_esc(statusText)}</span>
        ${candidate.matched_existing_server_name ? `<span class="ais-detail">${_t('tools.matched_server', 'Matched Server')}: ${_esc(candidate.matched_existing_server_name)}</span>` : ''}
      </div>
      <div class="ais-card-actions">
        <button class="btn btn-secondary btn-xs" data-action="toolsPageApi.aisTestDiscovered" data-action-arg="${_esc(candidate.base_url)}">${_t('tools.test_conn', 'Test')}</button>
        ${candidate.already_registered ? '' : `<button class="btn btn-primary btn-xs" data-action="toolsPageApi.aisRegisterDiscovered" data-action-arg="${_esc(candidate.base_url)}">${_t('tools.register', 'Register')}</button>`}
        ${!candidate.already_registered && matchable.length ? `<select id="${selectId}" class="btn btn-secondary btn-xs" style="max-width:180px;"><option value="">${_t('tools.select_server', 'Select server')}</option>${matchable.map((server) => `<option value="${_esc(server.id)}"${candidate.matched_existing_server_id === server.id ? ' selected' : ''}>${_esc(server.name)}</option>`).join('')}</select><button class="btn btn-secondary btn-xs" data-action="toolsPageApi.aisMatchDiscovered" data-action-arg="${_esc(candidate.base_url)}">${_t('tools.match_existing', 'Match existing')}</button>` : ''}
        ${candidate.matched_existing_server_id ? `<button class="btn btn-secondary btn-xs" data-action="toolsPageApi.aisUnmatchDiscovered" data-action-arg="${_esc(candidate.base_url)}">${_t('tools.clear_match', 'Clear match')}</button>` : ''}
        <button class="btn btn-secondary btn-xs" data-action="toolsPageApi.aisIgnoreDiscovered" data-action-arg="${_esc(candidate.base_url)}">${_t('tools.ignore', 'Ignore')}</button>
      </div>
    </div>`;
}

function renderIgnoredCandidate(candidate: DiscoveredCandidate): string {
  const icon = candidate.provider === 'hailo_genai' ? ENGINE_ICONS.hailo_vlm : ENGINE_ICONS.ollama;
  const label = candidate.provider === 'hailo_genai' ? ENGINE_LABELS.hailo_vlm : ENGINE_LABELS.ollama;
  return `
    <div class="ais-card ais-disabled">
      <div class="ais-card-header">
        <span class="ais-icon">${icon}</span>
        <div class="ais-card-info">
          <span class="ais-name">${_esc(candidate.display_preferred_url)}</span>
          <span class="ais-type">${_esc(label)}</span>
        </div>
        <span class="ais-badge ais-badge-disabled">${_t('tools.ignored', 'Ignored')}</span>
      </div>
      <div class="ais-card-details">
        <span class="ais-detail">${_t('tools.url', 'URL')}: ${_esc(candidate.base_url)}</span>
        <span class="ais-detail">${_t('tools.scope', 'Scope')}: ${_esc(candidate.scope)}</span>
      </div>
      <div class="ais-card-actions">
        <button class="btn btn-secondary btn-xs" data-action="toolsPageApi.aisUnignoreDiscovered" data-action-arg="${_esc(candidate.base_url)}">${_t('tools.unignore', 'Unignore')}</button>
      </div>
    </div>`;
}

export function renderServerList(container: HTMLElement): void {
  const servers = getServers();
  if (!servers.length) {
    container.innerHTML = renderEmptyState();
    return;
  }

  const allCandidates = getDiscoveredCandidates();
  const activeCandidates = allCandidates.filter((candidate) => !candidate.ignored);
  const ignoredCandidates = allCandidates.filter((candidate) => candidate.ignored);

  let html = '<div class="ais-list">';
  for (const server of servers) {
    const icon = ENGINE_ICONS[server.type] || '\u2699';
    const label = ENGINE_LABELS[server.type] || server.type;
    const activeClass = server.is_active ? ' ais-active' : '';
    const disabledClass = server.enabled ? '' : ' ais-disabled';
    const model = server.config.model || server.config.model_name || '';
    const url = server.config.base_url || '';
    html += `
      <div class="ais-card${activeClass}${disabledClass}" data-server-id="${server.id}">
        <div class="ais-card-header">
          <span class="ais-icon">${icon}</span>
          <div class="ais-card-info">
            <span class="ais-name">${_esc(server.name)}</span>
            <span class="ais-type">${label}</span>
          </div>
          ${server.is_active ? `<span class="ais-badge ais-badge-active">${_t('tools.active', 'Active')}</span>` : ''}
          ${!server.enabled ? `<span class="ais-badge ais-badge-disabled">${_t('tools.disabled', 'Disabled')}</span>` : ''}
          <span class="ais-status" id="aisStatus-${server.id}"></span>
        </div>
        <div class="ais-card-details">
          ${model ? `<span class="ais-detail">${_t('tools.model', 'Model')}: ${_esc(model)}</span>` : ''}
          ${url ? `<span class="ais-detail">${_t('tools.url', 'URL')}: ${_esc(url)}</span>` : ''}
          <span class="ais-detail">${_t('tools.priority', 'Priority')}: ${server.priority}</span>
        </div>
        <div class="ais-card-actions">
          ${!server.is_active && server.enabled ? `<button class="btn btn-primary btn-xs" data-action="toolsPageApi.aisActivate" data-action-arg="${server.id}">${_t('tools.set_active', 'Set Active')}</button>` : ''}
          <button class="btn btn-secondary btn-xs" data-action="toolsPageApi.aisTest" data-action-arg="${server.id}">${_t('tools.test_conn', 'Test')}</button>
          <button class="btn btn-secondary btn-xs" data-action="toolsPageApi.aisShowEditDialog" data-action-arg="${server.id}">${_t('tools.edit', 'Edit')}</button>
          <button class="btn btn-secondary btn-xs" data-action="toolsPageApi.aisToggleEnabledArg" data-action-arg="${server.id}:${!server.enabled}">${server.enabled ? _t('tools.disable', 'Disable') : _t('tools.enable', 'Enable')}</button>
          <button class="btn btn-danger btn-xs" data-action="toolsPageApi.aisRemove" data-action-arg="${server.id}">${_t('tools.remove', 'Remove')}</button>
        </div>
      </div>`;
  }
  html += '</div>';
  html += `<div style="margin-top:10px;display:flex;gap:8px;"><button class="btn btn-primary btn-sm" data-action="toolsPageApi.aisShowAddDialog">+ ${_t('tools.add_server', 'Add Server')}</button></div>`;
  if (activeCandidates.length || ignoredCandidates.length) {
    html += `<div style="margin-top:16px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.12);"><div style="font-weight:600;margin-bottom:8px;">${_t('tools.discovered_servers', 'Discovered Servers')}</div><div class="ais-list">${activeCandidates.map(renderDiscoveredCandidate).join('')}</div></div>`;
    if (ignoredCandidates.length) {
      html += `<div style="margin-top:12px;padding-top:12px;border-top:1px dashed rgba(255,255,255,0.12);"><div style="font-weight:600;margin-bottom:8px;">${_t('tools.ignored_discovered_servers', 'Ignored Discovered Servers')}</div><div class="ais-list">${ignoredCandidates.map(renderIgnoredCandidate).join('')}</div></div>`;
    }
  }
  container.innerHTML = html;
}

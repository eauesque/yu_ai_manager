import { apiFetch } from '../api';
import { _t } from './helpers';
import { errMsg, getDiscoveredCandidates, showToast } from './server-types';

function getCandidate(baseUrl: string) {
  const candidate = getDiscoveredCandidates().find((item) => item.base_url === baseUrl);
  if (!candidate) throw new Error(_t('tools.discovered_candidate_missing', 'Discovered candidate not found'));
  return candidate;
}

export async function aisActivate(serverId: string, reload: () => Promise<void>): Promise<void> {
  try {
    await apiFetch(`/api/analysis/servers/${serverId}/activate`, { method: 'POST' });
    await reload();
  } catch (e) {
    showToast(errMsg(e), 'error');
  }
}

export async function aisTest(serverId: string): Promise<void> {
  const el = document.getElementById(`aisStatus-${serverId}`);
  if (el) {
    el.textContent = '\u23F3';
    el.className = 'ais-status ais-testing';
  }
  try {
    const res = await apiFetch(`/api/analysis/servers/${serverId}/test`, { method: 'POST' });
    const data: { available: boolean; elapsed_ms: number } = await res.json();
    if (!el) return;
    if (data.available) {
      el.textContent = `\u2705 ${data.elapsed_ms}ms`;
      el.className = 'ais-status ais-ok';
    } else {
      el.textContent = '\u274C Unavailable';
      el.className = 'ais-status ais-error';
    }
  } catch {
    if (el) {
      el.textContent = '\u274C Error';
      el.className = 'ais-status ais-error';
    }
  }
}

export async function aisRemove(serverId: string, reload: () => Promise<void>): Promise<void> {
  if (!confirm(_t('tools.confirm_remove_server', 'Remove this AI server?'))) return;
  try {
    await apiFetch(`/api/analysis/servers/${serverId}`, { method: 'DELETE' });
    await reload();
  } catch (e) {
    showToast(errMsg(e), 'error');
  }
}

export async function aisToggleEnabled(serverId: string, enabled: boolean, reload: () => Promise<void>): Promise<void> {
  try {
    await apiFetch(`/api/analysis/servers/${serverId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    await reload();
  } catch (e) {
    showToast(errMsg(e), 'error');
  }
}

export async function aisMigrateFromLegacy(reload: () => Promise<void>): Promise<void> {
  try {
    const res = await apiFetch('/api/analysis/servers/migrate', { method: 'POST' });
    const data: { migrated?: number; error?: string } = await res.json();
    if (data.error) showToast(data.error, 'error');
    else {
      showToast(`${data.migrated} servers imported`, 'success');
      await reload();
    }
  } catch (e) {
    showToast(errMsg(e), 'error');
  }
}

async function withDiscoveredMutation(
  baseUrl: string,
  method: 'POST' | 'DELETE',
  path: string,
  body: Record<string, unknown>,
  successMessage: string,
  reload: () => Promise<void>,
): Promise<void> {
  try {
    await apiFetch(path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    showToast(successMessage, 'success');
    await reload();
  } catch (e) {
    showToast(errMsg(e), 'error');
  }
}

export async function aisRegisterDiscovered(baseUrl: string, reload: () => Promise<void>): Promise<void> {
  const candidate = getCandidate(baseUrl);
  await withDiscoveredMutation(baseUrl, 'POST', '/api/analysis/servers/discovered/register', {
    provider: candidate.provider,
    base_url: candidate.base_url,
    model: candidate.model,
    model_name: candidate.model_name,
  }, _t('tools.server_registered', 'Server registered'), reload);
}

export async function aisTestDiscovered(baseUrl: string): Promise<void> {
  try {
    const candidate = getCandidate(baseUrl);
    const res = await apiFetch('/api/analysis/servers/discovered/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: candidate.provider,
        base_url: candidate.base_url,
        model: candidate.model,
        model_name: candidate.model_name,
      }),
    });
    const data = await res.json();
    if (data.available) showToast(_t('tools.connection_ok', 'Connection OK'), 'success');
    else if (data.auth_required) showToast(_t('tools.auth_required', 'Auth required'), 'error');
    else showToast(data.error || _t('tools.connection_failed', 'Connection failed'), 'error');
  } catch (e) {
    showToast(errMsg(e), 'error');
  }
}

export async function aisMatchDiscovered(baseUrl: string, reload: () => Promise<void>): Promise<void> {
  const candidate = getCandidate(baseUrl);
  const selectId = `aisMatchSelect-${btoa(candidate.base_url).replace(/[^a-zA-Z0-9]/g, '')}`;
  const selectEl = document.getElementById(selectId) as HTMLSelectElement | null;
  const serverId = selectEl?.value || '';
  if (!serverId) {
    showToast(_t('tools.select_server_first', 'Select a server first'), 'error');
    return;
  }
  await withDiscoveredMutation(baseUrl, 'POST', '/api/analysis/servers/discovered/match', {
    provider: candidate.provider,
    base_url: candidate.base_url,
    server_id: serverId,
  }, _t('tools.match_saved', 'Match saved'), reload);
}

export async function aisUnmatchDiscovered(baseUrl: string, reload: () => Promise<void>): Promise<void> {
  const candidate = getCandidate(baseUrl);
  await withDiscoveredMutation(baseUrl, 'DELETE', '/api/analysis/servers/discovered/match', {
    base_url: candidate.base_url,
  }, _t('tools.match_cleared', 'Match cleared'), reload);
}

export async function aisIgnoreDiscovered(baseUrl: string, reload: () => Promise<void>): Promise<void> {
  const candidate = getCandidate(baseUrl);
  await withDiscoveredMutation(baseUrl, 'POST', '/api/analysis/servers/discovered/ignore', {
    base_url: candidate.base_url,
  }, _t('tools.ignored', 'Ignored'), reload);
}

export async function aisUnignoreDiscovered(baseUrl: string, reload: () => Promise<void>): Promise<void> {
  await withDiscoveredMutation(baseUrl, 'DELETE', '/api/analysis/servers/discovered/ignore', {
    base_url: baseUrl,
  }, _t('tools.unignore', 'Unignore'), reload);
}

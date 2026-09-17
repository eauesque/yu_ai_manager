/**
 * ai-analysis/server-list.ts -- entrypoint facade for list load and actions.
 */

import { apiFetch } from '../api';
import { DiscoveredCandidate, ServerEntry, setDiscoveredCandidates, setServers } from './server-types';
import { renderServerList } from './server-list-render';
import {
  aisActivate as activateServer,
  aisIgnoreDiscovered as ignoreDiscoveredCandidate,
  aisMatchDiscovered as matchDiscoveredCandidate,
  aisMigrateFromLegacy as migrateLegacyServers,
  aisRegisterDiscovered as registerDiscoveredCandidate,
  aisRemove as removeServer,
  aisTest as testServer,
  aisTestDiscovered as testDiscoveredCandidate,
  aisToggleEnabled as toggleServerEnabled,
  aisUnignoreDiscovered as unignoreDiscoveredCandidate,
  aisUnmatchDiscovered as unmatchDiscoveredCandidate,
} from './server-list-actions';

export async function loadAiServers(): Promise<void> {
  const container = document.getElementById('aiServersContainer');
  if (!container) return;

  try {
    const [res, discoveredRes] = await Promise.all([
      apiFetch('/api/analysis/servers'),
      apiFetch('/api/analysis/servers/discovered'),
    ]);
    const data: { servers: ServerEntry[] } = await res.json();
    const discoveredData: { candidates: DiscoveredCandidate[] } = await discoveredRes.json();
    setServers(data.servers || []);
    setDiscoveredCandidates(discoveredData.candidates || []);
    renderServerList(container);
  } catch {
    container.innerHTML = '<p style="color:var(--muted);font-size:12px;">Failed to load servers</p>';
  }
}

export async function aisActivate(serverId: string): Promise<void> {
  await activateServer(serverId, loadAiServers);
}

export async function aisTest(serverId: string): Promise<void> {
  await testServer(serverId);
}

export async function aisRemove(serverId: string): Promise<void> {
  await removeServer(serverId, loadAiServers);
}

export async function aisToggleEnabled(serverId: string, enabled: boolean): Promise<void> {
  await toggleServerEnabled(serverId, enabled, loadAiServers);
}

export async function aisMigrateFromLegacy(): Promise<void> {
  await migrateLegacyServers(loadAiServers);
}

export async function aisRegisterDiscovered(baseUrl: string): Promise<void> {
  await registerDiscoveredCandidate(baseUrl, loadAiServers);
}

export async function aisTestDiscovered(baseUrl: string): Promise<void> {
  await testDiscoveredCandidate(baseUrl);
}

export async function aisMatchDiscovered(baseUrl: string): Promise<void> {
  await matchDiscoveredCandidate(baseUrl, loadAiServers);
}

export async function aisUnmatchDiscovered(baseUrl: string): Promise<void> {
  await unmatchDiscoveredCandidate(baseUrl, loadAiServers);
}

export async function aisIgnoreDiscovered(baseUrl: string): Promise<void> {
  await ignoreDiscoveredCandidate(baseUrl, loadAiServers);
}

export async function aisUnignoreDiscovered(baseUrl: string): Promise<void> {
  await unignoreDiscoveredCandidate(baseUrl, loadAiServers);
}

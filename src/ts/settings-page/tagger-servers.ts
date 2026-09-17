/**
 * settings-page/tagger-servers.ts -- Mesh Tagger Peers management UI.
 *
 * Shows auto-discovered mesh tagger peers (read-only) with health check.
 * Servers are discovered via LAN Cowork mesh, no manual CRUD needed.
 */

import { getAppApi } from '../shared/browser-apis';

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback) || fallback;
}

function _esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function _api(url: string, opts?: RequestInit): Promise<any> {
  const res = await fetch(url, {
    ...opts,
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      ...(opts?.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const json = await res.json();
  if (json.data) return json.data;
  return json;
}

function _showToast(msg: string, type: 'success' | 'error'): void {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = msg;
  toast.className = `toast show ${type === 'error' ? 'toast-error' : ''}`;
  setTimeout(() => { toast.className = 'toast'; }, 3000);
}

/* ------------------------------------------------------------------ */
/* Types                                                                */
/* ------------------------------------------------------------------ */

interface MeshPeer {
  id: string;
  name: string;
  type: string;
  priority: number;
  enabled: boolean;
  status?: string;
}

/* ------------------------------------------------------------------ */
/* State                                                                */
/* ------------------------------------------------------------------ */

let _peers: MeshPeer[] = [];

/* ------------------------------------------------------------------ */
/* Load & render                                                        */
/* ------------------------------------------------------------------ */

export async function loadTaggerServers(): Promise<void> {
  const container = document.getElementById('tsrContainer');
  if (!container) return;

  try {
    const data = await _api('/api/tagger-servers');
    _peers = data.servers || [];
    _renderAll(container);
  } catch {
    container.textContent = 'Failed to load tagger peers';
  }
}

function _renderAll(container: HTMLElement): void {
  // Clear previous content
  container.textContent = '';

  // Mesh mode banner
  const banner = document.createElement('div');
  banner.style.cssText = 'margin-bottom:16px;display:flex;align-items:center;gap:8px;';
  const bannerText = document.createElement('span');
  bannerText.style.cssText = 'font-size:13px;color:var(--muted);';
  bannerText.textContent = '\uD83C\uDF10 ' + _t('settings.tsr_mesh_mode', 'Mesh mode \u2014 peers are auto-discovered via LAN Cowork');
  banner.appendChild(bannerText);
  container.appendChild(banner);

  if (!_peers.length) {
    const empty = document.createElement('div');
    empty.style.cssText = 'text-align:center;padding:24px;color:var(--muted);';
    const p1 = document.createElement('p');
    p1.style.cssText = 'margin:0 0 8px;';
    p1.textContent = _t('settings.tsr_no_peers', 'No tagger peers found on the mesh.');
    const p2 = document.createElement('p');
    p2.style.cssText = 'font-size:12px;margin:0;';
    p2.textContent = _t('settings.tsr_no_peers_hint', 'Peers with tagger capability will appear here automatically when they join the mesh.');
    empty.appendChild(p1);
    empty.appendChild(p2);
    container.appendChild(empty);
    return;
  }

  // Peer cards (read-only)
  const list = document.createElement('div');
  list.className = 'tsr-list';
  for (const p of _peers) {
    const statusIcon = p.status === 'online' ? '\u2705' : '\u26AA';
    const statusLabel = p.status === 'online'
      ? _t('settings.tsr_online', 'Online')
      : _t('settings.tsr_offline', 'Offline');

    const card = document.createElement('div');
    card.className = 'tsr-card';
    card.dataset.serverId = p.id;

    const header = document.createElement('div');
    header.className = 'tsr-card-header';

    const icon = document.createElement('span');
    icon.className = 'tsr-icon';
    icon.textContent = '\uD83E\uDD16';

    const info = document.createElement('div');
    info.className = 'tsr-card-info';
    const nameEl = document.createElement('span');
    nameEl.className = 'tsr-name';
    nameEl.textContent = p.name;
    const typeEl = document.createElement('span');
    typeEl.className = 'tsr-type';
    typeEl.textContent = 'Mesh Peer';
    info.appendChild(nameEl);
    info.appendChild(typeEl);

    const badge = document.createElement('span');
    badge.className = 'tsr-badge';
    badge.textContent = statusIcon + ' ' + statusLabel;

    const statusEl = document.createElement('span');
    statusEl.className = 'tsr-status';
    statusEl.id = 'tsrStatus-' + p.id;

    header.appendChild(icon);
    header.appendChild(info);
    header.appendChild(badge);
    header.appendChild(statusEl);
    card.appendChild(header);
    list.appendChild(card);
  }
  container.appendChild(list);

  // Health check button
  const controls = document.createElement('div');
  controls.style.cssText = 'margin-top:12px;display:flex;gap:8px;align-items:center;';
  const healthBtn = document.createElement('button');
  healthBtn.className = 'btn btn-secondary btn-sm';
  healthBtn.dataset.action = 'settingsPageApi.tsrHealthCheck';
  healthBtn.textContent = _t('settings.tsr_health', 'Health Check');
  controls.appendChild(healthBtn);
  container.appendChild(controls);
}

/* ------------------------------------------------------------------ */
/* Health check                                                         */
/* ------------------------------------------------------------------ */

export async function tsrHealthCheck(): Promise<void> {
  try {
    const data = await _api('/api/tagger-servers/health');
    const peers = data.peers || [];
    for (const p of peers) {
      const el = document.getElementById('tsrStatus-' + p.peer_id);
      if (el) {
        if (p.status === 'online') {
          el.textContent = p.is_local ? '\u2705 Local' : '\u2705 OK';
          el.className = 'tsr-status tsr-ok';
        } else {
          el.textContent = '\u274C Offline';
          el.className = 'tsr-status tsr-error';
        }
      }
    }
    _showToast(peers.length + ' peer(s) checked', 'success');
  } catch (e) {
    _showToast(String(e), 'error');
  }
}

/* ------------------------------------------------------------------ */
/* Legacy stubs (keep exports to avoid build errors in settings-page)   */
/* ------------------------------------------------------------------ */

export async function tsrSetMode(): Promise<void> { /* no-op: mesh uses work-stealing */ }
export async function tsrTest(_serverId: string): Promise<void> { /* removed: mesh peers */ }
export async function tsrRemove(_serverId: string): Promise<void> { /* removed: mesh peers */ }
export async function tsrToggleEnabled(_arg: string): Promise<void> { /* removed: mesh peers */ }
export async function tsrMigrateLegacy(): Promise<void> { /* removed: mesh peers */ }
export function tsrShowAddDialog(): void { /* removed: mesh peers */ }
export function tsrShowEditDialog(_serverId: string): void { /* removed: mesh peers */ }
export function tsrOnTypeChange(): void { /* removed */ }
export function tsrCloseDialog(): void { document.getElementById('tsrDialog')?.remove(); }
export async function tsrSaveDialog(_existingId: string): Promise<void> { /* removed: mesh peers */ }

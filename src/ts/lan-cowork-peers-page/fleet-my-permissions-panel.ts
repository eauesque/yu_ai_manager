/**
 * lan-cowork-peers-page/fleet-my-permissions-panel.ts
 * 自分の権限セクション: リモートピアが許可している操作を読み取り専用で表示する。
 */
import { getMyPermissions, showToast, tr, PeerPermissionResult } from './api';

const ERROR_I18N: Record<string, string> = {
  peer_offline:       'lc_peers.my_permissions.error_peer_offline',
  peer_unreachable:   'lc_peers.my_permissions.error_peer_unreachable',
  auth_failed:        'lc_peers.my_permissions.error_auth_failed',
  timeout:            'lc_peers.my_permissions.error_timeout',
  no_pairing_token:   'lc_peers.my_permissions.error_no_pairing_token',
};

const ERROR_FALLBACK: Record<string, string> = {
  peer_offline:       'オフライン（到達未試行）',
  peer_unreachable:   '到達不可',
  auth_failed:        '認証失敗',
  timeout:            'タイムアウト',
  no_pairing_token:   'ペアリング未完了',
};

function peerLabel(peer: PeerPermissionResult): string {
  const name = peer.name;
  const suffix = peer.peer_id.slice(-4);
  const dot = peer.status === 'online' ? '●' : '○';
  const display = name.length > 20 ? name.slice(0, 20) + '…' : name;
  return `${display} ${suffix} ${dot}`;
}

function cellText(value: boolean | null, masterOn: boolean | null, error: string | null): string {
  if (error) return '—';
  if (value === null) return '—';
  if (value && masterOn === false) return '✓ ⚠';
  return value ? '✓' : '✗';
}

function cellTitle(value: boolean | null, masterOn: boolean | null, error: string | null): string {
  if (error) {
    const key = ERROR_I18N[error] ?? '';
    return tr(key, ERROR_FALLBACK[error] ?? error);
  }
  if (value && masterOn === false) {
    return tr(
      'lc_peers.my_permissions.master_off_warning',
      'allowlist に含まれているがリモートの master が OFF のため実際には操作不可',
    );
  }
  return '';
}

function renderTable(peers: PeerPermissionResult[]): void {
  const tbody = document.getElementById('lcMyPermTbody');
  const emptyEl = document.getElementById('lcMyPermEmpty');
  if (!tbody || !emptyEl) return;
  tbody.replaceChildren();

  const emptyLink = document.getElementById('lcMyPermEmptyLink') as HTMLAnchorElement | null;
  if (peers.length === 0) {
    emptyEl.hidden = false;
    if (emptyLink) emptyLink.hidden = false;
    return;
  }
  emptyEl.hidden = true;
  if (emptyLink) emptyLink.hidden = true;

  for (const peer of peers) {
    const row = document.createElement('tr');

    const tdName = document.createElement('td');
    tdName.textContent = peerLabel(peer);
    tdName.title = `${peer.name} (${peer.peer_id})`;
    row.appendChild(tdName);

    for (const op of ['restart', 'update', 'log_stream'] as const) {
      const td = document.createElement('td');
      td.style.textAlign = 'center';
      const val = (peer as any)[op] as boolean | null;
      td.textContent = cellText(val, peer.allow_remote_update, peer.error);
      const title = cellTitle(val, peer.allow_remote_update, peer.error);
      if (title) td.title = title;
      if (peer.error) td.style.color = '#999';
      else if (val === true && peer.allow_remote_update === false) td.style.color = '#e88000';
      row.appendChild(td);
    }
    tbody.appendChild(row);
  }
}

async function load(bust: boolean): Promise<void> {
  try {
    const res = await getMyPermissions(bust);
    if (res.ok && res.peers) renderTable(res.peers);
  } catch {
    showToast(tr('lc_peers.my_permissions.load_err', '権限情報の取得に失敗しました'));
  }
}

export function initMyPermissionsPanel(): void {
  const section = document.getElementById('lcMyPermissionsSection');
  if (!section) return;

  void load(false);
  document.getElementById('lcMyPermRefreshBtn')?.addEventListener('click', () => void load(true));
}

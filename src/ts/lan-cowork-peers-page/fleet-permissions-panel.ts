/**
 * lan-cowork-peers-page/fleet-permissions-panel.ts
 * Fleet 許可セクション: このノードへの操作許可をピア別マトリクスで管理する。
 */
import {
  discoverPeersWithAuth,
  getFleetAllowlists,
  saveFleetAllowlists,
  showToast,
  tr,
} from './api';
import { customConfirm } from './confirm-modal';

type OpKey = 'restart' | 'update' | 'log_stream';

interface PeerRow {
  peer_id: string;
  name: string;
  status: string;
}

interface PermState {
  masterSwitch: boolean;
  restart: Set<string>;
  update: Set<string>;
  log_stream: Set<string>;
}

let _state: PermState = {
  masterSwitch: false,
  restart: new Set(),
  update: new Set(),
  log_stream: new Set(),
};
let _peers: PeerRow[] = [];

function peerLabel(peer: PeerRow): string {
  const name = peer.name;
  const suffix = peer.peer_id.slice(-4);
  const dot = peer.status === 'online' ? '●' : '○';
  const display = name.length > 20 ? name.slice(0, 20) + '…' : name;
  return `${display} ${suffix} ${dot}`;
}

function syncRestartCell(peerId: string): void {
  const updateCb = document.getElementById(`lc-fp-update-${peerId}`) as HTMLInputElement | null;
  const restartCb = document.getElementById(`lc-fp-restart-${peerId}`) as HTMLInputElement | null;
  if (!updateCb || !restartCb) return;
  if (updateCb.checked) {
    restartCb.checked = true;
    restartCb.disabled = true;
    restartCb.title = tr(
      'lc_peers.fleet_permissions.restart_forced_by_update',
      '「更新」が有効のため自動的に許可されます',
    );
  } else {
    restartCb.disabled = false;
    restartCb.title = '';
  }
}

function applyMasterState(masterOn: boolean): void {
  // Toggle the inline OFF badge next to the master switch label.
  const badge = document.getElementById('lcFleetPermMasterOffBadge');
  if (badge) badge.hidden = masterOn;

  // Sync restart-update dependency regardless of master state.
  const tbody = document.getElementById('lcFleetPermTbody');
  tbody?.querySelectorAll<HTMLInputElement>('input[data-op="restart"]').forEach((cb) => {
    syncRestartCell(cb.dataset.peerId!);
  });
}

function renderTable(): void {
  const tbody = document.getElementById('lcFleetPermTbody');
  const emptyEl = document.getElementById('lcFleetPermEmpty');
  if (!tbody || !emptyEl) return;
  tbody.replaceChildren();

  const masterOn = _state.masterSwitch;

  applyMasterState(masterOn);

  const emptyLink = document.getElementById('lcFleetPermEmptyLink') as HTMLAnchorElement | null;
  if (_peers.length === 0) {
    emptyEl.hidden = false;
    if (emptyLink) emptyLink.hidden = false;
    return;
  }
  emptyEl.hidden = true;
  if (emptyLink) emptyLink.hidden = true;

  for (const peer of _peers) {
    const row = document.createElement('tr');

    const tdName = document.createElement('td');
    tdName.textContent = peerLabel(peer);
    tdName.title = `${peer.name} (${peer.peer_id})`;
    row.appendChild(tdName);

    for (const op of ['restart', 'update', 'log_stream'] as OpKey[]) {
      const td = document.createElement('td');
      td.style.textAlign = 'center';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.id = `lc-fp-${op}-${peer.peer_id}`;
      cb.dataset.peerId = peer.peer_id;
      cb.dataset.op = op;
      cb.checked = (_state[op] as Set<string>).has(peer.peer_id);
      if (op === 'update') {
        cb.addEventListener('change', () => syncRestartCell(peer.peer_id));
      }
      td.appendChild(cb);
      row.appendChild(td);
    }
    tbody.appendChild(row);
    syncRestartCell(peer.peer_id);
  }
}

function collectCurrentState(): PermState {
  const tbody = document.getElementById('lcFleetPermTbody');
  const masterCb = document.getElementById('lcFleetPermMasterSwitch') as HTMLInputElement | null;
  const next: PermState = {
    masterSwitch: masterCb?.checked ?? false,
    restart: new Set<string>(),
    update: new Set<string>(),
    log_stream: new Set<string>(),
  };
  tbody?.querySelectorAll<HTMLInputElement>('input[data-peer-id]').forEach((cb) => {
    if (!cb.checked) return;
    const pid = cb.dataset.peerId!;
    const op = cb.dataset.op as OpKey;
    if (op === 'restart') next.restart.add(pid);
    if (op === 'update') { next.update.add(pid); next.restart.add(pid); }
    if (op === 'log_stream') next.log_stream.add(pid);
  });
  return next;
}

function computeRemovals(before: PermState, after: PermState): string[] {
  const labels: Record<OpKey, string> = {
    restart: tr('lc_peers.fleet_permissions.col_restart', '再起動'),
    update: tr('lc_peers.fleet_permissions.col_update', '更新+再起動'),
    log_stream: tr('lc_peers.fleet_permissions.col_log_stream', 'ログ配信'),
  };
  const removed: string[] = [];
  for (const op of ['restart', 'update', 'log_stream'] as OpKey[]) {
    const beforeSet = before[op] as Set<string>;
    const afterSet = after[op] as Set<string>;
    for (const pid of beforeSet) {
      if (!afterSet.has(pid)) {
        const peer = _peers.find((p) => p.peer_id === pid);
        removed.push(`${labels[op]}: ${peer?.name ?? pid}`);
      }
    }
  }
  return removed;
}

async function confirmAndSave(): Promise<void> {
  const newState = collectCurrentState();
  const masterCb = document.getElementById('lcFleetPermMasterSwitch') as HTMLInputElement | null;
  const newMaster = masterCb?.checked ?? false;
  const oldMaster = _state.masterSwitch;

  if (oldMaster && !newMaster) {
    const msg = tr(
      'lc_peers.fleet_permissions.confirm_master_off',
      'リモート Fleet 操作を一括拒否します。\n全ピアからの再起動・更新・ログ配信を受け付けなくなります。\n続行しますか？',
    );
    const ok = await customConfirm(msg, {
      danger: true,
      okText: tr('lc_peers.fleet_permissions.confirm_master_off_ok', 'OFFにする'),
      cancelText: tr('common.cancel', 'キャンセル'),
    });
    if (!ok) {
      // Restore checkbox state AND re-sync the badge UI (was a bug).
      if (masterCb) {
        masterCb.checked = true;
        applyMasterState(true);
      }
      return;
    }
  }

  const removals = computeRemovals(_state, newState);
  if (removals.length > 0) {
    const prefix = tr('lc_peers.fleet_permissions.confirm_reduce_prefix', '以下の操作許可を削除します:');
    const suffix = tr('lc_peers.fleet_permissions.confirm_reduce_suffix', '続行しますか？');
    const items = removals.map((r) => `  ・ ${r}`).join('\n');
    const ok = await customConfirm(`${prefix}\n${items}\n${suffix}`, {
      danger: true,
      okText: tr('lc_peers.fleet_permissions.confirm_reduce_ok', '削除する'),
      cancelText: tr('common.cancel', 'キャンセル'),
    });
    if (!ok) return;
  }

  const statusEl = document.getElementById('lcFleetPermSaveStatus') as HTMLElement | null;
  if (statusEl) { statusEl.hidden = false; statusEl.textContent = tr('lc_peers.fleet_permissions.saving', '保存中...'); }

  try {
    const payload = {
      allow_remote_update: newMaster,
      allow_update_from: [...newState.update],
      allow_restart_from: [...newState.restart].filter((pid) => !newState.update.has(pid)),
      allow_log_stream_from: [...newState.log_stream],
    };
    const res = await saveFleetAllowlists(payload);
    if (res.ok) {
      _state = newState;
      showToast(tr('lc_peers.fleet_permissions.save_ok', '保存しました'));
      if (statusEl) statusEl.textContent = tr('lc_peers.fleet_permissions.saved', '保存済み');
    } else {
      showToast(tr('lc_peers.fleet_permissions.save_err', '保存に失敗しました') + ': ' + (res.error ?? ''));
      if (statusEl) statusEl.hidden = true;
    }
  } catch {
    showToast(tr('lc_peers.fleet_permissions.save_err', '保存に失敗しました'));
    if (statusEl) statusEl.hidden = true;
  }
}

async function loadData(): Promise<void> {
  try {
    const [peersRes, allowlistRes] = await Promise.all([
      discoverPeersWithAuth(),
      getFleetAllowlists(),
    ]);
    const now = Math.floor(Date.now() / 1000);
    _peers = (peersRes.peers ?? [])
      .filter((p) => {
        const outbound = p.token_expires_at != null && p.token_expires_at > now;
        const inbound = p.has_inbound_token === true;
        return outbound || inbound;
      })
      .map((p) => ({
        peer_id: p.peer_id,
        name: p.name || p.peer_id,
        status: p.status,
      }));
    _state = {
      masterSwitch: allowlistRes.allow_remote_update ?? false,
      restart: new Set([...(allowlistRes.allow_restart_from ?? []), ...(allowlistRes.allow_update_from ?? [])]),
      update: new Set(allowlistRes.allow_update_from ?? []),
      log_stream: new Set(allowlistRes.allow_log_stream_from ?? []),
    };
    const masterCb = document.getElementById('lcFleetPermMasterSwitch') as HTMLInputElement | null;
    if (masterCb) masterCb.checked = _state.masterSwitch;
  } catch { /* silent */ }
  renderTable();
}

export function initFleetPermissionsPanel(): void {
  const section = document.getElementById('lcFleetPermissionsSection');
  if (!section) return;

  loadData();

  document.getElementById('lcFleetPermRefreshBtn')?.addEventListener('click', () => void loadData());
  document.getElementById('lcFleetPermSaveBtn')?.addEventListener('click', () => void confirmAndSave());

  const masterCb = document.getElementById('lcFleetPermMasterSwitch') as HTMLInputElement | null;
  masterCb?.addEventListener('change', () => applyMasterState(masterCb.checked));
}

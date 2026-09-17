/**
 * lan-cowork-peers-page/tokens-panel.ts
 * Renders the active peer tokens table and handles revoke actions.
 *
 * Dynamic row data-action values:
 *   lc-peers-revoke   — revoke the token for a peer
 *
 * The "Pair" button for un-paired peers is handled by pair-modal.ts.
 * Its data-action is lc-peers-pair-initiate, but the proxy endpoint is
 * implemented in Task 16 — so this task stubs it with a toast.
 */

import { listTokens, revokeToken, clientPairRequest, showToast, tr, TokenRecord } from './api';
import { openClientPairFlow } from './pair-modal';
import { customConfirm } from './confirm-modal';

function formatTime(ts: number | null): string {
  if (ts === null) return '—';
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
}

/** IDs of peers that have lost auth (received peer.auth_lost SSE). */
const _authLostPeers = new Set<string>();

export function markAuthLost(peerId: string): void {
  _authLostPeers.add(peerId);
}

function createRevokeButton(peerId: string): HTMLButtonElement {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'lc-peers-btn lc-peers-btn-danger';
  btn.dataset['action'] = 'lc-peers-revoke';
  btn.dataset['peerId'] = peerId;
  btn.dataset['i18n'] = 'lc_peers.peers.revoke';
  btn.textContent = tr('lc_peers.peers.revoke', '失効');
  return btn;
}

function createTokenRow(tok: TokenRecord): HTMLTableRowElement {
  const row = document.createElement('tr');
  row.dataset['peerId'] = tok.peer_id;

  const tdPeer = document.createElement('td');
  tdPeer.textContent = tok.peer_id;

  // Status badge
  const tdStatus = document.createElement('td');
  const badge = document.createElement('span');
  const isAuthLost = _authLostPeers.has(tok.peer_id);
  badge.className = `lc-peers-badge ${isAuthLost ? 'lc-peers-badge-pending' : 'lc-peers-badge-paired'}`;
  if (isAuthLost) {
    badge.dataset['i18n'] = 'lc_peers.peers.status.auth_lost';
    badge.textContent = tr('lc_peers.peers.status.auth_lost', '再ペアリング必要');
  } else {
    badge.dataset['i18n'] = 'lc_peers.peers.status.paired';
    badge.textContent = tr('lc_peers.peers.status.paired', 'ペアリング済み');
  }
  tdStatus.appendChild(badge);

  const tdExpires = document.createElement('td');
  tdExpires.className = 'lc-peers-expires';
  tdExpires.textContent = formatTime(tok.expires_at);

  const tdActions = document.createElement('td');
  tdActions.appendChild(createRevokeButton(tok.peer_id));

  row.appendChild(tdPeer);
  row.appendChild(tdStatus);
  row.appendChild(tdExpires);
  row.appendChild(tdActions);
  return row;
}

export async function loadTokens(): Promise<void> {
  const tbody = document.getElementById('lcPeersPeersTbody');
  const table = document.getElementById('lcPeersPeersTable') as HTMLTableElement | null;
  const empty = document.getElementById('lcPeersPeersEmpty');
  if (!tbody || !table || !empty) return;

  let data;
  try {
    data = await listTokens();
  } catch {
    showToast(tr('lc_peers.peers.load_error', 'トークン一覧の取得に失敗しました'));
    return;
  }

  if (!data.ok || !data.tokens) {
    showToast(data.error ?? tr('lc_peers.peers.load_error', 'トークン一覧の取得に失敗しました'));
    return;
  }

  // Clear existing rows using DOM API
  while (tbody.firstChild) {
    tbody.removeChild(tbody.firstChild);
  }

  if (data.tokens.length === 0) {
    table.hidden = true;
    empty.hidden = false;
  } else {
    for (const tok of data.tokens) {
      tbody.appendChild(createTokenRow(tok));
    }
    table.hidden = false;
    empty.hidden = true;
  }
}

export function initTokensPanel(): void {
  const section = document.getElementById('lcPeersPeersSection');
  if (!section) return;

  section.addEventListener('click', async (e) => {
    const btn = (e.target as Element).closest('[data-action]');
    if (!btn) return;
    const action = (btn as HTMLElement).dataset['action'];
    const peerId = (btn as HTMLElement).dataset['peerId'] ?? '';

    if (action === 'lc-peers-refresh-peers') {
      await loadTokens();
      return;
    }

    if (action === 'lc-peers-revoke' && peerId) {
      const ok = await customConfirm(
        tr('lc_peers.peers.revoke_confirm', 'このピアのトークンを失効させますか？'),
        {
          danger: true,
          okText: tr('lc_peers.peers.revoke', '失効'),
          cancelText: tr('common.cancel', 'キャンセル'),
        },
      );
      if (!ok) return;
      (btn as HTMLButtonElement).disabled = true;
      try {
        const resp = await revokeToken(peerId);
        if (!resp.ok) {
          showToast(resp.error ?? tr('lc_peers.peers.revoke_error', '失効に失敗しました'));
          (btn as HTMLButtonElement).disabled = false;
          return;
        }
        showToast(tr('lc_peers.peers.revoked', 'トークンを失効させました'));
        _authLostPeers.delete(peerId);
        await loadTokens();
      } catch {
        showToast(tr('lc_peers.peers.revoke_error', '失効に失敗しました'));
        (btn as HTMLButtonElement).disabled = false;
      }
      return;
    }

    // lc-peers-pair-initiate — proxy to remote peer via local server
    if (action === 'lc-peers-pair-initiate' && peerId) {
      (btn as HTMLButtonElement).disabled = true;
      let resp;
      try {
        resp = await clientPairRequest(peerId);
      } catch {
        showToast(tr('lc_peers.peers.pair_request_error', 'ペアリングリクエストに失敗しました'));
        (btn as HTMLButtonElement).disabled = false;
        return;
      }
      (btn as HTMLButtonElement).disabled = false;
      if (!resp.ok || !resp.request_id || !resp.sas) {
        showToast(resp.error ?? tr('lc_peers.peers.pair_request_error', 'ペアリングリクエストに失敗しました'));
        return;
      }
      // Open PIN entry modal (client flow)
      openClientPairFlow(peerId, resp.request_id, resp.sas);
      return;
    }
  });

  // Initial load
  loadTokens();
}

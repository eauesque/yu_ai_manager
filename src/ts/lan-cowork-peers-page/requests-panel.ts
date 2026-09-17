/**
 * lan-cowork-peers-page/requests-panel.ts
 * Renders the pending pairing requests table and handles approve/reject actions.
 *
 * Dynamic row data-action values:
 *   lc-peers-confirm-sas-approve  — approve an incoming pairing request after SAS match
 *   lc-peers-reject   — reject an incoming pairing request
 */

import { listPairingRequests, approveRequest, rejectRequest, showToast, tr, PairingRequest } from './api';

/** Callbacks so other modules can react to approve/reject. */
export type RequestsPanelCallbacks = {
  onApproved?: (request_id: string, pin: string, peer_id: string) => void;
};

function formatTime(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
}

function createActionButton(
  action: string,
  requestId: string,
  i18nKey: string,
  fallbackLabel: string,
  extraClasses?: string,
): HTMLButtonElement {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = `lc-peers-btn${extraClasses ? ' ' + extraClasses : ''}`;
  btn.dataset['action'] = action;
  btn.dataset['requestId'] = requestId;
  btn.dataset['i18n'] = i18nKey;
  btn.textContent = tr(i18nKey, fallbackLabel);
  return btn;
}

function createRequestRow(req: PairingRequest): HTMLTableRowElement {
  const tr_el = document.createElement('tr');
  tr_el.dataset['requestId'] = req.request_id;
  tr_el.dataset['peerId'] = req.peer_id;

  const tdHost = document.createElement('td');
  tdHost.textContent = `${req.host}:${req.port}`;

  const tdPeer = document.createElement('td');
  tdPeer.textContent = req.peer_id;

  const tdTime = document.createElement('td');
  tdTime.textContent = formatTime(req.created_at);

  const tdActions = document.createElement('td');
  const sas = document.createElement('div');
  sas.className = 'lc-peers-request-sas';
  sas.textContent = `認証コード: ${req.sas}`;
  const sasHint = document.createElement('div');
  sasHint.className = 'lc-peers-request-sas-hint';
  sasHint.textContent = '↑ 相手のデバイス画面のコードと一致していますか？';
  tdActions.appendChild(sas);
  tdActions.appendChild(sasHint);
  tdActions.appendChild(createActionButton(
    'lc-peers-confirm-sas-approve', req.request_id,
    'lc_peers.requests.approve_sas_match', '一致している → 承認', 'lc-peers-btn-approve',
  ));
  tdActions.appendChild(document.createTextNode(' '));
  tdActions.appendChild(createActionButton(
    'lc-peers-reject', req.request_id,
    'lc_peers.requests.reject', '拒否', 'lc-peers-btn-danger',
  ));

  tr_el.appendChild(tdHost);
  tr_el.appendChild(tdPeer);
  tr_el.appendChild(tdTime);
  tr_el.appendChild(tdActions);
  return tr_el;
}

export async function loadRequests(callbacks?: RequestsPanelCallbacks): Promise<void> {
  const tbody = document.getElementById('lcPeersRequestsTbody');
  const table = document.getElementById('lcPeersRequestsTable') as HTMLTableElement | null;
  const empty = document.getElementById('lcPeersRequestsEmpty');
  if (!tbody || !table || !empty) return;

  let data;
  try {
    data = await listPairingRequests();
  } catch {
    showToast(tr('lc_peers.requests.load_error', 'リクエスト一覧の取得に失敗しました'));
    return;
  }

  if (!data.ok || !data.requests) {
    showToast(data.error ?? tr('lc_peers.requests.load_error', 'リクエスト一覧の取得に失敗しました'));
    return;
  }

  const pending = data.requests.filter(r => r.status === 'pending');

  // Clear existing rows using DOM API (avoids innerHTML)
  while (tbody.firstChild) {
    tbody.removeChild(tbody.firstChild);
  }

  if (pending.length === 0) {
    table.hidden = true;
    empty.hidden = false;
  } else {
    for (const req of pending) {
      tbody.appendChild(createRequestRow(req));
    }
    table.hidden = false;
    empty.hidden = true;
  }
}

export function initRequestsPanel(callbacks?: RequestsPanelCallbacks): void {
  const section = document.getElementById('lcPeersRequestsSection');
  if (!section) return;

  section.addEventListener('click', async (e) => {
    const btn = (e.target as Element).closest('[data-action]');
    if (!btn) return;
    const action = (btn as HTMLElement).dataset['action'];
    const requestId = (btn as HTMLElement).dataset['requestId'] ?? '';

    if (action === 'lc-peers-refresh-requests') {
      await loadRequests(callbacks);
      return;
    }

    if (action === 'lc-peers-confirm-sas-approve' && requestId) {
      (btn as HTMLButtonElement).disabled = true;
      const row = (btn as Element).closest('tr') as HTMLTableRowElement | null;
      const peerId = row?.dataset['peerId'] ?? '';
      try {
        const resp = await approveRequest(requestId);
        if (!resp.ok) {
          showToast(resp.error ?? tr('lc_peers.requests.approve_error', '承認に失敗しました'));
          (btn as HTMLButtonElement).disabled = false;
          return;
        }
        const pin = resp.pin ?? '';
        callbacks?.onApproved?.(requestId, pin, peerId);
        await loadRequests(callbacks);
      } catch {
        showToast(tr('lc_peers.requests.approve_error', '承認に失敗しました'));
        (btn as HTMLButtonElement).disabled = false;
      }
      return;
    }

    if (action === 'lc-peers-reject' && requestId) {
      (btn as HTMLButtonElement).disabled = true;
      try {
        const resp = await rejectRequest(requestId);
        if (!resp.ok) {
          showToast(resp.error ?? tr('lc_peers.requests.reject_error', '拒否に失敗しました'));
          (btn as HTMLButtonElement).disabled = false;
          return;
        }
        showToast(tr('lc_peers.requests.rejected', '拒否しました'));
        await loadRequests(callbacks);
      } catch {
        showToast(tr('lc_peers.requests.reject_error', '拒否に失敗しました'));
        (btn as HTMLButtonElement).disabled = false;
      }
      return;
    }
  });

  // Initial load
  loadRequests(callbacks);
}

/**
 * lan-cowork-page/peers-panel.ts
 * Fetches peer list, renders cards, fires lc:peers-updated CustomEvent.
 */
import {
  discoverPeers,
  clientPairRequest,
  clientPairVerify,
  removePeer,
  showToast,
  tr,
  Peer,
} from './api';
import { customConfirm, customPrompt } from '../shared/dialog';

// ── PIN modal ──────────────────────────────────────────────────────────────

function showPinModal(msg: string, sas?: string): Promise<string | null> {
  return new Promise((resolve) => {
    const overlay = document.getElementById('lcMainPinModal') as HTMLElement | null;
    const msgEl = document.getElementById('lcMainPinModalMsg');
    const sasBox = document.getElementById('lcMainPairSas') as HTMLElement | null;
    const sasCode = document.getElementById('lcMainPairSasCode');
    const input = document.getElementById('lcMainPinInput') as HTMLInputElement | null;
    const confirmBtn = document.getElementById('lcMainPinConfirmBtn');
    const cancelBtn = document.getElementById('lcMainPinCancelBtn');
    const errorEl = document.getElementById('lcMainPinError') as HTMLElement | null;
    if (!overlay || !input || !confirmBtn || !cancelBtn) {
      // Fallback if DOM elements missing
      customPrompt(msg).then((v) => resolve(v));
      return;
    }
    if (msgEl) msgEl.textContent = msg;
    if (sasBox && sasCode) {
      sasCode.textContent = sas ?? '';
      sasBox.hidden = !sas;
    }
    if (errorEl) { errorEl.hidden = true; errorEl.textContent = ''; }
    input.value = '';
    overlay.hidden = false;
    input.focus();

    function cleanup(result: string | null): void {
      overlay!.hidden = true;
      confirmBtn!.removeEventListener('click', onConfirm);
      cancelBtn!.removeEventListener('click', onCancel);
      overlay!.removeEventListener('click', onOverlay);
      document.removeEventListener('keydown', onKey);
      resolve(result);
    }

    function onConfirm(): void {
      const val = input!.value.trim();
      if (!val) {
        if (errorEl) { errorEl.textContent = tr('lan_cowork.pin_modal.error.empty', 'PIN を入力してください'); errorEl.hidden = false; }
        return;
      }
      cleanup(val);
    }
    function onCancel(): void { cleanup(null); }
    function onOverlay(e: Event): void { if (e.target === overlay) cleanup(null); }
    function onKey(e: KeyboardEvent): void {
      if (e.key === 'Escape') cleanup(null);
      if (e.key === 'Enter') onConfirm();
    }

    confirmBtn.addEventListener('click', onConfirm);
    cancelBtn.addEventListener('click', onCancel);
    overlay.addEventListener('click', onOverlay);
    document.addEventListener('keydown', onKey);
  });
}

function isPaired(peer: Peer): boolean {
  const exp = peer.token_expires_at;
  if (!exp) return false;
  return exp * 1000 > Date.now();
}

function renderPeerCard(peer: Peer): string {
  const statusLabel = peer.status === 'online'
    ? tr('lan_cowork.peers.online', 'Online')
    : tr('lan_cowork.peers.offline', 'Offline');
  const statusClass = peer.status === 'online' ? 'lc-badge-online' : 'lc-badge-offline';
  const paired = isPaired(peer);
  const pairBadge = paired
    ? `<span class="lc-badge lc-badge-online" data-i18n="lan_cowork.peers.paired">${tr('lan_cowork.peers.paired', 'ペアリング済')}</span>`
    : `<span class="lc-badge lc-badge-offline" data-i18n="lan_cowork.peers.unpaired">${tr('lan_cowork.peers.unpaired', '未ペアリング')}</span>`;
  const pairBtn = paired
    ? ''
    : `<button type="button" class="lc-btn lc-btn-sm" data-action="lc-pair-request" data-peer-id="${escapeHtml(peer.peer_id)}" data-i18n="lan_cowork.peers.pair_btn">${tr('lan_cowork.peers.pair_btn', 'ペアリング要求')}</button>`;
  const removeBtn = `<button type="button" class="lc-btn lc-btn-sm lc-btn-danger" data-action="lc-remove-peer" data-peer-id="${escapeHtml(peer.peer_id)}" data-peer-name="${escapeHtml(peer.name)}" data-i18n="lan_cowork.peers.remove_btn">${tr('lan_cowork.peers.remove_btn', '削除')}</button>`;
  return `
    <div class="lc-peer-card">
      <div class="lc-peer-name">${escapeHtml(peer.name)}</div>
      <div class="lc-peer-addr">${escapeHtml(peer.api_host)}:${escapeHtml(String(peer.api_port))}</div>
      <span class="lc-badge ${statusClass}">${statusLabel}</span>
      ${pairBadge}
      ${pairBtn}
      ${removeBtn}
    </div>`;
}

export function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!);
}

function dispatchPeersUpdated(peers: Peer[]): void {
  document.dispatchEvent(new CustomEvent('lc:peers-updated', { detail: peers }));
}

async function loadPeers(grid: HTMLElement, refreshBtn: HTMLButtonElement): Promise<void> {
  refreshBtn.disabled = true;
  try {
    const data = await discoverPeers();
    if (!data.ok || !data.peers) {
      const disabled = typeof data.error === 'string' && /not enabled/i.test(data.error);
      if (disabled) {
        const p = document.createElement('p');
        p.className = 'lc-empty';
        p.setAttribute('data-i18n', 'lan_cowork.peers.extension_disabled');
        p.textContent = tr(
          'lan_cowork.peers.extension_disabled',
          'LAN Cowork extension is disabled. Enable it from Extensions admin and restart the server.',
        );
        grid.replaceChildren(p);
      } else {
        showToast(tr('lan_cowork.peers.discover_error', 'Failed to discover peers'));
        const p = document.createElement('p');
        p.className = 'lc-empty';
        p.setAttribute('data-i18n', 'lan_cowork.peers.empty');
        p.textContent = tr('lan_cowork.peers.empty', 'No peers connected');
        grid.replaceChildren(p);
      }
      dispatchPeersUpdated([]);
      return;
    }
    if (data.peers.length === 0) {
      grid.innerHTML = `<p class="lc-empty" data-i18n="lan_cowork.peers.empty">${tr('lan_cowork.peers.empty', 'No peers connected')}</p>`;
    } else {
      grid.innerHTML = data.peers.map(renderPeerCard).join('');
    }
    dispatchPeersUpdated(data.peers);
  } catch {
    showToast(tr('lan_cowork.peers.discover_error', 'Failed to discover peers'));
    grid.innerHTML = `<p class="lc-empty" data-i18n="lan_cowork.peers.empty">${tr('lan_cowork.peers.empty', 'No peers connected')}</p>`;
    dispatchPeersUpdated([]);
  } finally {
    refreshBtn.disabled = false;
  }
}

async function handlePairRequest(
  peerId: string,
  btn: HTMLButtonElement,
  grid: HTMLElement,
  refreshBtn: HTMLButtonElement,
): Promise<void> {
  btn.disabled = true;
  const originalText = btn.textContent ?? '';
  btn.textContent = tr('lan_cowork.peers.pair_requesting', '要求中...');
  try {
    const resp = await clientPairRequest(peerId);
    if (!resp.ok || !resp.request_id || !resp.sas) {
      showToast(tr('lan_cowork.peers.pair_request_error', 'ペアリング要求失敗') + ': ' + (resp.error ?? ''));
      return;
    }
    showToast(tr('lan_cowork.peers.pair_request_sent', '認証コードを相手側で確認後、8桁の PIN を入力してください'));
    const pin = await showPinModal(
      tr('lan_cowork.peers.pair_pin_prompt', '認証コードを相手ノードの管理者に確認してもらってください。承認後、8桁の PIN を入力してください。'),
      resp.sas,
    );
    if (!pin) {
      return;
    }
    const verified = await clientPairVerify(peerId, resp.request_id, pin.trim());
    if (!verified.ok) {
      showToast(tr('lan_cowork.peers.pair_verify_error', 'PIN 検証失敗') + ': ' + (verified.error ?? ''));
      return;
    }
    showToast(tr('lan_cowork.peers.pair_success', 'ペアリング完了'));
    await loadPeers(grid, refreshBtn);
  } catch {
    showToast(tr('lan_cowork.peers.pair_request_error', 'ペアリング要求失敗'));
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

async function handleRemovePeer(
  peerId: string,
  peerName: string,
  btn: HTMLButtonElement,
  grid: HTMLElement,
  refreshBtn: HTMLButtonElement,
): Promise<void> {
  const msg = tr('lan_cowork.peers.remove_confirm', 'このピアを削除しますか？') + '\n' + peerName;
  if (!(await customConfirm(msg, { danger: true }))) return;
  btn.disabled = true;
  try {
    const resp = await removePeer(peerId);
    if (!resp.ok) {
      showToast(tr('lan_cowork.peers.remove_error', '削除に失敗しました') + ': ' + (resp.error ?? ''));
      return;
    }
    showToast(tr('lan_cowork.peers.remove_success', '削除しました'));
    await loadPeers(grid, refreshBtn);
  } catch {
    showToast(tr('lan_cowork.peers.remove_error', '削除に失敗しました'));
  } finally {
    btn.disabled = false;
  }
}

export function initPeersPanel(): void {
  const grid = document.getElementById('lcPeerGrid');
  const refreshBtn = document.getElementById('lcRefreshBtn') as HTMLButtonElement | null;
  if (!grid || !refreshBtn) return;

  refreshBtn.addEventListener('click', () => loadPeers(grid, refreshBtn));

  grid.addEventListener('click', (e) => {
    const el = e.target as Element;
    const pairTarget = el.closest('[data-action="lc-pair-request"]') as HTMLElement | null;
    if (pairTarget) {
      const peerId = pairTarget.dataset['peerId'];
      if (!peerId) return;
      void handlePairRequest(peerId, pairTarget as HTMLButtonElement, grid, refreshBtn);
      return;
    }
    const removeTarget = el.closest('[data-action="lc-remove-peer"]') as HTMLElement | null;
    if (removeTarget) {
      const peerId = removeTarget.dataset['peerId'];
      const peerName = removeTarget.dataset['peerName'] ?? peerId ?? '';
      if (!peerId) return;
      void handleRemovePeer(peerId, peerName, removeTarget as HTMLButtonElement, grid, refreshBtn);
    }
  });

  loadPeers(grid, refreshBtn);
}

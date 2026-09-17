/**
 * lan-cowork-peers-page/sse.ts
 * SSE listeners for the peer management page.
 *
 * Subscribed events:
 *   peer.pairing_request — a new pairing request arrived → refresh requests table
 *   peer.token_revoked   — a token was revoked remotely  → refresh tokens table
 *   peer.auth_lost       — a token became invalid        → mark peer, refresh tokens
 */

import { sseSubscribe } from '../sse';
import { loadRequests } from './requests-panel';
import { loadTokens, markAuthLost } from './tokens-panel';
import { showToast, tr } from './api';

export function initPeersPageSSE(): void {
  // New incoming pairing request
  sseSubscribe('peer.pairing_request', (data) => {
    const payload = data as { peer_id?: string };
    const peerId = payload?.peer_id ?? '';
    showToast(tr('lc_peers.sse.pairing_request', 'ペアリングリクエストを受信しました') + (peerId ? ` (${peerId})` : ''));
    loadRequests().catch(() => {/* best-effort */});
  });

  // Token was revoked (by this host or remotely)
  sseSubscribe('peer.token_revoked', (_data) => {
    loadTokens().catch(() => {/* best-effort */});
  });

  // Pairing completed (this host approved the request, the requester verified PIN)
  sseSubscribe('peer.paired', (data) => {
    const payload = data as { peer_id?: string };
    const peerId = payload?.peer_id ?? '';
    showToast(tr('lc_peers.sse.paired', 'ペアリングが完了しました') + (peerId ? ` (${peerId})` : ''));
    loadRequests().catch(() => {/* best-effort */});
    loadTokens().catch(() => {/* best-effort */});
  });

  // Token became invalid (e.g., expired or revoked on remote) — show badge
  sseSubscribe('peer.auth_lost', (data) => {
    const payload = data as { peer_id?: string };
    if (payload?.peer_id) {
      markAuthLost(payload.peer_id);
    }
    loadTokens().catch(() => {/* best-effort */});
  });
}

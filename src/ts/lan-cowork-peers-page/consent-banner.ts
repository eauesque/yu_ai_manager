/**
 * Fleet update consent banner — shown when a chief sends an update consent request.
 *
 * Listens for 'fleet.consent_request' SSE events, displays a sticky banner
 * with approve-once / approve-permanent / deny buttons, and sends the decision
 * back via POST /ext/lan_cowork/fleet/consent/respond.
 */

import { sseSubscribe } from '../sse';
import { tr } from './api';

const BASE = '/ext/lan_cowork';

interface ConsentPayload {
  request_id: string;
  chief_peer_id: string;
  remaining_sec: number;
}

let _currentRequestId: string | null = null;
let _countdownTimer: ReturnType<typeof setInterval> | null = null;

function getBanner(): HTMLElement | null {
  return document.getElementById('fleetConsentBanner');
}

function showBanner(payload: ConsentPayload): void {
  const banner = getBanner();
  if (!banner) return;

  _currentRequestId = payload.request_id;

  const msgEl = document.getElementById('fleetConsentBannerMsg');
  if (msgEl) {
    const tpl = tr(
      'fleet.consent.banner.title',
      `{peer} からリモート更新リクエストが届きました`
    );
    msgEl.textContent = tpl.replace('{peer}', payload.chief_peer_id);
  }

  startCountdown(payload.remaining_sec);
  banner.hidden = false;

  // Web Notification (best-effort)
  if (Notification.permission === 'granted') {
    try {
      const title = tr(
        'fleet.consent.banner.title',
        `{peer} からリモート更新リクエスト`
      ).replace('{peer}', payload.chief_peer_id);
      new Notification(title, {
        body: tr('fleet.consent.banner.approve_once', '今回だけ承認') +
              ' / ' +
              tr('fleet.consent.banner.deny', '拒否'),
        tag: 'fleet-consent',
      });
    } catch (_) {/* ignore */}
  }
}

function startCountdown(remainingSec: number): void {
  if (_countdownTimer) clearInterval(_countdownTimer);
  let remaining = remainingSec;
  const el = document.getElementById('fleetConsentBannerCountdown');

  const update = (): void => {
    if (!el) return;
    const tpl = tr('fleet.consent.banner.countdown', `残り {sec} 秒`);
    el.textContent = tpl.replace('{sec}', String(remaining));
    if (remaining <= 0) {
      stopCountdown();
      hideBanner();
    }
    remaining--;
  };
  update();
  _countdownTimer = setInterval(update, 1000);
}

function stopCountdown(): void {
  if (_countdownTimer) {
    clearInterval(_countdownTimer);
    _countdownTimer = null;
  }
}

function hideBanner(): void {
  const banner = getBanner();
  if (banner) banner.hidden = true;
  _currentRequestId = null;
  stopCountdown();
}

async function respond(decision: 'approved' | 'denied', permanent: boolean): Promise<void> {
  if (!_currentRequestId) return;
  const requestId = _currentRequestId;
  hideBanner();

  try {
    await fetch(`${BASE}/fleet/consent/respond`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      body: JSON.stringify({ request_id: requestId, decision, permanent }),
    });
  } catch (_) {/* best-effort */}
}

async function checkPending(): Promise<void> {
  try {
    const resp = await fetch(`${BASE}/fleet/consent/pending`, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (!resp.ok) return;
    const data = await resp.json() as { pending: ConsentPayload | null };
    if (data.pending) {
      showBanner(data.pending);
    }
  } catch (_) {/* best-effort */}
}

export function initConsentBanner(): void {
  const banner = getBanner();
  if (!banner) return;

  // Button handlers (data-action delegation not used here as buttons are dynamic)
  document.getElementById('fleetConsentApproveOnce')
    ?.addEventListener('click', () => respond('approved', false));
  document.getElementById('fleetConsentApprovePermanent')
    ?.addEventListener('click', () => respond('approved', true));
  document.getElementById('fleetConsentDeny')
    ?.addEventListener('click', () => respond('denied', false));

  // Notification enable button
  document.getElementById('lcFleetEnableNotifications')
    ?.addEventListener('click', async () => {
      if (Notification.permission !== 'denied') {
        await Notification.requestPermission();
      }
    });

  // SSE subscription for incoming consent requests
  sseSubscribe('fleet.consent_request', (data) => {
    const payload = data as ConsentPayload;
    if (payload?.request_id) {
      showBanner(payload);
    }
  });

  // Page load: check for a pending request (e.g., arrived while page was closed)
  checkPending().catch(() => {/* best-effort */});
}

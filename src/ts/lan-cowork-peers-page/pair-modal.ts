/**
 * lan-cowork-peers-page/pair-modal.ts
 * Manages the pairing modal overlay (step1/step2/step3) and PIN verification flow.
 *
 * Static data-action values handled here (wired via document-level delegation):
 *   lc-peers-pair-cancel  — cancel / close the modal
 *   lc-peers-pin-confirm  — submit PIN (also handles form submit)
 *   lc-peers-pair-done    — close modal on success
 */

import { verifyPin, clientPairVerify, getFleetAllowlists, saveFleetAllowlists, showToast, tr, type ApiResponse } from './api';

type ModalState = {
  requestId: string;
  pin: string; // PIN received from server after approve (shown to admin or passed to verify)
  sas?: string;
  peerId?: string; // set for client-initiated (proxy) flow
  approveePeerId?: string; // set in approve flow: the peer we just approved
};

let _state: ModalState | null = null;

export function decideFailureDisplay(resp: ApiResponse): {
  messageKey: string;
  fallback: string;
  params?: Record<string, string | number>;
  showRepairSteps: boolean;
} {
  if (resp.state === 'unknown') {
    return {
      messageKey: 'lc_peers.pair_modal.error.unknown',
      fallback: resp.error ?? '相手側の状態を確認できません。',
      showRepairSteps: true,
    };
  }
  if (resp.state === 'retryable') {
    return {
      messageKey: 'lc_peers.pair_modal.pin.error.retryable',
      fallback: 'PIN が正しくありません。残り {attempts} 回試せます。',
      params: { attempts: resp.attempts_remaining ?? 0 },
      showRepairSteps: false,
    };
  }
  if (resp.state === 'failed' && resp.code === 'pin_attempts_exhausted') {
    return {
      messageKey: 'lc_peers.pair_modal.pin.error.attempts_exhausted',
      fallback: 'PIN の試行回数が上限に達しました。',
      showRepairSteps: true,
    };
  }
  return {
    messageKey: resp.error === 'invalid pin'
      ? 'lc_peers.pair_modal.pin.error.invalid'
      : 'lc_peers.pair_modal.error.generic',
    fallback: resp.error ?? 'エラーが発生しました',
    showRepairSteps: resp.state === 'failed' && resp.code === 'fingerprint_mismatch',
  };
}

function getEl(id: string): HTMLElement | null {
  return document.getElementById(id);
}

function showStep(stepNum: 1 | 2 | 3): void {
  const steps = [1, 2, 3] as const;
  for (const n of steps) {
    const el = getEl(`lcPeersPairStep${n}`);
    if (el) el.classList.toggle('active', n === stepNum);
  }
}

function showModal(): void {
  const overlay = getEl('lcPeersPairModal');
  if (overlay) overlay.classList.add('active');
}

async function saveFleetPermsIfRequested(peerId: string): Promise<void> {
  const cbRestart = getEl('lcPeersPairGrantRestart') as HTMLInputElement | null;
  const cbLog = getEl('lcPeersPairGrantLog') as HTMLInputElement | null;
  const doRestart = cbRestart?.checked ?? false;
  const doLog = cbLog?.checked ?? false;
  if (!doRestart && !doLog) return;
  try {
    const current = await getFleetAllowlists();
    const restartSet = new Set([...(current.allow_restart_from ?? [])]);
    const logSet = new Set([...(current.allow_log_stream_from ?? [])]);
    if (doRestart) restartSet.add(peerId);
    if (doLog) logSet.add(peerId);
    await saveFleetAllowlists({
      allow_remote_update: true,
      allow_restart_from: [...restartSet],
      allow_log_stream_from: [...logSet],
      allow_update_from: current.allow_update_from ?? [],
    });
    showToast(tr('lc_peers.pair_modal.fleet_perms.saved', 'Fleet 許可を保存しました'));
  } catch {
    showToast(tr('lc_peers.pair_modal.fleet_perms.save_failed', 'Fleet 許可の保存に失敗しました'));
  }
}

function resetFleetPermsUI(): void {
  const section = getEl('lcPeersPairFleetPerms');
  if (section) section.hidden = true;
  const cbRestart = getEl('lcPeersPairGrantRestart') as HTMLInputElement | null;
  const cbLog = getEl('lcPeersPairGrantLog') as HTMLInputElement | null;
  if (cbRestart) cbRestart.checked = true;
  if (cbLog) cbLog.checked = true;
}

function hideModal(): void {
  const overlay = getEl('lcPeersPairModal');
  if (overlay) overlay.classList.remove('active');
  _state = null;
  clearPinInput();
  clearPinError();
  clearModalError();
  resetFleetPermsUI();
}

function clearPinInput(): void {
  const input = getEl('lcPeersPinInput') as HTMLInputElement | null;
  if (input) input.value = '';
}

function showPinError(msg: string): void {
  const el = getEl('lcPeersPinError');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('active');
}

function clearPinError(): void {
  const el = getEl('lcPeersPinError');
  if (!el) return;
  el.classList.remove('active');
}

function showModalError(msg: string): void {
  const el = getEl('lcPeersPairError');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('active');
}

function clearModalError(): void {
  const el = getEl('lcPeersPairError');
  if (!el) return;
  el.classList.remove('active');
}

function setSasDisplay(sas: string | null): void {
  const wrap = getEl('lcPeersPairSas');
  const code = getEl('lcPeersPairSasCode');
  if (!wrap || !code) return;
  if (!sas) {
    wrap.hidden = true;
    code.textContent = '';
    return;
  }
  code.textContent = sas;
  wrap.hidden = false;
}

async function submitPin(): Promise<void> {
  if (!_state) return;

  const input = getEl('lcPeersPinInput') as HTMLInputElement | null;
  const pin = input?.value.trim() ?? '';
  if (!pin) {
    showPinError(tr('lc_peers.pair_modal.pin.error.empty', 'PIN を入力してください'));
    return;
  }

  clearPinError();
  clearModalError();

  let resp;
  try {
    if (_state.peerId) {
      // Client-initiated flow: use local proxy endpoint
      resp = await clientPairVerify(_state.peerId, _state.requestId, pin);
    } else {
      // Server-side approve flow: verify directly against own pairing service
      resp = await verifyPin(_state.requestId, pin);
    }
  } catch {
    showModalError(tr('lc_peers.pair_modal.error.generic', 'エラーが発生しました'));
    return;
  }

  if (!resp.ok) {
    const display = decideFailureDisplay(resp);
    let errMsg = tr(display.messageKey, display.fallback);
    if (display.params) {
      for (const [key, value] of Object.entries(display.params)) {
        errMsg = errMsg.replace(`{${key}}`, String(value));
      }
    }
    if (display.showRepairSteps) {
      errMsg += ` ${tr('lc_peers.pair_modal.repair_steps', '再ペアリングするには、相手ノードの管理者に新しいリクエストを承認してもらってください。')}`;
    }
    showPinError(errMsg);
    return;
  }

  // PIN verified — toast immediately so the user gets reassurance
  // even before clicking "Done", and on the approver side too.
  showToast(tr('lc_peers.pair_modal.paired_toast', 'ペアリングが完了しました'));
  showStep(3);
}

/**
 * Open the modal for the "approving side" — show the PIN that was
 * generated by approve(), so the admin can communicate it to the requester.
 * The verify step is for the requesting side (handled by Task 16's proxy).
 * Here we show step 2 (PIN entry) pre-filled with the server-generated PIN.
 */
export function openApproveFlow(requestId: string, serverPin: string, approveePeerId: string): void {
  _state = { requestId, pin: serverPin, approveePeerId };
  clearPinError();
  clearModalError();
  setSasDisplay(null);

  const input = getEl('lcPeersPinInput') as HTMLInputElement | null;
  if (input) {
    input.type = 'text';
    input.readOnly = true;
    input.value = serverPin;
    input.inputMode = 'numeric';
    input.maxLength = 8;
    input.pattern = '\\d{8}';
  }

  const msg = getEl('lcPeersPairStep2Msg');
  if (msg) msg.textContent = tr('lc_peers.pair_modal.step2.approve_msg', '以下の PIN をリクエスト元のホストに伝えてください。');

  // Show fleet permission section with this peer's id
  const fleetSection = getEl('lcPeersPairFleetPerms');
  if (fleetSection) fleetSection.hidden = false;

  // Approver only needs to close — hide confirm, repurpose cancel as "閉じる"
  const confirmBtn = getEl('lcPeersPinConfirm') as HTMLButtonElement | null;
  if (confirmBtn) confirmBtn.hidden = true;
  const cancelBtn = getEl('lcPeersPinCancel');
  if (cancelBtn) {
    cancelBtn.textContent = tr('lc_peers.pair_modal.close_with_perms', '閉じる（許可を保存）');
    cancelBtn.dataset['action'] = 'lc-peers-approve-close';
  }

  showModal();
  showStep(2);
}

/**
 * Open the modal for the "requesting side" — user enters the PIN that was
 * shown by the remote admin.  The PIN is submitted via the local proxy
 * (/api/client/pair/verify) which stores the resulting token.
 */
export function openClientPairFlow(peerId: string, requestId: string, sas: string): void {
  _state = { requestId, pin: '', sas, peerId };
  clearPinError();
  clearModalError();
  setSasDisplay(sas);

  const input = getEl('lcPeersPinInput') as HTMLInputElement | null;
  if (input) {
    input.type = 'password';
    input.readOnly = false;
    input.value = '';
    input.inputMode = 'numeric';
    input.maxLength = 8;
    input.pattern = '\\d{8}';
  }

  const msg = getEl('lcPeersPairStep2Msg');
  if (msg) msg.textContent = 'このコードを相手ノードの管理者に確認してもらってください。承認後、8桁の PIN を入力してください。';

  // Restore confirm/cancel for the entry flow
  const confirmBtn = getEl('lcPeersPinConfirm') as HTMLButtonElement | null;
  if (confirmBtn) confirmBtn.hidden = false;
  const cancelBtn = getEl('lcPeersPinCancel');
  if (cancelBtn) {
    cancelBtn.textContent = tr('lc_peers.pair_modal.cancel', 'キャンセル');
    cancelBtn.dataset['action'] = 'lc-peers-pair-cancel';
  }

  showModal();
  showStep(2);
}

export function initPairModal(): void {
  const overlay = getEl('lcPeersPairModal');
  if (!overlay) return;

  // Form submit handler (Enter key on PIN input)
  const form = getEl('lcPeersPinForm') as HTMLFormElement | null;
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      await submitPin();
    });
  }

  // Click delegation for modal action buttons
  overlay.addEventListener('click', async (e) => {
    const btn = (e.target as Element).closest('[data-action]');
    if (!btn) return;
    const action = (btn as HTMLElement).dataset['action'];

    if (action === 'lc-peers-approve-close') {
      const peerId = _state?.approveePeerId ?? '';
      if (peerId) await saveFleetPermsIfRequested(peerId);
      hideModal();
      return;
    }

    if (action === 'lc-peers-pair-cancel') {
      hideModal();
      return;
    }

    if (action === 'lc-peers-pin-confirm') {
      // Only handle if not a submit button (form submit handles that)
      const btnType = (btn as HTMLButtonElement).type;
      if (btnType !== 'submit') {
        e.preventDefault();
        await submitPin();
      }
      return;
    }

    if (action === 'lc-peers-pair-done') {
      hideModal();
      showToast(tr('lc_peers.pair_modal.paired_toast', 'ペアリングが完了しました'));
      return;
    }
  });

  // NOTE: We deliberately do NOT close on overlay background click —
  // pairing flows include PIN entry / Fleet permission grant, and an
  // accidental click should not lose the user's progress. Use the
  // Cancel/Close button (or Esc) to dismiss.

  // Close on Escape key only when on a step where it's safe to abort.
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const isActive = overlay.classList.contains('active');
    if (!isActive) return;
    // On step 3 (success) Esc is fine; on step 1/2 require explicit
    // button press to avoid accidental cancellation mid-PIN-entry.
    const step3 = getEl('lcPeersPairStep3');
    if (step3 && step3.classList.contains('active')) hideModal();
  });
}

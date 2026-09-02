/* Fleet admin UI polling and stream helpers */
(function () {
  "use strict";

  const ns = window.__fleetAdmin = window.__fleetAdmin || {};
  const state = ns.state = ns.state || {};
  state.overview = state.overview || { pollTimer: null };
  state.logs = state.logs || { abortCtrl: null, selectedPeer: null, paused: false, lines: [] };
  state.consent = state.consent || { peerId: null, requestId: null, pollTimer: null, countdownTimer: null };
  state.update = state.update || { pollTimer: null };

  const POLL_INTERVAL_MS = 30000;

  ns.startOverviewPolling = function startOverviewPolling(renderOverview) {
    if (state.overview.pollTimer) clearInterval(state.overview.pollTimer);
    state.overview.pollTimer = setInterval(() => renderOverview(false), POLL_INTERVAL_MS);
  };

  ns.stopLogStream = function stopLogStream() {
    if (state.logs.abortCtrl) {
      state.logs.abortCtrl.abort();
      state.logs.abortCtrl = null;
    }
  };

  ns.connectLogStream = function connectLogStream(peerId) {
    ns.stopLogStream();
    state.logs.lines = [];
    const output = document.getElementById("fleet-logs-output");
    if (output) output.replaceChildren();

    const level = document.getElementById("fleet-logs-level")?.value || "";
    let url = `/ext/lan_cowork/fleet/logs/stream?peer_id=${encodeURIComponent(peerId)}&lines=200`;
    if (level) url += `&level=${encodeURIComponent(level)}`;

    const ctrl = new AbortController();
    state.logs.abortCtrl = ctrl;

    (async () => {
      try {
        const resp = await fetch(url, { signal: ctrl.signal });
        if (!resp.ok || !resp.body) return;
        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        let evtType = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() ?? "";
          for (const line of lines) {
            if (line.startsWith("event:")) {
              evtType = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              const raw = line.slice(5).trim();
              if (evtType === "log") {
                try { ns.appendLogLine(JSON.parse(raw)); } catch (_) {}
              } else if (evtType === "close") {
                ctrl.abort();
                return;
              }
              evtType = "";
            } else if (line === "") {
              evtType = "";
            }
          }
        }
      } catch (_) {}
    })();
  };

  ns.stopConsentPoll = function stopConsentPoll() {
    if (state.consent.pollTimer) {
      clearInterval(state.consent.pollTimer);
      state.consent.pollTimer = null;
    }
  };

  ns.stopConsentCountdown = function stopConsentCountdown() {
    if (state.consent.countdownTimer) {
      clearInterval(state.consent.countdownTimer);
      state.consent.countdownTimer = null;
    }
  };

  ns.startConsentCountdown = function startConsentCountdown(remainingSec) {
    let remaining = remainingSec;
    const waitingMsg = document.getElementById("fleet-consent-waiting-msg");
    const update = () => {
      if (!waitingMsg) return;
      waitingMsg.textContent = (
        window.tr?.("fleet.consent.chief.waiting", "Waiting for consent ⏱ ({sec}s remaining)")
        || "Waiting for consent ⏱ ({sec}s remaining)"
      ).replace("{sec}", remaining);
      if (remaining <= 0) ns.stopConsentCountdown();
      remaining--;
    };
    update();
    state.consent.countdownTimer = setInterval(update, 1000);
  };

  ns.startConsentPoll = function startConsentPoll() {
    ns.stopConsentPoll();
    const poll = async () => {
      if (!state.consent.requestId || !state.consent.peerId) return;
      try {
        const { resp, data } = await ns.fetchConsentStatus(state.consent.peerId, state.consent.requestId);
        if (!resp.ok) return;
        if (data.status === "approved") {
          ns.stopConsentPoll();
          ns.stopConsentCountdown();
          await ns.retriggerUpdateWithToken(state.consent.peerId, state.consent.requestId, data.permanent);
        } else if (data.status === "denied") {
          ns.stopConsentPoll();
          ns.stopConsentCountdown();
          ns.showConsentError("fleet.error.consent_denied", "Consent was denied.");
        } else if (data.status === "expired" || data.status === "not_found") {
          ns.stopConsentPoll();
          ns.stopConsentCountdown();
          ns.showConsentError("fleet.consent.chief.timeout", "Consent timed out. Re-request?");
        }
      } catch (_) {}
    };
    state.consent.pollTimer = setInterval(poll, 3000);
  };

  ns.startDispatchPoll = function startDispatchPoll(dispatchId) {
    if (state.update.pollTimer) clearInterval(state.update.pollTimer);
    const poll = async () => {
      try {
        const { resp, data } = await ns.fetchDispatchStatus(dispatchId);
        if (!resp.ok) return;
        const statusEl = document.getElementById("fleet-update-dispatch-status");
        if (statusEl) statusEl.textContent = "dispatch: " + data.status;
        (data.peers || []).forEach(peerStatus => {
          ns.updateProgressCell(peerStatus.peer_id, peerStatus);
        });
        if (["success", "failed"].includes(data.status)) {
          clearInterval(state.update.pollTimer);
          state.update.pollTimer = null;
        }
      } catch (_) {}
    };
    state.update.pollTimer = setInterval(poll, 5000);
    poll();
  };
})();

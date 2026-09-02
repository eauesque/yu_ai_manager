/* Fleet admin UI actions */
(function () {
  "use strict";

  const ns = window.__fleetAdmin = window.__fleetAdmin || {};
  const state = ns.state = ns.state || {};
  state.logs = state.logs || { selectedPeer: null };
  state.consent = state.consent || { peerId: null, requestId: null, pollTimer: null, countdownTimer: null };

  ns.showConsentPanel = function showConsentPanel(peerId, msg) {
    const panel = document.getElementById("fleet-consent-panel");
    if (!panel) return;
    const msgEl = document.getElementById("fleet-consent-panel-msg");
    const sendBtn = document.getElementById("fleet-consent-send-btn");
    const cancelBtn = document.getElementById("fleet-consent-cancel-btn");
    const retryBtn = document.getElementById("fleet-consent-retry-btn");
    const waitingMsg = document.getElementById("fleet-consent-waiting-msg");

    state.consent.peerId = peerId;
    if (msgEl) msgEl.textContent = msg;
    if (sendBtn) sendBtn.style.display = "";
    if (cancelBtn) cancelBtn.style.display = "none";
    if (retryBtn) retryBtn.style.display = "none";
    if (waitingMsg) waitingMsg.style.display = "none";
    panel.style.display = "";
  };

  ns.hideConsentPanel = function hideConsentPanel() {
    const panel = document.getElementById("fleet-consent-panel");
    if (panel) panel.style.display = "none";
    ns.stopConsentPoll();
    ns.stopConsentCountdown();
    state.consent = { peerId: null, requestId: null, pollTimer: null, countdownTimer: null };
  };

  ns.showConsentError = function showConsentError(i18nKey, fallback) {
    const waitingMsg = document.getElementById("fleet-consent-waiting-msg");
    const retryBtn = document.getElementById("fleet-consent-retry-btn");
    const cancelBtn = document.getElementById("fleet-consent-cancel-btn");
    if (waitingMsg) waitingMsg.textContent = window.tr?.(i18nKey, fallback) || fallback;
    if (retryBtn) retryBtn.style.display = "";
    if (cancelBtn) cancelBtn.style.display = "none";
  };

  ns.sendConsentRequest = async function sendConsentRequest() {
    if (!state.consent.peerId) return;
    const requestId = "cr_" + Math.random().toString(36).slice(2, 10);
    state.consent.requestId = requestId;

    const sendBtn = document.getElementById("fleet-consent-send-btn");
    const cancelBtn = document.getElementById("fleet-consent-cancel-btn");
    const waitingMsg = document.getElementById("fleet-consent-waiting-msg");
    if (sendBtn) sendBtn.style.display = "none";
    if (cancelBtn) cancelBtn.style.display = "";
    if (waitingMsg) waitingMsg.style.display = "";

    try {
      const { resp, data } = await ns.requestConsentRelay(state.consent.peerId, requestId);
      if (resp.status === 409) {
        if (sendBtn) sendBtn.style.display = "";
        if (cancelBtn) cancelBtn.style.display = "none";
        ns.showConsentError("fleet.error.other_chief_pending", ("Another chief is awaiting consent ({sec}s remaining)").replace("{sec}", data.remaining_sec || "?"));
        return;
      }
      if (resp.status === 429) {
        if (sendBtn) sendBtn.style.display = "";
        if (cancelBtn) cancelBtn.style.display = "none";
        ns.showConsentError("fleet.error.deny_cooldown", ("Deny cooldown active ({sec}s remaining)").replace("{sec}", data.retry_after_sec || "?"));
        return;
      }
      if (!resp.ok) {
        if (waitingMsg) waitingMsg.textContent = "Error: " + (data.error || JSON.stringify(data));
        return;
      }
    } catch (e) {
      if (waitingMsg) waitingMsg.textContent = "Error: " + e.message;
      return;
    }

    ns.startConsentCountdown(300);
    ns.startConsentPoll();
  };

  ns.retriggerUpdateWithToken = async function retriggerUpdateWithToken(peerId, requestId, permanent) {
    if (permanent) ns.hideConsentPanel();
    const source = document.getElementById("fleet-update-source")?.value || "origin";
    const branch = document.getElementById("fleet-update-branch")?.value || "main";
    const consentTokens = permanent ? {} : { [peerId]: requestId };
    try {
      const { data } = await ns.dispatchUpdate([peerId], source, branch, consentTokens);
      if (data.dispatch_id) {
        ns.hideConsentPanel();
        ns.startDispatchPoll(data.dispatch_id);
        const progress = document.getElementById("fleet-update-progress");
        if (progress) progress.style.display = "";
      } else if (data.error === "consent_token_invalid") {
        ns.showConsentError("fleet.error.consent_token_invalid", "Consent invalidated. Please re-request.");
      } else {
        ns.showConsentError("fleet.error.update_failed_token_consumed", "Update failed — consent consumed. Re-request?");
      }
    } catch (_) {
      ns.showConsentError("fleet.error.update_failed_token_consumed", "Update failed — consent consumed. Re-request?");
    }
  };

  ns.singlePullRestart = async function singlePullRestart(peerId) {
    const confirmMsg = window.tr?.("fleet.update.confirm.update", "Update the selected nodes? They will git pull and restart. Continue?")
      || "Update the selected nodes? They will git pull and restart. Continue?";
    if (!(await window.customConfirm(confirmMsg))) return;
    const source = document.getElementById("fleet-update-source")?.value || "origin";
    const branch = document.getElementById("fleet-update-branch")?.value || "main";
    try {
      const { data } = await ns.dispatchUpdate([peerId], source, branch);
      if (data.dispatch_id) {
        ns.startDispatchPoll(data.dispatch_id);
        const progress = document.getElementById("fleet-update-progress");
        if (progress) progress.style.display = "";
      } else {
        window.customAlert("Error: " + (data.message || JSON.stringify(data)));
      }
    } catch (e) {
      window.customAlert("Error: " + e.message);
    }
  };

  ns.singleRestart = async function singleRestart(peerId) {
    await ns.dispatchRestartFlow([peerId]);
  };

  ns.dispatchRestartSelected = async function dispatchRestartSelected() {
    const peerIds = Array.from(document.querySelectorAll("#fleet-update-tbody input[type=checkbox]:checked"))
      .map(cb => cb.value);
    if (peerIds.length === 0) {
      window.customAlert(window.tr?.("fleet.update.no_selection", "Please select at least one node") || "Please select at least one node");
      return;
    }
    await ns.dispatchRestartFlow(peerIds);
  };

  ns.dispatchRestartFlow = async function dispatchRestartFlow(peerIds) {
    const confirmMsg = window.tr?.("fleet.update.confirm.restart", "Restart the selected nodes?")
      || "Restart the selected nodes?";
    if (!(await window.customConfirm(confirmMsg))) return;
    try {
      const { data } = await ns.dispatchRestart(peerIds);
      if (data.dispatch_id) {
        ns.startDispatchPoll(data.dispatch_id);
        const progress = document.getElementById("fleet-update-progress");
        if (progress) progress.style.display = "";
      } else {
        window.customAlert("Error: " + (data.message || JSON.stringify(data)));
      }
    } catch (e) {
      window.customAlert("Error: " + e.message);
    }
  };

  ns.dispatchSelected = async function dispatchSelected() {
    const peerIds = Array.from(document.querySelectorAll("#fleet-update-tbody input[type=checkbox]:checked"))
      .map(cb => cb.value);
    if (peerIds.length === 0) {
      window.customAlert(window.tr?.("fleet.update.no_selection", "Please select at least one node") || "Please select at least one node");
      return;
    }
    const confirmMsg = window.tr?.("fleet.update.confirm.update", "Update the selected nodes? They will git pull and restart. Continue?")
      || "Update the selected nodes? They will git pull and restart. Continue?";
    if (!(await window.customConfirm(confirmMsg))) return;
    const source = document.getElementById("fleet-update-source")?.value || "origin";
    const branch = document.getElementById("fleet-update-branch")?.value || "main";
    try {
      const { data } = await ns.dispatchUpdate(peerIds, source, branch);
      if (data.dispatch_id) {
        ns.startDispatchPoll(data.dispatch_id);
        const progress = document.getElementById("fleet-update-progress");
        if (progress) progress.style.display = "";
      } else {
        window.customAlert("Error: " + (data.message || JSON.stringify(data)));
      }
    } catch (e) {
      window.customAlert("Error: " + e.message);
    }
  };

  ns.copyLogsToClipboard = function copyLogsToClipboard() {
    const output = document.getElementById("fleet-logs-output");
    if (!output) return;
    const text = Array.from(output.children).map(el => el.textContent || "").join("\n");
    const setStatus = msg => {
      const status = document.getElementById("fleet-logs-status");
      if (!status) return;
      status.textContent = msg;
      setTimeout(() => { if (status.textContent === msg) status.textContent = ""; }, 1500);
    };
    const okMsg = window.tr?.("fleet.logs.copied", "Copied!") || "Copied!";
    const failMsg = window.tr?.("fleet.logs.copy_failed", "Copy failed") || "Copy failed";
    const legacyCopy = value => {
      try {
        const ta = document.createElement("textarea");
        ta.value = value;
        ta.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0;";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        return !!ok;
      } catch (_) {
        return false;
      }
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(() => setStatus(okMsg)).catch(() => {
        setStatus(legacyCopy(text) ? okMsg : failMsg);
      });
    } else {
      setStatus(legacyCopy(text) ? okMsg : failMsg);
    }
  };

  ns.downloadLogs = function downloadLogs() {
    const output = document.getElementById("fleet-logs-output");
    if (!output) return;
    const text = Array.from(output.children).map(el => el.textContent || "").join("\n");
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const peer = state.logs.selectedPeer || "fleet";
    const blob = new Blob([text], { type: "text/plain; charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `fleet-log-${peer}-${ts}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
})();

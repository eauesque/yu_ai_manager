/* Fleet admin UI settings-tab wiring */
(function () {
  "use strict";

  const ns = window.__fleetAdmin = window.__fleetAdmin || {};
  const state = ns.state = ns.state || {};
  state.settings = state.settings || {
    inited: false,
    peers: [],
    current: { allow_log_stream_from: [], allow_update_from: [], allow_remote_update: false },
    remoteStatus: {},
  };

  async function loadAllowlists() {
    try {
      const { resp, data } = await ns.fetchAllowlists();
      if (!resp.ok || !data || !data.ok) return;
      state.settings.current = {
        allow_log_stream_from: data.allow_log_stream_from || [],
        allow_update_from: data.allow_update_from || [],
        allow_remote_update: !!data.allow_remote_update,
      };
    } catch (_) {}
  }

  async function loadRemoteStatuses() {
    const timings = window._fleetTimings || {};
    await Promise.all(state.settings.peers.map(async peer => {
      if (ns.peerStatusLabel && ns.peerStatusLabel(peer, timings) === "offline") {
        state.settings.remoteStatus[peer.peer_id] = { offline: true };
        return;
      }
      try {
        const { resp, data } = await ns.fetchPeerAllowlistStatus(peer.peer_id);
        if (resp.ok && data.ok) {
          state.settings.remoteStatus[peer.peer_id] = { log_stream: !!data.log_stream, update: !!data.update };
        } else {
          state.settings.remoteStatus[peer.peer_id] = { error: data.error || ("HTTP " + resp.status) };
        }
      } catch (e) {
        state.settings.remoteStatus[peer.peer_id] = { error: e.message };
      }
    }));
  }

  ns.renderSettingsLocalTable = function renderSettingsLocalTable() {
    const tbody = document.getElementById("fleet-settings-local-tbody");
    if (!tbody) return;
    tbody.replaceChildren();

    const noticeTr = document.createElement("tr");
    const noticeTd = document.createElement("td");
    noticeTd.colSpan = 3;
    const noticeLink = document.createElement("a");
    noticeLink.href = "/lan-cowork/peers";
    noticeLink.dataset.i18n = "fleet_admin.allowlist.readonly_notice";
    noticeLink.textContent = window.tr?.(
      "fleet_admin.allowlist.readonly_notice",
      "Edit permissions from LAN Cowork → Fleet Permissions section",
    ) || "Edit permissions from LAN Cowork → Fleet Permissions section";
    noticeTd.appendChild(noticeLink);
    noticeTr.appendChild(noticeTd);
    tbody.appendChild(noticeTr);

    const logSet = new Set(state.settings.current.allow_log_stream_from);
    const updSet = new Set(state.settings.current.allow_update_from);
    state.settings.peers.forEach(peer => {
      const tr = document.createElement("tr");
      const tdName = document.createElement("td");
      tdName.textContent = (peer.name || peer.peer_id) + " (" + ns.escHtmlLog(peer.peer_id) + ")";
      tr.appendChild(tdName);

      const tdLog = document.createElement("td");
      const cbLog = document.createElement("input");
      cbLog.type = "checkbox";
      cbLog.dataset.peerId = peer.peer_id;
      cbLog.dataset.kind = "log_stream";
      cbLog.checked = logSet.has(peer.peer_id);
      cbLog.disabled = true;
      tdLog.appendChild(cbLog);
      tr.appendChild(tdLog);

      const tdUpd = document.createElement("td");
      const cbUpd = document.createElement("input");
      cbUpd.type = "checkbox";
      cbUpd.dataset.peerId = peer.peer_id;
      cbUpd.dataset.kind = "update";
      cbUpd.checked = updSet.has(peer.peer_id);
      cbUpd.disabled = true;
      tdUpd.appendChild(cbUpd);
      tr.appendChild(tdUpd);
      tbody.appendChild(tr);
    });
    const cbRemote = document.getElementById("fleet-settings-allow-remote-update");
    if (cbRemote) {
      cbRemote.checked = !!state.settings.current.allow_remote_update;
      cbRemote.disabled = true;
    }
    const saveBtn = document.getElementById("fleet-settings-local-save");
    if (saveBtn) saveBtn.disabled = true;
  };

  ns.renderSettingsRemoteTable = function renderSettingsRemoteTable() {
    const tbody = document.getElementById("fleet-settings-remote-tbody");
    if (!tbody) return;
    tbody.replaceChildren();
    state.settings.peers.forEach(peer => {
      const tr = document.createElement("tr");
      const tdName = document.createElement("td");
      tdName.textContent = (peer.name || peer.peer_id) + " (" + ns.escHtmlLog(peer.peer_id) + ")";
      tr.appendChild(tdName);

      const tdStatus = document.createElement("td");
      const st = state.settings.remoteStatus[peer.peer_id];
      if (st === undefined) {
        tdStatus.textContent = "…";
      } else if (st && st.offline) {
        tdStatus.textContent = window.tr?.("fleet.node.status.offline", "Offline") || "Offline";
      } else if (st && st.error) {
        tdStatus.textContent = (window.tr?.("fleet.settings.remote.status_unreachable", "Unreachable") || "Unreachable") + ": " + st.error;
      } else if (st) {
        tdStatus.textContent = "log:" + (st.log_stream ? "✓" : "×") + " / upd:" + (st.update ? "✓" : "×");
      }
      tr.appendChild(tdStatus);

      const tdAct = document.createElement("td");
      const statusKnown = st && !st.error && !st.offline;
      const granted = statusKnown && (st.log_stream || st.update);
      const fullyGranted = statusKnown && st.log_stream && st.update;
      const btnGrant = document.createElement("button");
      btnGrant.className = "btn btn-sm";
      if (fullyGranted) {
        btnGrant.textContent = window.tr?.("fleet.settings.remote.already_granted", "Already granted") || "Already granted";
        btnGrant.disabled = true;
      } else {
        btnGrant.textContent = window.tr?.("fleet.settings.remote.grant", "Grant this peer") || "Grant this peer";
        btnGrant.addEventListener("click", () => ns.peerGrantRevoke(peer.peer_id, "grant", btnGrant));
      }

      const btnRevoke = document.createElement("button");
      btnRevoke.className = "btn btn-sm btn-secondary";
      if (statusKnown && !granted) {
        btnRevoke.textContent = window.tr?.("fleet.settings.remote.not_granted", "Not granted") || "Not granted";
        btnRevoke.disabled = true;
      } else {
        btnRevoke.textContent = window.tr?.("fleet.settings.remote.revoke", "Revoke this peer") || "Revoke this peer";
        btnRevoke.addEventListener("click", () => ns.peerGrantRevoke(peer.peer_id, "revoke", btnRevoke));
      }

      if (st && st.offline) {
        btnGrant.disabled = true;
        btnRevoke.disabled = true;
      }

      tdAct.append(btnGrant, document.createTextNode(" "), btnRevoke);
      tr.appendChild(tdAct);
      tbody.appendChild(tr);
    });
  };

  ns.peerGrantRevoke = async function peerGrantRevoke(peerId, action, btn) {
    btn.disabled = true;
    btn.textContent = "...";
    try {
      const { resp, data } = await ns.postPeerAllowlist(peerId, action, ["log_stream", "update"]);
      if (resp.ok && data.ok) {
        btn.textContent = window.tr?.("fleet.settings.remote.done", "Done") || "Done";
      } else {
        const msg = data.message || data.error || `HTTP ${resp.status}`;
        btn.textContent = (window.tr?.("fleet.settings.remote.failed", "Failed") || "Failed") + ": " + msg;
      }
    } catch (e) {
      btn.textContent = (window.tr?.("fleet.settings.remote.failed", "Failed") || "Failed") + ": " + e.message;
    } finally {
      setTimeout(async () => {
        await loadRemoteStatuses();
        ns.renderSettingsRemoteTable();
      }, 800);
    }
  };

  ns.saveLocalAllowlists = async function saveLocalAllowlists() {
    const status = document.getElementById("fleet-settings-local-status");
    const logStream = [];
    const update = [];
    document.querySelectorAll("#fleet-settings-local-tbody input[type=checkbox]").forEach(cb => {
      if (!cb.checked) return;
      if (cb.dataset.kind === "log_stream") logStream.push(cb.dataset.peerId);
      if (cb.dataset.kind === "update") update.push(cb.dataset.peerId);
    });
    const allowRemoteUpdate = !!document.getElementById("fleet-settings-allow-remote-update")?.checked;
    try {
      const { resp, data } = await ns.saveAllowlists({
        allow_log_stream_from: logStream,
        allow_update_from: update,
        allow_remote_update: allowRemoteUpdate,
      });
      if (resp.ok && data.ok) {
        state.settings.current = {
          allow_log_stream_from: data.allow_log_stream_from || [],
          allow_update_from: data.allow_update_from || [],
          allow_remote_update: !!data.allow_remote_update,
        };
        if (status) {
          status.textContent = window.tr?.("fleet.settings.saved", "Saved") || "Saved";
          setTimeout(() => { status.textContent = ""; }, 2500);
        }
      } else if (status) {
        status.textContent = (window.tr?.("fleet.settings.save_failed", "Save failed") || "Save failed") + ": " + (data.error || resp.status);
      }
    } catch (e) {
      if (status) {
        status.textContent = (window.tr?.("fleet.settings.save_failed", "Save failed") || "Save failed") + ": " + e.message;
      }
    }
  };

  ns.initSettingsTab = async function initSettingsTab(peers) {
    state.settings.peers = peers || [];
    await loadAllowlists();
    ns.renderSettingsLocalTable();
    ns.renderSettingsRemoteTable();
    loadRemoteStatuses().then(ns.renderSettingsRemoteTable);
    if (state.settings.inited) return;
    state.settings.inited = true;
    document.getElementById("fleet-settings-local-save")?.addEventListener("click", ns.saveLocalAllowlists);
  };
})();

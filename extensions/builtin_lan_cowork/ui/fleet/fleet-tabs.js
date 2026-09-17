/* Fleet admin UI tab wiring */
(function () {
  "use strict";

  const ns = window.__fleetAdmin = window.__fleetAdmin || {};
  const state = ns.state = ns.state || {};
  state.logs = state.logs || { inited: false, abortCtrl: null, selectedPeer: null, paused: false, lines: [] };
  state.update = state.update || { inited: false, peers: [], pollTimer: null };

  const STEP_LABELS = {
    git_precheck: "precheck",
    git_fetch: "fetching",
    git_pull_ff_only: "pulling",
    restart_signal: "restarting",
    postcheck_online: "online",
    awaiting_restart: "awaiting restart",
    online: "online",
  };

  ns.renderLogPeerList = function renderLogPeerList(peers) {
    const list = document.getElementById("fleet-logs-peer-list");
    if (!list) return;
    list.replaceChildren();
    peers.forEach((peer, i) => {
      const label = document.createElement("label");
      label.className = "fleet-logs-peer-radio";
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "fleet-logs-peer";
      radio.value = peer.peer_id;
      if (i === 0 && !state.logs.selectedPeer) radio.checked = true;
      radio.addEventListener("change", () => {
        state.logs.selectedPeer = peer.peer_id;
        ns.connectLogStream(peer.peer_id);
      });
      label.appendChild(radio);
      label.append(" " + ns.escHtmlLog(peer.name || peer.peer_id));
      list.appendChild(label);
    });
    if (peers.length > 0 && !state.logs.selectedPeer) {
      state.logs.selectedPeer = peers[0].peer_id;
      ns.connectLogStream(state.logs.selectedPeer);
    }
  };

  ns.renderUpdateTable = function renderUpdateTable(peers) {
    const tbody = document.getElementById("fleet-update-tbody");
    if (!tbody) return;
    state.update.peers = peers;
    tbody.replaceChildren();
    peers.forEach(peer => {
      const info = peer.info || {};
      const git = info.git || {};
      const isChief = (peer.roles || []).includes("chief");
      const tr = document.createElement("tr");
      tr.dataset.peerId = peer.peer_id;

      const tdCheck = document.createElement("td");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = peer.peer_id;
      checkbox.disabled = isChief;
      checkbox.setAttribute("aria-label", "Select " + (peer.name || peer.peer_id));
      tdCheck.appendChild(checkbox);
      tr.appendChild(tdCheck);

      const tdName = document.createElement("td");
      tdName.textContent = peer.name || peer.peer_id;
      if (isChief) {
        const badge = document.createElement("span");
        badge.className = "fleet-badge-chief";
        badge.textContent = "CHIEF";
        tdName.appendChild(badge);
      }
      tr.appendChild(tdName);

      [["version", info.version || "-"], ["commit", (git.commit || "-") + (git.dirty ? " *" : "")], ["branch", git.branch || "-"]]
        .forEach(([, text]) => {
          const td = document.createElement("td");
          td.textContent = text;
          tr.appendChild(td);
        });

      const tdAction = document.createElement("td");
      const btn = document.createElement("button");
      btn.className = "btn btn-sm";
      btn.textContent = window.tr?.("fleet.update.button.pull_restart", "Pull & Restart") || "Pull & Restart";
      btn.disabled = isChief;
      btn.addEventListener("click", () => ns.singlePullRestart(peer.peer_id));
      tdAction.appendChild(btn);

      const btnRestart = document.createElement("button");
      btnRestart.className = "btn btn-sm";
      btnRestart.style.marginLeft = "0.4rem";
      btnRestart.textContent = window.tr?.("fleet.update.button.restart_only", "Restart only") || "Restart only";
      btnRestart.disabled = isChief;
      btnRestart.addEventListener("click", () => ns.singleRestart(peer.peer_id));
      tdAction.appendChild(btnRestart);
      tr.appendChild(tdAction);

      const tdProgress = document.createElement("td");
      tdProgress.id = "fleet-update-progress-" + peer.peer_id;
      tdProgress.textContent = "-";
      tr.appendChild(tdProgress);
      tbody.appendChild(tr);
    });
  };

  ns.updateProgressCell = function updateProgressCell(peerId, peerStatus) {
    const cell = document.getElementById("fleet-update-progress-" + peerId);
    if (!cell) return;
    const step = peerStatus.current_step || (peerStatus.status === "success" ? "online" : "");
    const label = STEP_LABELS[step] || step || peerStatus.status || "-";
    const statusClass = peerStatus.status === "success" ? "--success" : peerStatus.status === "failed" ? "--failed" : "--running";
    const span = document.createElement("span");
    span.className = "fleet-update-step fleet-update-step" + statusClass;
    const errText = peerStatus.status === "failed" && peerStatus.error ? ` (${peerStatus.error})` : "";
    span.textContent = label + errText;
    if (errText) span.title = peerStatus.error;
    cell.replaceChildren(span);
    if (peerStatus.status === "failed" && peerStatus.error === "remote_update_disabled") {
      ns.showConsentPanel(
        peerId,
        (window.tr?.("fleet.consent.chief.send_request_for", "Remote update disabled for {peer}. Send consent request?")
          || "Remote update disabled for {peer}. Send consent request?").replace("{peer}", peerId),
      );
    }
  };

  ns.initUpdateTab = function initUpdateTab(peers) {
    ns.renderUpdateTable(peers);
    if (state.update.inited) return;
    state.update.inited = true;
    document.getElementById("fleet-update-dispatch-btn")?.addEventListener("click", ns.dispatchSelected);
    document.getElementById("fleet-restart-dispatch-btn")?.addEventListener("click", ns.dispatchRestartSelected);
    document.getElementById("fleet-update-select-all")?.addEventListener("change", event => {
      document.querySelectorAll("#fleet-update-tbody input[type=checkbox]:not(:disabled)")
        .forEach(cb => { cb.checked = event.target.checked; });
    });
    document.getElementById("fleet-consent-send-btn")?.addEventListener("click", ns.sendConsentRequest);
    document.getElementById("fleet-consent-cancel-btn")?.addEventListener("click", ns.hideConsentPanel);
    document.getElementById("fleet-consent-retry-btn")?.addEventListener("click", ns.sendConsentRequest);
  };

  ns.initLogsTab = function initLogsTab(peers) {
    ns.renderLogPeerList(peers);
    if (state.logs.inited) return;
    state.logs.inited = true;
    document.getElementById("fleet-logs-pause-btn")?.addEventListener("click", () => {
      state.logs.paused = !state.logs.paused;
      const btn = document.getElementById("fleet-logs-pause-btn");
      if (!btn) return;
      btn.textContent = state.logs.paused
        ? (window.tr?.("fleet.logs.resume", "Resume") || "Resume")
        : (window.tr?.("fleet.logs.pause", "Pause") || "Pause");
    });
    document.getElementById("fleet-logs-level")?.addEventListener("change", () => {
      if (state.logs.selectedPeer) ns.connectLogStream(state.logs.selectedPeer);
    });
    document.getElementById("fleet-logs-clear-btn")?.addEventListener("click", () => {
      state.logs.lines = [];
      const output = document.getElementById("fleet-logs-output");
      if (output) output.replaceChildren();
    });
    document.getElementById("fleet-logs-copy-btn")?.addEventListener("click", ns.copyLogsToClipboard);
    document.getElementById("fleet-logs-download-btn")?.addEventListener("click", ns.downloadLogs);
    document.querySelectorAll(".fleet-tab").forEach(btn => {
      btn.addEventListener("click", () => {
        if (btn.dataset.tab !== "logs") {
          ns.stopLogStream();
        } else if (state.logs.selectedPeer && !state.logs.abortCtrl) {
          ns.connectLogStream(state.logs.selectedPeer);
        }
      });
    });
  };
})();

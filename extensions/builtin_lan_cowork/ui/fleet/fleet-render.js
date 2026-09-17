/* Fleet admin UI render helpers */
(function () {
  "use strict";

  const ns = window.__fleetAdmin = window.__fleetAdmin || {};
  const state = ns.state = ns.state || {};
  state.logs = state.logs || { selectedPeer: null, paused: false, lines: [] };

  ns.escHtml = function escHtml(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  };

  ns.escHtmlLog = function escHtmlLog(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  };

  function statusLabel(peer, timings) {
    const timeoutMs = (timings.heartbeat_timeout_sec || 60) * 1000;
    const hbAt = peer.last_heartbeat_at ? new Date(peer.last_heartbeat_at).getTime() : 0;
    const hbRecent = hbAt && (Date.now() - hbAt) < timeoutMs;
    if (!hbRecent && !peer.reachable) return "offline";
    if (hbRecent && !peer.reachable) return "degraded";
    return "online";
  }
  ns.peerStatusLabel = statusLabel;

  function barFillClass(pct) {
    if (pct >= 85) return "fleet-bar-fill--high";
    if (pct >= 65) return "fleet-bar-fill--medium";
    return "";
  }

  function renderBar(label, pct) {
    const safePct = Number(pct) || 0;
    return (
      '<div class="fleet-node-row">'
      + '<span class="fleet-node-row-label">' + ns.escHtml(label) + "</span>"
      + '<div class="fleet-bar"><div class="fleet-bar-fill ' + ns.escHtml(barFillClass(pct))
      + '" style="width:' + safePct + '%"></div></div>'
      + '<span class="fleet-bar-pct">' + safePct + "%</span>"
      + "</div>"
    );
  }

  function renderCard(peer, timings) {
    const info = peer.info || {};
    const status = statusLabel(peer, timings);
    const isChief = (peer.roles || []).includes("chief");
    const chiefBadge = isChief ? '<span class="fleet-badge-chief">CHIEF</span>' : "";
    const statusText = (window.tr && window.tr("fleet.node.status." + status)) || status;
    const restartTitle = (window.tr && window.tr("fleet.button.restart_node")) || "Restart this node";
    const restartBtn = isChief
      ? ""
      : '<button type="button" class="fleet-node-restart-btn" '
        + 'data-action="restart-node" '
        + 'data-peer-id="' + ns.escHtml(peer.peer_id) + '" '
        + 'title="' + ns.escHtml(restartTitle) + '" '
        + 'aria-label="' + ns.escHtml(restartTitle) + '">&#x21bb;</button>';
    const cpu = info.cpu || {};
    const ram = info.ram || {};
    const disk = info.disk || {};
    const git = info.git || {};
    const gpus = Array.isArray(info.gpus) && info.gpus.length > 0 ? info.gpus : [info.gpu || {}];
    const uptimeSec = info.process_uptime_sec || 0;
    const uptimeStr = uptimeSec >= 3600
      ? Math.floor(uptimeSec / 3600) + "h " + Math.floor((uptimeSec % 3600) / 60) + "m"
      : Math.floor(uptimeSec / 60) + "m";
    const gitStr = git.branch
      ? git.branch + " @ " + (git.commit || "?") + (git.dirty ? " *" : "")
      : "-";

    return (
      '<div class="fleet-node-card">'
      + '<div class="fleet-node-header">'
      + '<span class="fleet-node-name">' + ns.escHtml(peer.name || peer.peer_id) + chiefBadge + "</span>"
      + '<span class="fleet-node-status">'
      + '<span class="fleet-status-dot fleet-status-dot--' + ns.escHtml(status) + '"></span>'
      + ns.escHtml(statusText)
      + restartBtn
      + "</span>"
      + "</div>"
      + '<div class="fleet-node-meta">' + ns.escHtml(info.version || "-") + " &nbsp; "
      + ns.escHtml((info.os || {}).system || "") + " " + ns.escHtml((info.os || {}).release || "") + "</div>"
      + renderBar("CPU", cpu.usage_pct ?? 0)
      + '<div class="fleet-node-row"><span class="fleet-node-row-label">CPU</span><span>'
      + ns.escHtml(cpu.name || "-") + "</span></div>"
      + renderBar("RAM", ram.pct ?? 0)
      + '<div class="fleet-node-row"><span class="fleet-node-row-label"></span><span>'
      + ns.escHtml(String(ram.total_gb || "-")) + " GB</span></div>"
      + gpus.map(function (gpu, i) {
        const vramTotal = Number(gpu.vram_total_gb) || 0;
        const vramUsed = Number(gpu.vram_used_gb) || 0;
        const vramPct = vramTotal > 0 ? Math.round((vramUsed / vramTotal) * 100) : null;
        const gpuUtil = gpu.utilization_pct;
        const suffix = gpus.length > 1 ? String(i + 1) : "";
        return (
          '<div class="fleet-node-row"><span class="fleet-node-row-label">GPU' + suffix + '</span><span>'
          + ns.escHtml(gpu.name || "-") + "</span></div>"
          + (vramPct !== null
            ? renderBar("VRAM" + suffix, vramPct)
              + '<div class="fleet-node-row"><span class="fleet-node-row-label"></span><span>'
              + ns.escHtml(String(vramUsed)) + " / " + ns.escHtml(String(vramTotal)) + " GB</span></div>"
            : "")
          + (gpuUtil !== null && gpuUtil !== undefined
            ? renderBar("GPU" + suffix + "%", Number(gpuUtil) || 0)
            : "")
        );
      }).join("")
      + renderBar("Disk", disk.pct ?? 0)
      + '<div class="fleet-node-row"><span class="fleet-node-row-label"></span><span>'
      + ns.escHtml(String(disk.total_gb || "-")) + " GB</span></div>"
      + '<div class="fleet-node-row"><span class="fleet-node-row-label">Uptime</span><span>'
      + ns.escHtml(uptimeStr) + "</span></div>"
      + '<div class="fleet-node-row"><span class="fleet-node-row-label">git</span><span>'
      + ns.escHtml(gitStr) + "</span></div>"
      + "</div>"
    );
  }

  ns.renderOverviewError = function renderOverviewError(message) {
    const grid = document.getElementById("fleet-nodes-grid");
    if (!grid) return;
    const p = document.createElement("p");
    p.className = "fleet-error";
    p.textContent = message;
    grid.replaceChildren(p);
  };

  ns.renderOverviewData = function renderOverviewData(data) {
    const grid = document.getElementById("fleet-nodes-grid");
    if (!grid) return;

    const banner = document.getElementById("fleet-multi-chief-banner");
    if (banner) {
      const chiefs = (data.roles_index || {}).chief || [];
      banner.style.display = chiefs.length > 1 ? "" : "none";
    }

    if (data.peers) {
      ns.initLogsTab(data.peers);
      ns.initUpdateTab(data.peers);
      ns.initSettingsTab(data.peers);
    }

    const timings = window._fleetTimings || {};
    grid.innerHTML = (data.peers || []).map(peer => renderCard(peer, timings)).join("");
  };

  ns.formatLogLine = function formatLogLine(entry, searchText) {
    const ts = new Date(entry.timestamp * 1000).toISOString().replace("T", " ").slice(0, 23);
    const line = `[${ts}] [${entry.level}] ${entry.source}: ${entry.message}`;
    if (searchText && !line.toLowerCase().includes(searchText.toLowerCase())) return null;
    return line;
  };

  ns.appendLogLine = function appendLogLine(entry) {
    const search = document.getElementById("fleet-logs-search")?.value || "";
    const line = ns.formatLogLine(entry, search);
    if (line === null) return;

    state.logs.lines.push(entry);
    if (state.logs.lines.length > 5000) state.logs.lines.shift();

    const output = document.getElementById("fleet-logs-output");
    if (!output || state.logs.paused) return;

    const p = document.createElement("p");
    p.className = "fleet-log-line fleet-log-line--" + ns.escHtmlLog(entry.level);
    p.textContent = line;
    output.appendChild(p);
    while (output.children.length > 5000) output.removeChild(output.firstChild);

    const autoscroll = document.getElementById("fleet-logs-autoscroll");
    if (autoscroll?.checked) output.scrollTop = output.scrollHeight;
  };
})();

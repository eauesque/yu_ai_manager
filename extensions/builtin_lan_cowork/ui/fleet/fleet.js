/* Fleet admin UI entrypoint */
(function () {
  "use strict";

  const ns = window.__fleetAdmin = window.__fleetAdmin || {};

  function initTabs() {
    document.querySelectorAll(".fleet-tab").forEach(btn => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.tab;
        document.querySelectorAll(".fleet-tab").forEach(tabBtn => {
          tabBtn.classList.remove("fleet-tab--active");
        });
        document.querySelectorAll(".fleet-tab-panel").forEach(panel => {
          panel.style.display = "none";
        });
        btn.classList.add("fleet-tab--active");
        const panel = document.getElementById("fleet-tab-" + tab);
        if (panel) panel.style.display = "";
      });
    });
  }

  async function renderOverview(forceRefresh) {
    try {
      const data = await ns.fetchPeers(forceRefresh);
      ns.renderOverviewData(data);
    } catch (e) {
      ns.renderOverviewError("取得失敗: " + e.message);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.body.classList.add("i18n-ready");
    initTabs();
    document.getElementById("fleet-refresh-btn")
      ?.addEventListener("click", () => renderOverview(true));

    document.getElementById("fleet-nodes-grid")
      ?.addEventListener("click", event => {
        const btn = event.target && event.target.closest
          ? event.target.closest('[data-action="restart-node"]')
          : null;
        if (!btn) return;
        const peerId = btn.dataset.peerId;
        if (peerId) ns.singleRestart(peerId);
      });

    renderOverview(false);
    ns.startOverviewPolling(renderOverview);
  });
})();

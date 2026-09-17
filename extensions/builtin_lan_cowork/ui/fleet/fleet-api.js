/* Fleet admin UI API helpers */
(function () {
  "use strict";

  const ns = window.__fleetAdmin = window.__fleetAdmin || {};

  async function fetchJson(url, options) {
    const resp = await fetch(url, options);
    const data = await resp.json().catch(() => ({}));
    return { resp, data };
  }

  ns.fetchPeers = async function fetchPeers(forceRefresh) {
    const url = "/ext/lan_cowork/fleet/peers" + (forceRefresh ? "?force_refresh=true" : "");
    const { resp, data } = await fetchJson(url, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    return data;
  };

  ns.requestConsentRelay = async function requestConsentRelay(peerId, requestId) {
    return fetchJson("/ext/lan_cowork/fleet/consent/relay/request", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ peer_id: peerId, request_id: requestId }),
    });
  };

  ns.fetchConsentStatus = async function fetchConsentStatus(peerId, requestId) {
    const url = "/ext/lan_cowork/fleet/consent/relay/status"
      + `?peer_id=${encodeURIComponent(peerId)}`
      + `&request_id=${encodeURIComponent(requestId)}`;
    return fetchJson(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
  };

  ns.dispatchUpdate = async function dispatchUpdate(peerIds, source, branch, consentTokens) {
    return fetchJson("/ext/lan_cowork/fleet/update/dispatch", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({
        peer_ids: peerIds,
        source,
        branch,
        consent_tokens: consentTokens || {},
      }),
    });
  };

  ns.dispatchRestart = async function dispatchRestart(peerIds) {
    return fetchJson("/ext/lan_cowork/fleet/restart/dispatch", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify({ peer_ids: peerIds }),
    });
  };

  ns.fetchDispatchStatus = async function fetchDispatchStatus(dispatchId) {
    const url = "/ext/lan_cowork/fleet/update/dispatch/status"
      + `?dispatch_id=${encodeURIComponent(dispatchId)}`;
    return fetchJson(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
  };

  ns.fetchAllowlists = async function fetchAllowlists() {
    return fetchJson("/ext/lan_cowork/api/settings/fleet/allowlists");
  };

  ns.fetchPeerAllowlistStatus = async function fetchPeerAllowlistStatus(peerId) {
    const url = "/ext/lan_cowork/fleet/peer-allowlist-status"
      + `?peer_id=${encodeURIComponent(peerId)}`;
    return fetchJson(url);
  };

  ns.postPeerAllowlist = async function postPeerAllowlist(peerId, action, categories) {
    const endpoint = action === "grant" ? "peer-grant" : "peer-revoke";
    return fetchJson(`/ext/lan_cowork/fleet/${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "FleetAdmin",
      },
      body: JSON.stringify({ peer_id: peerId, categories }),
    });
  };

  ns.saveAllowlists = async function saveAllowlists(payload) {
    return fetchJson("/ext/lan_cowork/api/settings/fleet/allowlists", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "FleetAdmin",
      },
      body: JSON.stringify(payload),
    });
  };
})();

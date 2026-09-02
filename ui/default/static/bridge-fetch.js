// Bridge fetch helper — single source of truth for routing bridge API calls
// (generate / progress / cancel) to either the local bridge or, when LAN
// Cowork dispatches to a peer, to the peer-relay endpoint.
//
// Without this helper, every bridge-side script had to repeat the
// `if (window._lanCoworkEnabled && _lanCoworkDispatch(...))` branch and
// stuff `body.source_peer` / `body.target_peer` into the body. That was
// the breeding ground for the asymmetries documented in
// docs/development/development_docs/LAN_COWORK_PATH_ASYMMETRY.md.
//
// Server side, /api/peer/* and /ext/<bridge>/api/* both delegate to the
// same Python handlers (core/bridge_core/bridge_handlers.py), so request
// and response shape are guaranteed to match. This helper just decides
// which URL to hit.

(function () {
  "use strict";

  function _resolveDispatch(bridge) {
    if (!window._lanCoworkEnabled) return null;
    if (typeof window._lanCoworkDispatch !== "function") return null;
    return window._lanCoworkDispatch(bridge) || null;
  }

  // bridgeFetch(bridge, action, body, opts)
  //   bridge: "comfyui" | "sd-webui" | "nai"
  //   action: "generate" | "progress" | "cancel"
  //   body: optional object — POSTed as JSON; for "progress" it is sent as
  //         body when peer-routed (so the peer can pick the bridge), and
  //         ignored when local-routed.
  //   opts: { signal, headers, localBase }
  //         localBase overrides the local bridge prefix (defaults to
  //         "/ext/<bridge>-bridge"; NAI's prefix is "/ext/nai-bridge",
  //         ComfyUI's "/ext/comfyui-bridge", SD WebUI's "/ext/sd-webui").
  window.bridgeFetch = function (bridge, action, body, opts) {
    opts = opts || {};
    body = body || {};
    var dispatch = _resolveDispatch(bridge);
    var url;
    var bodyToSend;
    if (dispatch) {
      url = "/ext/lan_cowork/api/peer/" + action;
      bodyToSend = Object.assign({}, body, {
        bridge: bridge,
        source_peer: dispatch.local_peer_id,
        target_peer: dispatch.target_peer_id,
      });
    } else {
      var localBase = opts.localBase || _defaultLocalBase(bridge);
      url = localBase + "/api/" + action;
      bodyToSend = body;
    }

    var method = action === "progress" ? (dispatch ? "POST" : "GET") : "POST";
    if (method === "GET" && bodyToSend && Object.keys(bodyToSend).length > 0) {
      var qs = new URLSearchParams(bodyToSend).toString();
      if (qs) url += "?" + qs;
    }
    var fetchInit = {
      method: method,
      headers: Object.assign(
        {
          "X-Requested-With": "XMLHttpRequest",
          "Content-Type": "application/json",
        },
        opts.headers || {}
      ),
    };
    if (method === "POST") {
      fetchInit.body = JSON.stringify(bodyToSend);
    }
    if (opts.signal) fetchInit.signal = opts.signal;
    return fetch(url, fetchInit);
  };

  function _defaultLocalBase(bridge) {
    if (bridge === "comfyui") return "/ext/comfyui-bridge";
    if (bridge === "sd-webui") return "/ext/sd-webui";
    if (bridge === "nai") return "/ext/nai-bridge";
    return "/ext/" + bridge + "-bridge";
  }

  // Convenience: returns true when the given bridge dispatch would go to
  // a peer right now. Useful for UI state (progress polling cadence,
  // cancel button label, etc.).
  window.bridgeIsPeerDispatched = function (bridge) {
    return !!_resolveDispatch(bridge);
  };
})();

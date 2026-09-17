// Helper for child iframes / standalone pages to send-to-bridge.
// - In Tauri shell (or /tauri-shell): postMessage to parent shell
// - In browser standalone: window.open (new tab) or window.location.href (same tab)
//   based on bridgeNav:openInNewTab setting and Ctrl/Cmd/auxclick modifiers.
// Spec: docs/superpowers/specs/2026-05-04-browser-bridge-new-tab-design.md (rev4)

(function () {
  const ORIGIN = window.location.origin;
  const NEW_TAB_SETTING_KEY = "bridgeNav:openInNewTab";

  // bridgeId -> {category, tab} mapping (fetched from tabs.json on first use)
  let _targets = null;
  async function loadTargets() {
    if (_targets) return _targets;
    try {
      const r = await fetch("/api/tauri-shell/tabs", {cache: "no-cache"});
      const j = await r.json();
      _targets = j.bridgeTargets || {};
    } catch (_) { _targets = {}; }
    return _targets;
  }

  function inShell() {
    try { return window.parent !== window && !!window.parent.__tauriShell; }
    catch (_) { return false; }
  }

  function bridgeUrl(bridge, payload) {
    const map = {nai: "/ext/nai-bridge/", comfyui: "/ext/comfyui-bridge/", a1111: "/ext/sd-webui/"};
    const base = map[bridge] || "/";
    const qs = payload && Object.keys(payload).length
      ? "?" + new URLSearchParams(flattenPayload(payload)).toString()
      : "";
    return base + qs;
  }

  function flattenPayload(p) {
    const out = {};
    Object.keys(p || {}).forEach(k => {
      const v = p[k];
      out[k] = typeof v === "object" ? JSON.stringify(v) : String(v);
    });
    return out;
  }

  function shouldOpenNewTab(evt) {
    // auxclick (middle button) is always new-tab regardless of setting.
    if (evt && evt.type === "auxclick" && evt.button === 1) return true;
    const setting = localStorage.getItem(NEW_TAB_SETTING_KEY) === "true";
    // shift is intentionally NOT considered (treated as plain click). Spec §3.2 / §8.
    const modifier = !!(evt && (evt.ctrlKey || evt.metaKey));
    return modifier ? !setting : setting;
  }

  function openInNewTabWithFallback(url) {
    const win = window.open(url, "_blank", "noopener");
    if (!win) {
      const msg = (window.tr && window.tr("bridge_nav.popup_blocked"))
        || "ポップアップがブロックされました。同タブで開きました";
      if (window.showToast) window.showToast(msg);
      window.location.href = url;
      return;
    }
    if (window.showToast) {
      const ok = (window.tr && window.tr("bridge_nav.opened_in_new_tab"))
        || "新しいタブで開きました";
      window.showToast(ok);
    }
  }

  async function sendToBridge(bridge, payload, evt) {
    if (inShell()) {
      const targets = await loadTargets();
      const target = targets[bridge];
      if (!target) {
        console.error("[cross_tab] unknown bridge:", bridge);
        return;
      }
      window.parent.postMessage({
        type: "tauri-shell:switch-and-send",
        target, payload,
      }, ORIGIN);
      return;
    }
    const url = bridgeUrl(bridge, payload);
    if (shouldOpenNewTab(evt)) {
      openInNewTabWithFallback(url);
    } else {
      window.location.href = url;
    }
  }

  window.tauriCrossTab = {sendToBridge, inShell, shouldOpenNewTab};
})();

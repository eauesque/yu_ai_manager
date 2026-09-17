// Injected by shell into iframe.contentDocument after iframe load.
// Responsibilities:
//   1. Forward keyboard shortcuts to parent shell.
//   2. Send tauri-shell:ready handshake on DOMContentLoaded.
// Spec: §4.1, §4.2

(function () {
  if (window.__tauriShortcutBridgeAttached) return;
  window.__tauriShortcutBridgeAttached = true;

  const ORIGIN = window.location.origin;
  const tabId = (function () {
    const me = document.currentScript;
    return me && me.dataset && me.dataset.tabId ? me.dataset.tabId : "unknown";
  })();

  function sendReady() {
    try {
      window.parent.postMessage({type: "tauri-shell:ready", tab: tabId}, ORIGIN);
    } catch (_) {}
  }

  if (document.readyState === "complete" || document.readyState === "interactive") {
    setTimeout(sendReady, 0);
  } else {
    document.addEventListener("DOMContentLoaded", sendReady, {once: true});
  }

  function isForwardKey(e) {
    if (e.ctrlKey && !e.shiftKey && !e.altKey && /^[1-4]$/.test(e.key)) return true;
    if (e.ctrlKey && e.key === "Tab") return true;
    if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) return true;
    return false;
  }

  document.addEventListener("keydown", (e) => {
    if (!isForwardKey(e)) return;
    e.preventDefault();
    try {
      window.parent.postMessage({
        type: "tauri-shell:shortcut",
        key: e.key,
        modifiers: {ctrl: e.ctrlKey, shift: e.shiftKey, alt: e.altKey},
      }, ORIGIN);
    } catch (_) {}
  }, true);
})();

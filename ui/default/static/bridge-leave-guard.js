// Bridge leave guard — warns the user before navigating away while a
// generation is in progress.
//
// Two leave paths are covered:
//   1. In-page <a href> clicks (capture-phase listener) — shows a custom
//      confirm() dialog with a translatable message. The user can cancel
//      navigation to keep the in-flight generation visible.
//   2. window.beforeunload (reload / close / external nav) — sets
//      returnValue so the browser shows its built-in "leave site?"
//      warning. The browser does NOT honor a custom message here, so we
//      rely on the standard prompt as a last-line backstop.
//
// Usage from a bridge script:
//   BridgeLeaveGuard.install({ isGenerating: function() { return generating; } });
//
// install() is idempotent: calling it again replaces the predicate, so
// each bridge page can install once on load.

(function () {
  "use strict";

  var state = {
    isGenerating: null,
  };
  var installed = false;

  function shouldGuard() {
    try {
      return !!(state.isGenerating && state.isGenerating());
    } catch (_e) {
      return false;
    }
  }

  function leaveMessage() {
    var fallback = "生成中の画像は保存されない可能性があります。タブから移動しますか？";
    if (typeof window.tr === "function") {
      return window.tr("bridge.leave_warning", fallback);
    }
    return fallback;
  }

  function findAnchor(target) {
    while (target && target !== document) {
      if (target.tagName === "A" && target.getAttribute("href")) return target;
      target = target.parentNode;
    }
    return null;
  }

  function onClickCapture(ev) {
    if (!shouldGuard()) return;
    if (ev.defaultPrevented) return;
    if (ev.button !== 0) return; // primary click only
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return; // open in new tab etc.
    var a = findAnchor(ev.target);
    if (!a) return;
    var href = a.getAttribute("href") || "";
    if (!href || href.charAt(0) === "#") return; // in-page anchor
    if (a.target && a.target !== "" && a.target !== "_self") return; // _blank etc.
    if (href.indexOf("javascript:") === 0) return;
    if (a.hasAttribute("download")) return;
    // window.customConfirm is async; we must block the click synchronously
    // and re-trigger navigation only if the user confirms.
    ev.preventDefault();
    ev.stopPropagation();
    var confirmFn = typeof window.customConfirm === "function"
      ? window.customConfirm
      : function (m) { return Promise.resolve(window.confirm(m)); };
    confirmFn(leaveMessage(), { danger: true }).then(function (ok) {
      if (ok) {
        // Temporarily disable the guard so the re-issued navigation isn't
        // intercepted again, then restore it on the next tick.
        var prev = state.isGenerating;
        state.isGenerating = null;
        try {
          var resolved = a.href || href;
          window.location.href = resolved;
        } finally {
          setTimeout(function () { state.isGenerating = prev; }, 0);
        }
      }
    });
  }

  function onBeforeUnload(ev) {
    if (!shouldGuard()) return;
    ev.preventDefault();
    ev.returnValue = "";
    return "";
  }

  function ensureListeners() {
    if (installed) return;
    document.addEventListener("click", onClickCapture, true);
    window.addEventListener("beforeunload", onBeforeUnload);
    installed = true;
  }

  window.BridgeLeaveGuard = {
    install: function (opts) {
      opts = opts || {};
      if (typeof opts.isGenerating === "function") {
        state.isGenerating = opts.isGenerating;
      }
      ensureListeners();
    },
  };
})();

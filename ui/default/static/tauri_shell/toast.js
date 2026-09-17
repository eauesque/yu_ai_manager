// Minimal toast helper.
// Exposes window.showToast(message) using #shell-toast element appended to body.
// Spec: 2026-05-04-browser-bridge-new-tab-design.md §6.2

(function () {
  if (window.showToast) return;  // idempotent — safe if loaded twice

  function ensureElement() {
    let el = document.getElementById("shell-toast");
    if (el) return el;
    el = document.createElement("div");
    el.id = "shell-toast";
    if (document.body) {
      document.body.appendChild(el);
    } else {
      document.addEventListener("DOMContentLoaded", function () {
        document.body.appendChild(el);
      }, {once: true});
    }
    return el;
  }

  let _hideTimer = null;
  function showToast(message) {
    const el = ensureElement();
    el.textContent = message;
    el.classList.add("show");
    if (_hideTimer) clearTimeout(_hideTimer);
    _hideTimer = setTimeout(function () {
      el.classList.remove("show");
      _hideTimer = null;
    }, 3000);
  }

  window.showToast = showToast;
})();

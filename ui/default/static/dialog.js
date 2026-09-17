/*
 * dialog.js — in-app replacements for window.confirm / alert / prompt.
 *
 * Why: browser-native dialogs are inconsistent in Tauri, do not honor
 * dark-mode / CSS variables, and cannot be styled or instrumented.
 * Use window.customConfirm / customAlert / customPrompt everywhere
 * instead. See docs/development/development_docs/UI_DIALOG_POLICY.md.
 *
 * Loaded globally via templates/_nav.html so it is available in every page,
 * including inline <script> blocks in extension templates.
 */
(function () {
  'use strict';
  if (typeof window === 'undefined') return;

  var Z_INDEX = 10000;

  function tr(path, fallback) {
    try {
      if (typeof window.tr === 'function') return window.tr(path, fallback);
    } catch (e) { /* ignore */ }
    return fallback;
  }

  function makeOverlay() {
    var overlay = document.createElement('div');
    overlay.style.cssText = [
      'position:fixed', 'inset:0',
      'background:rgba(0,0,0,0.5)',
      'z-index:' + Z_INDEX,
      'display:flex', 'align-items:center', 'justify-content:center',
    ].join(';');
    return overlay;
  }

  var _dialogSeq = 0;

  // These modals replaced window.confirm/alert/prompt, but carried no role, no
  // aria-modal and no id or class of any kind. Two consequences, fixed here:
  // a screen reader announced them as an anonymous div, and nothing could
  // address them -- Playwright tests still listening for a native `dialog`
  // event silently never confirmed anything, so several delete tests were
  // asserting against an action that had not happened.
  function makeModal(kind, message) {
    var modal = document.createElement('div');
    modal.setAttribute('role', kind === 'alert' ? 'alertdialog' : 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('data-dialog', kind);
    if (message != null && String(message) !== '') {
      _dialogSeq += 1;
      modal.setAttribute('data-dialog-message-id', 'dlg-msg-' + _dialogSeq);
      modal.setAttribute('aria-labelledby', 'dlg-msg-' + _dialogSeq);
    }
    modal.style.cssText = [
      'background:var(--bg, #fff)',
      'color:var(--fg, #222)',
      'max-width:480px', 'width:90%',
      'border-radius:8px',
      'padding:24px',
      'box-shadow:0 10px 40px rgba(0,0,0,0.25)',
      'border:1px solid var(--border, #ddd)',
    ].join(';');
    return modal;
  }

  function makeMessage(text, modal) {
    var p = document.createElement('p');
    p.style.cssText = 'margin:0 0 20px;white-space:pre-line;line-height:1.6;font-size:0.95rem;';
    p.textContent = String(text == null ? '' : text);
    // Give the dialog its accessible name: aria-labelledby on the modal points
    // at this paragraph.
    var id = modal && modal.getAttribute('data-dialog-message-id');
    if (id) p.id = id;
    return p;
  }

  // `role` is the stable hook: "confirm" / "cancel" / "ok". Labels are
  // translated, so matching on text breaks with the locale.
  function makeButton(label, primary, danger, role) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = label;
    if (role) btn.setAttribute('data-dialog-action', role);
    var color = danger ? '#dc2626' : 'var(--accent, #2563eb)';
    if (primary) {
      btn.style.cssText = [
        'padding:8px 16px',
        'border:1px solid ' + color,
        'background:' + color,
        'color:#fff',
        'border-radius:5px',
        'cursor:pointer',
        'font-size:0.9rem',
        'font-weight:600',
      ].join(';');
    } else {
      btn.style.cssText = [
        'padding:8px 16px',
        'border:1px solid var(--border, #ccc)',
        'background:var(--bg, #fff)',
        'color:var(--fg, #222)',
        'border-radius:5px',
        'cursor:pointer',
        'font-size:0.9rem',
      ].join(';');
    }
    return btn;
  }

  function makeActions() {
    var d = document.createElement('div');
    d.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;';
    return d;
  }

  function mount(modal, onKey) {
    var overlay = makeOverlay();
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    document.addEventListener('keydown', onKey, true);
    return function cleanup() {
      document.removeEventListener('keydown', onKey, true);
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    };
  }

  window.customConfirm = function (message, options) {
    options = options || {};
    var okText = options.okText || tr('common.ok', 'OK');
    var cancelText = options.cancelText || tr('common.cancel', 'キャンセル');
    var danger = !!options.danger;
    return new Promise(function (resolve) {
      var modal = makeModal('confirm', message);
      modal.appendChild(makeMessage(message, modal));
      var actions = makeActions();
      var cancelBtn = makeButton(cancelText, false, false, 'cancel');
      var okBtn = makeButton(okText, true, danger, 'confirm');

      var cleanup;
      function onKey(e) {
        if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); cleanup(); resolve(false); }
        else if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); cleanup(); resolve(true); }
      }
      cancelBtn.addEventListener('click', function () { cleanup(); resolve(false); });
      okBtn.addEventListener('click', function () { cleanup(); resolve(true); });
      actions.appendChild(cancelBtn);
      actions.appendChild(okBtn);
      modal.appendChild(actions);
      cleanup = mount(modal, onKey);
      setTimeout(function () { okBtn.focus(); }, 0);
    });
  };

  window.customAlert = function (message, options) {
    options = options || {};
    var okText = options.okText || tr('common.ok', 'OK');
    return new Promise(function (resolve) {
      var modal = makeModal('alert', message);
      modal.appendChild(makeMessage(message, modal));
      var actions = makeActions();
      var okBtn = makeButton(okText, true, false, 'ok');

      var cleanup;
      function onKey(e) {
        if (e.key === 'Escape' || e.key === 'Enter') {
          e.preventDefault(); e.stopPropagation(); cleanup(); resolve();
        }
      }
      okBtn.addEventListener('click', function () { cleanup(); resolve(); });
      actions.appendChild(okBtn);
      modal.appendChild(actions);
      cleanup = mount(modal, onKey);
      setTimeout(function () { okBtn.focus(); }, 0);
    });
  };

  window.customPrompt = function (message, defaultValue, options) {
    options = options || {};
    var okText = options.okText || tr('common.ok', 'OK');
    var cancelText = options.cancelText || tr('common.cancel', 'キャンセル');
    var initial = defaultValue == null ? '' : String(defaultValue);
    return new Promise(function (resolve) {
      var modal = makeModal('prompt', message);
      modal.appendChild(makeMessage(message, modal));

      var input;
      if (options.multiline) {
        input = document.createElement('textarea');
        input.rows = 4;
        input.style.cssText = 'width:100%;box-sizing:border-box;padding:8px;border:1px solid var(--border, #ccc);border-radius:5px;background:var(--bg, #fff);color:var(--fg, #222);font-family:inherit;font-size:0.95rem;margin-bottom:16px;resize:vertical;';
      } else {
        input = document.createElement('input');
        input.type = 'text';
        input.style.cssText = 'width:100%;box-sizing:border-box;padding:8px;border:1px solid var(--border, #ccc);border-radius:5px;background:var(--bg, #fff);color:var(--fg, #222);font-size:0.95rem;margin-bottom:16px;';
      }
      input.value = initial;
      if (options.placeholder) input.placeholder = String(options.placeholder);
      modal.appendChild(input);

      var actions = makeActions();
      var cancelBtn = makeButton(cancelText, false, false, 'cancel');
      var okBtn = makeButton(okText, true, false, 'confirm');
      input.setAttribute('data-dialog-input', '');

      var cleanup;
      function onKey(e) {
        if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); cleanup(); resolve(null); }
        else if (e.key === 'Enter') {
          if (e.target && e.target.tagName === 'TEXTAREA') return;
          e.preventDefault(); e.stopPropagation(); cleanup(); resolve(input.value);
        }
      }
      cancelBtn.addEventListener('click', function () { cleanup(); resolve(null); });
      okBtn.addEventListener('click', function () { cleanup(); resolve(input.value); });
      actions.appendChild(cancelBtn);
      actions.appendChild(okBtn);
      modal.appendChild(actions);
      cleanup = mount(modal, onKey);
      setTimeout(function () { input.focus(); if (input.select) input.select(); }, 0);
    });
  };
})();

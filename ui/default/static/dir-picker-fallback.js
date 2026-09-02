/* dir-picker-fallback.js — server-side directory browser popover.
 * Used when the native OS folder dialog (/api/tools/select-folder) is unavailable
 * (headless build without the `native-dialog` Rust feature, or a browser sandbox
 * that can't return real filesystem paths). Walks /api/tools/list-dirs instead.
 *
 * Usage: window.dirPickerFallback(initialPath, function(selectedPath) { ... });
 */
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  window.dirPickerFallback = function (initialPath, onSelect) {
    var overlay = document.createElement('div');
    overlay.style.cssText =
      'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.55);' +
      'display:flex;align-items:center;justify-content:center;';
    var box = document.createElement('div');
    box.style.cssText =
      'background:#1e1e2a;color:#e0e0e0;border-radius:8px;padding:16px;' +
      'width:min(560px,90vw);max-height:70vh;display:flex;flex-direction:column;' +
      'font-family:system-ui,sans-serif;font-size:13px;box-shadow:0 10px 30px rgba(0,0,0,0.5);';
    box.innerHTML =
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">' +
      '<strong style="flex:1;">フォルダを選択</strong>' +
      '<button type="button" data-dpf-close style="background:none;border:none;color:inherit;cursor:pointer;font-size:16px;">✕</button>' +
      '</div>' +
      '<div data-dpf-roots style="margin-bottom:6px;"></div>' +
      '<div style="display:flex;gap:6px;margin-bottom:8px;">' +
      '<input type="text" data-dpf-path style="flex:1;background:rgba(0,0,0,0.25);color:inherit;border:1px solid rgba(127,127,127,0.35);border-radius:4px;padding:5px 8px;font-family:monospace;font-size:12px;">' +
      '<button type="button" data-dpf-go class="dpf-btn">移動</button>' +
      '</div>' +
      '<div data-dpf-list style="flex:1;overflow:auto;border:1px solid rgba(127,127,127,0.2);border-radius:4px;padding:4px;"></div>' +
      '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px;">' +
      '<button type="button" data-dpf-cancel class="dpf-btn">キャンセル</button>' +
      '<button type="button" data-dpf-select class="dpf-btn primary">この場所を選択</button>' +
      '</div>';
    var style = document.createElement('style');
    style.textContent =
      '.dpf-btn{background:rgba(127,127,127,0.15);color:inherit;border:1px solid rgba(127,127,127,0.35);' +
      'border-radius:4px;padding:5px 12px;cursor:pointer;font-size:12px;}' +
      '.dpf-btn:hover{background:rgba(127,127,127,0.28);}' +
      '.dpf-btn.primary{background:#4fc3f7;color:#003040;border-color:#4fc3f7;}' +
      '.dpf-row{display:flex;align-items:center;gap:6px;padding:4px 6px;border-radius:3px;cursor:pointer;}' +
      '.dpf-row:hover{background:rgba(127,127,127,0.15);}';
    box.appendChild(style);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    var pathEl = box.querySelector('[data-dpf-path]');
    var listEl = box.querySelector('[data-dpf-list]');
    var rootsEl = box.querySelector('[data-dpf-roots]');
    var current = initialPath || '';

    function close() {
      overlay.remove();
      document.removeEventListener('keydown', onKey);
    }
    function onKey(e) {
      if (e.key === 'Escape') close();
    }
    document.addEventListener('keydown', onKey);
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) close();
    });
    box.querySelector('[data-dpf-close]').addEventListener('click', close);
    box.querySelector('[data-dpf-cancel]').addEventListener('click', close);
    box.querySelector('[data-dpf-select]').addEventListener('click', function () {
      var val = pathEl.value.trim();
      if (val) onSelect(val);
      close();
    });
    box.querySelector('[data-dpf-go]').addEventListener('click', function () {
      load(pathEl.value.trim());
    });
    pathEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') load(pathEl.value.trim());
    });

    function load(path) {
      listEl.innerHTML = '<div style="opacity:0.6;padding:6px;">読込中...</div>';
      var q = path ? '?path=' + encodeURIComponent(path) : '';
      fetch('/api/tools/list-dirs' + q)
        .then(function (r) {
          if (!r.ok) throw new Error(String(r.status));
          return r.json();
        })
        .then(function (data) {
          if (data.error) throw new Error(data.error);
          current = data.current || '';
          pathEl.value = current;

          var roots = Array.isArray(data.roots) ? data.roots : [];
          rootsEl.innerHTML = roots
            .map(function (r) {
              return '<button type="button" class="dpf-btn" data-dpf-nav="' + esc(r) + '" style="margin-right:4px;">' + esc(r) + '</button>';
            })
            .join('');

          var html = '';
          if (data.parent) {
            html += '<div class="dpf-row" data-dpf-nav="' + esc(data.parent) + '">📁 ..</div>';
          }
          (data.dirs || []).forEach(function (d) {
            html += '<div class="dpf-row" data-dpf-nav="' + esc(d.path) + '">📁 ' + esc(d.name) + '</div>';
          });
          listEl.innerHTML = html || '<div style="opacity:0.6;padding:6px;">サブフォルダなし</div>';

          box.querySelectorAll('[data-dpf-nav]').forEach(function (el) {
            el.addEventListener('click', function () {
              load(el.getAttribute('data-dpf-nav'));
            });
          });
        })
        .catch(function (e) {
          listEl.innerHTML = '<div style="color:#e57373;padding:6px;">' + esc(e.message || 'error') + '</div>';
        });
    }

    load(current);
  };
})();

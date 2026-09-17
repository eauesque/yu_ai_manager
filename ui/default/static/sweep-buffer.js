/**
 * SweepBuffer — shared deferred-save buffer for Bridge Sweep runs.
 *
 * During a Sweep, each successfully generated image is appended to a
 * per-bridge localStorage buffer. The Sweep runner POSTs the whole batch
 * to the bridge's /api/save-batch endpoint when the run finishes
 * (normally, on graceful stop, or on immediate stop). If the server
 * crashes mid-Sweep, the buffer survives in localStorage and is offered
 * for recovery on the next page load (auto-retry first; if that fails,
 * a banner offers retry / individual download / discard).
 *
 * Stored shape per key:
 *   {
 *     startedAt: epoch_ms,
 *     bridge: "nai" | "comfyui" | "sd-webui",
 *     param: "scale" | ...,
 *     images: [{ base64, seed, image_format, value, label, mime }, ...]
 *   }
 */
(function () {
  "use strict";

  if (window.SweepBuffer) return; // idempotent

  var STORAGE_PREFIX = "sweep_buffer_";
  var _memory = {};

  function _key(bridgeKey) { return STORAGE_PREFIX + bridgeKey; }

  function _clone(obj) {
    if (!obj) return null;
    return JSON.parse(JSON.stringify(obj));
  }

  function _read(bridgeKey) {
    if (_memory[bridgeKey]) return _memory[bridgeKey];
    try {
      var raw = localStorage.getItem(_key(bridgeKey));
      if (!raw) return null;
      var obj = JSON.parse(raw);
      if (!obj || !Array.isArray(obj.images)) return null;
      return obj;
    } catch (_) { return null; }
  }

  function _write(bridgeKey, obj) {
    _memory[bridgeKey] = obj;
    try { localStorage.setItem(_key(bridgeKey), JSON.stringify(obj)); }
    catch (e) { console.warn("SweepBuffer: localStorage write failed", e); }
    try {
      var bs = window.bridgeStorage;
      if (bs && typeof bs.set === "function") bs.set(_key(bridgeKey), _clone(obj));
    } catch (_) {}
  }

  function _clear(bridgeKey) {
    delete _memory[bridgeKey];
    try { localStorage.removeItem(_key(bridgeKey)); } catch (_) {}
    try {
      var bs = window.bridgeStorage;
      if (bs && typeof bs.remove === "function") bs.remove(_key(bridgeKey));
    } catch (_) {}
  }

  function start(bridgeKey, meta) {
    _write(bridgeKey, {
      startedAt: Date.now(),
      bridge: bridgeKey,
      param: meta && meta.param,
      images: [],
    });
  }

  function add(bridgeKey, item) {
    var buf = _read(bridgeKey);
    if (!buf) {
      buf = { startedAt: Date.now(), bridge: bridgeKey, images: [] };
    }
    buf.images.push(item);
    _write(bridgeKey, buf);
  }

  function size(bridgeKey) {
    var buf = _read(bridgeKey);
    return buf ? buf.images.length : 0;
  }

  function snapshot(bridgeKey) {
    var buf = _read(bridgeKey);
    return buf ? buf.images.slice() : [];
  }

  function clear(bridgeKey) { _clear(bridgeKey); }

  /**
   * POST the current buffer to *saveEndpoint*. On 200 ok=true response,
   * clear the buffer and resolve with `{saved: [...], failed: [...]}`.
   * Rejects on transport error or ok=false.
   */
  function flushToServer(bridgeKey, saveEndpoint) {
    var buf = _read(bridgeKey);
    if (!buf || buf.images.length === 0) {
      return Promise.resolve({ saved: [], failed: [], empty: true });
    }
    var payload = {
      images: buf.images.map(function (it) {
        var out = {
          base64: it.base64,
          seed: it.seed,
          image_format: it.image_format || "png",
        };
        if (it.sweep_meta) out.sweep_meta = it.sweep_meta;
        return out;
      }),
    };
    return fetch(saveEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(payload),
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (!d || !d.ok) {
        var err = (d && d.error) || "save-batch failed";
        throw new Error(err);
      }
      _clear(bridgeKey);
      return {
        saved: d.saved || [],
        failed: d.failed || [],
        saved_items: Array.isArray(d.saved_items) ? d.saved_items : [],
      };
    });
  }

  /**
   * Trigger an individual file download per image (browser save dialog).
   * Used as a manual fallback when the server can't accept the batch.
   */
  function downloadIndividually(bridgeKey, filenamePrefix) {
    var buf = _read(bridgeKey);
    if (!buf) return 0;
    var prefix = filenamePrefix || (bridgeKey + "_sweep");
    var n = 0;
    buf.images.forEach(function (it, i) {
      var fmt = it.image_format || "png";
      var mime = fmt === "webp" ? "image/webp" : (fmt === "jpg" ? "image/jpeg" : "image/png");
      var name = prefix + "_" + String(i + 1).padStart(3, "0") +
        (it.seed != null ? ("_seed" + it.seed) : "") + "." + fmt;
      try {
        var bin = atob(it.base64);
        var arr = new Uint8Array(bin.length);
        for (var j = 0; j < bin.length; j++) arr[j] = bin.charCodeAt(j);
        var blob = new Blob([arr], { type: mime });
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        n++;
      } catch (e) {
        console.warn("SweepBuffer: download failed", e);
      }
    });
    return n;
  }

  /**
   * On page load, check for a leftover buffer. If non-empty, attempt an
   * automatic flush; on failure, render a recovery banner offering retry
   * or individual download or discard.
   */
  function checkRecovery(bridgeKey, saveEndpoint, options) {
    options = options || {};
    var buf = _read(bridgeKey);
    if (!buf || buf.images.length === 0) return;
    var n = buf.images.length;
    var labels = options.labels || {};

    function notify(text, isError) {
      if (window.showToast) window.showToast(text, !!isError);
      else console.log("[SweepBuffer]", text);
    }

    // Try silent auto-recovery first.
    flushToServer(bridgeKey, saveEndpoint).then(function (res) {
      notify((labels.recovered || "Sweep の未保存 N 枚を自動保存しました")
        .replace("N", String(res.saved.length)));
    }).catch(function (e) {
      // Fallback: show a persistent banner.
      _showRecoveryBanner(bridgeKey, saveEndpoint, n, labels, e && e.message);
    });
  }

  function _showRecoveryBanner(bridgeKey, saveEndpoint, n, labels, errMsg) {
    var existing = document.getElementById("sweep-recovery-banner-" + bridgeKey);
    if (existing) existing.remove();
    var div = document.createElement("div");
    div.id = "sweep-recovery-banner-" + bridgeKey;
    div.style.cssText =
      "position:fixed;top:8px;right:8px;z-index:9999;max-width:480px;" +
      "background:#5d2;color:#fff;padding:12px 14px;border-radius:6px;" +
      "box-shadow:0 4px 16px rgba(0,0,0,0.4);font-size:13px;line-height:1.5;";
    var title = document.createElement("div");
    title.style.cssText = "font-weight:bold;margin-bottom:6px;color:#ffeb3b;";
    title.textContent = labels.warningTitle || "⚠ Sweep が中断されました";
    div.appendChild(title);
    var body = document.createElement("div");
    body.textContent = (labels.warningBody ||
      "前回の Sweep で N 枚の画像が未保存です。サーバ側に自動保存を試みましたが失敗しました。手動で対応してください。")
      .replace("N", String(n));
    div.appendChild(body);
    if (errMsg) {
      var err = document.createElement("div");
      err.style.cssText = "font-size:11px;opacity:0.85;margin-top:4px;";
      err.textContent = "(" + errMsg + ")";
      div.appendChild(err);
    }
    var actions = document.createElement("div");
    actions.style.cssText = "margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;";
    var btnRetry = document.createElement("button");
    btnRetry.textContent = labels.retryBtn || "サーバへ再保存";
    btnRetry.style.cssText = "padding:4px 10px;cursor:pointer;";
    btnRetry.addEventListener("click", function () {
      btnRetry.disabled = true;
      flushToServer(bridgeKey, saveEndpoint).then(function (res) {
        div.remove();
        if (window.showToast) window.showToast((labels.recovered || "Sweep の未保存 N 枚を自動保存しました")
          .replace("N", String(res.saved.length)));
      }).catch(function (e) {
        btnRetry.disabled = false;
        if (window.showToast) window.showToast((labels.retryFailed || "再保存失敗") + ": " + e.message, true);
      });
    });
    var btnDl = document.createElement("button");
    btnDl.textContent = labels.downloadBtn || "個別ダウンロード";
    btnDl.style.cssText = "padding:4px 10px;cursor:pointer;";
    btnDl.addEventListener("click", function () {
      var n2 = downloadIndividually(bridgeKey);
      if (window.showToast) window.showToast((labels.downloaded || "N 枚をダウンロードしました")
        .replace("N", String(n2)));
    });
    var btnDiscard = document.createElement("button");
    btnDiscard.textContent = labels.discardBtn || "破棄";
    btnDiscard.style.cssText = "padding:4px 10px;cursor:pointer;";
    btnDiscard.addEventListener("click", function () {
      if (!confirm(labels.discardConfirm || "未保存の Sweep 画像を破棄しますか？")) return;
      _clear(bridgeKey);
      div.remove();
    });
    actions.appendChild(btnRetry);
    actions.appendChild(btnDl);
    actions.appendChild(btnDiscard);
    div.appendChild(actions);
    document.body.appendChild(div);
  }

  window.SweepBuffer = {
    start: start,
    add: add,
    size: size,
    snapshot: snapshot,
    clear: clear,
    flushToServer: flushToServer,
    downloadIndividually: downloadIndividually,
    checkRecovery: checkRecovery,
  };
})();

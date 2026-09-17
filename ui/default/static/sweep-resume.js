/* Sweep "resume" loader — populate the Sweep form on a Bridge page from a
 * pre-existing sweep run identified by a file id.
 *
 * Triggered when the URL contains `?resume_sweep=<file_id>`. Fetches
 * `/api/sweep/info/<file_id>` (returns the sweep meta we embedded as XMP
 * during the original run), then populates the Sweep form inputs for the
 * given bridge. The user clicks Generate when ready — we don't auto-start
 * the run, since they may want to tweak.
 *
 * Usage from each bridge's _script_sweep.html::
 *
 *     window.SweepResume.maybeResume({
 *       bridge: "nai",
 *       prefix: "nab",                    // input id prefix
 *       params: ["scale", "cfg_rescale", ...],   // valid params
 *       sectionId: "nabSweepSection",
 *     });
 */
(function () {
  "use strict";

  // Diagnostic logging is gated on window.__YU_DEBUG__ so regular users
  // don't see [sweep-resume] noise in devtools. Set window.__YU_DEBUG__=true
  // before navigating to a `?resume_sweep=...` URL to enable.
  function _dbg() {
    if (!window.__YU_DEBUG__) return;
    try { console.debug.apply(console, arguments); } catch (_) {}
  }

  function _qs(name) {
    try {
      var sp = new URLSearchParams(window.location.search);
      return sp.get(name);
    } catch (_) { return null; }
  }

  function _stripParam(name) {
    try {
      var url = new URL(window.location.href);
      url.searchParams.delete(name);
      window.history.replaceState({}, "", url.toString());
    } catch (_) {}
  }

  function _set(id, val) {
    var el = document.getElementById(id);
    if (!el) return;
    el.value = String(val);
    try { el.dispatchEvent(new Event("change", { bubbles: true })); } catch (_) {}
    try { el.dispatchEvent(new Event("input", { bubbles: true })); } catch (_) {}
  }

  function _check(id, on) {
    var el = document.getElementById(id);
    if (!el) return;
    el.checked = !!on;
    try { el.dispatchEvent(new Event("change", { bubbles: true })); } catch (_) {}
  }

  function _populateAxis(opts, axis, suffix) {
    var pfx = opts.prefix;
    _dbg("[sweep-resume] populating " + (suffix || "X") + " axis: param=" + axis.param +
      " series.length=" + (Array.isArray(axis.series) ? axis.series.length : "n/a"));
    if (axis.param === "_macros") {
      // Set the per-axis param dropdown to "_macros" and let the bridge's
      // `_xxxApplyMacrosVisibility` swap the editor in. Then restore slot
      // state from the recorded series. ``suffix`` is "" for X, "Y" / "Z"
      // for the others.
      _set(pfx + "Sweep" + suffix + "Param", "_macros");
      var fn = window["_" + pfx + "RestoreSweepMacros"];
      var axisLetter = suffix === "" ? "x" : suffix.toLowerCase();
      if (typeof fn === "function") fn(axis.series || [], axisLetter);
      // Sync the SharedCount input so the visible value matches the restored
      // series length. Functional path uses the derived count from text slots
      // anyway, but keeping the input visually accurate helps the user.
      var seriesLen = Array.isArray(axis.series) ? axis.series.length : 0;
      if (seriesLen > 0) {
        var scId = pfx + "Sweep" + suffix + "MacrosSharedCount";
        var scEl = document.getElementById(scId);
        if (scEl) _set(scId, seriesLen);
      }
      return;
    }
    _set(pfx + "Sweep" + suffix + "Param", axis.param);
    var series = (axis.series || []).filter(function (v) { return typeof v === "number"; });
    if (series.length >= 1) {
      var lo = series[0];
      var hi = series[series.length - 1];
      for (var i = 1; i < series.length; i++) {
        if (series[i] < lo) lo = series[i];
        if (series[i] > hi) hi = series[i];
      }
      _set(pfx + "Sweep" + suffix + "Min", lo);
      _set(pfx + "Sweep" + suffix + "Max", hi);
    }
    _set(pfx + "Sweep" + suffix + "Mode", "count");
    _set(pfx + "Sweep" + suffix + "Count", axis.total || series.length || 6);
  }

  function _populate(opts, meta, runOpts) {
    if (!meta || !Array.isArray(meta.axes) || meta.axes.length === 0) return false;
    runOpts = runOpts || {};
    var pfx = opts.prefix;
    var validParams = new Set(opts.params || []);
    for (var i = 0; i < meta.axes.length; i++) {
      var p = meta.axes[i].param;
      if (p === "_macros") continue;  // handled by per-bridge macros restore
      if (!validParams.has(p)) {
        if (window.showToast) {
          window.showToast(
            (window.tr ? window.tr("sweep.resume_unknown_param", "Sweep: parameter not supported on this bridge: ")
                       : "Sweep: parameter not supported on this bridge: ") + p,
            true,
          );
        }
        return false;
      }
    }

    _check(pfx + "SweepEnabled", true);
    _populateAxis(opts, meta.axes[0], "");

    if (meta.axes.length >= 2) {
      // Y axis (2-axis sweeps and the inner axis of 3-axis sweeps).
      _check(pfx + "SweepYEnabled", true);
      _populateAxis(opts, meta.axes[1], "Y");
      var yEnEl = document.getElementById(pfx + "SweepYEnabled");
      if (yEnEl) {
        try { yEnEl.dispatchEvent(new Event("change", { bubbles: true })); } catch (_) {}
      }
    }

    if (meta.axes.length >= 3) {
      // Z axis (3-axis sweeps). Z requires Y; the bridge's apply helper
      // hard-disables Z when Y is off, so order matters here.
      _check(pfx + "SweepZEnabled", true);
      _populateAxis(opts, meta.axes[2], "Z");
      var zEnEl = document.getElementById(pfx + "SweepZEnabled");
      if (zEnEl) {
        try { zEnEl.dispatchEvent(new Event("change", { bubbles: true })); } catch (_) {}
      }
    }

    // Reuse the same base seed so the regenerated run is comparable, unless
    // the caller explicitly opted out via `?omit_seed=1` (e.g. to shuffle).
    if (!runOpts.omitSeed
        && typeof meta.base_seed === "number" && meta.base_seed >= 0) {
      _set(pfx + "Seed", meta.base_seed);
    }

    // Open the Sweep <details> section so the user immediately sees the
    // populated values.
    var section = document.getElementById(opts.sectionId);
    if (section && section.tagName.toLowerCase() === "details") {
      section.open = true;
      try { section.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (_) {}
    }

    if (window.showToast) {
      window.showToast(
        (window.tr ? window.tr("sweep.resume_populated", "Sweep restored. Click Generate to re-run.")
                   : "Sweep restored. Click Generate to re-run."),
      );
    }
    return true;
  }

  // Determine SD<->NAI conversion direction for cross-bridge sweep resume.
  // ComfyUI shares SD-style syntax (parens with weights), so it groups with
  // SD on the non-NAI side. Returns null when no conversion is needed.
  function _convertDirection(sourceBridge, destBridge) {
    var srcNai = sourceBridge === "nai";
    var dstNai = destBridge === "nai";
    if (srcNai === dstNai) return null;
    return srcNai ? "nai_to_sd" : "sd_to_nai";
  }

  // Collect every string value from `_macros` axis series (which are arrays
  // of `{slot_idx: value}` dicts). These are the per-iteration S/R prompt
  // fragments that need bridge-syntax conversion alongside the main prompt.
  function _collectMacrosStrings(meta) {
    var seen = new Set();
    if (!meta || !Array.isArray(meta.axes)) return [];
    meta.axes.forEach(function (axis) {
      if (!axis || axis.param !== "_macros" || !Array.isArray(axis.series)) return;
      axis.series.forEach(function (entry) {
        if (!entry || typeof entry !== "object") return;
        Object.keys(entry).forEach(function (k) {
          var v = entry[k];
          if (typeof v === "string" && v.length > 0) seen.add(v);
        });
      });
    });
    return Array.from(seen);
  }

  // Replace string values in `_macros` series with their converted form.
  // Mutates meta.axes in place.
  function _applyMacrosConversion(meta, conversionMap) {
    if (!meta || !Array.isArray(meta.axes)) return;
    meta.axes.forEach(function (axis) {
      if (!axis || axis.param !== "_macros" || !Array.isArray(axis.series)) return;
      axis.series = axis.series.map(function (entry) {
        if (!entry || typeof entry !== "object") return entry;
        var out = {};
        Object.keys(entry).forEach(function (k) {
          var v = entry[k];
          if (typeof v === "string" && conversionMap[v] != null) {
            out[k] = conversionMap[v];
          } else {
            out[k] = v;
          }
        });
        return out;
      });
    });
  }

  // Run the batch convert endpoint over every unique macros string in `meta`
  // and rewrite the series in place. Failure falls through silently — the
  // user gets the unconverted fragments rather than a hard error, matching
  // the main-prompt convert fallback in bridge-payload.ts.
  function _convertMacrosForCrossBridge(meta, sourceBridge, destBridge) {
    var direction = _convertDirection(sourceBridge, destBridge);
    if (!direction) return Promise.resolve();
    var strings = _collectMacrosStrings(meta);
    if (strings.length === 0) return Promise.resolve();

    return fetch("/ext/convert/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        items: strings.map(function (s) { return { prompt: s }; }),
        direction: direction,
      }),
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !Array.isArray(d.results)) {
          if (window.showToast) {
            window.showToast(
              (window.tr ? window.tr("sweep.resume_macros_convert_failed",
                "S/R プロンプトの変換に失敗しました。元の文法のまま復元されます")
                : "Failed to convert S/R prompts; restoring with original syntax"),
              true,
            );
          }
          return;
        }
        var map = {};
        d.results.forEach(function (item) {
          if (item && typeof item.original === "string" && typeof item.converted === "string") {
            map[item.original] = item.converted;
          }
        });
        _applyMacrosConversion(meta, map);
      })
      .catch(function () {
        if (window.showToast) {
          window.showToast(
            (window.tr ? window.tr("sweep.resume_macros_convert_failed",
              "S/R プロンプトの変換に失敗しました。元の文法のまま復元されます")
              : "Failed to convert S/R prompts; restoring with original syntax"),
            true,
          );
        }
      });
  }

  // Set a single textarea using the bridge's editor accessor when present,
  // falling back to direct `value` assignment + dispatched input event so
  // syntax highlight / character-count widgets pick up the change.
  function _writeTextarea(pfx, kind, val) {
    if (typeof val !== "string") return false;
    var fnName = "_" + pfx + (kind === "negative" ? "SetNegative" : "SetPrompt");
    var setter = window[fnName];
    if (typeof setter === "function") {
      setter(val);
      return true;
    }
    var elId = pfx + (kind === "negative" ? "Negative" : "Prompt");
    var el = document.getElementById(elId);
    if (el) {
      el.value = val;
      try { el.dispatchEvent(new Event("input", { bubbles: true })); } catch (_) {}
      return true;
    }
    return false;
  }

  // Override the bridge's prompt + negative textareas with the sweep meta's
  // unsubstituted templates. Used by maybeResume so that even if the
  // upstream `bridge_send_prompt` payload was not built with the template
  // (e.g. older sweep image with no prompt_template in XMP, or any other
  // race), the textarea ends up with `$1` / `$x1` placeholders rather than
  // baked-in substituted values. No-op when meta lacks the template attrs.
  //
  // Same-bridge path: feed the raw template directly (no syntax conversion).
  // Cross-bridge path: route the template through `/ext/convert/batch` to
  // translate NAI <-> SD/ComfyUI emphasis / mixing / weakening syntax, since
  // a NAI-syntax template pasted into SD-style bridges (or vice versa) would
  // otherwise be parsed as broken syntax. The macro markers (`$1` / `$x1`
  // etc.) are plain `$` + digits and survive the converter unchanged.
  function _applyPromptTemplate(opts, meta, sourceBridge) {
    if (!meta) return Promise.resolve();
    var pfx = opts.prefix;
    // Treat empty strings as "absent" — older sweeps may have saved
    // negative_template:"" when no negative was used; sending "" through
    // /ext/convert/batch is a wasted round-trip and the converter's empty
    // result would just round-trip back to "".
    var ptRaw = typeof meta.prompt_template === "string" ? meta.prompt_template : null;
    var ntRaw = typeof meta.negative_template === "string" ? meta.negative_template : null;
    var pt = (ptRaw && ptRaw.length > 0) ? ptRaw : null;
    var nt = (ntRaw && ntRaw.length > 0) ? ntRaw : null;
    if (pt == null && nt == null) {
      _dbg("[sweep-resume] no prompt_template in XMP — substituted prompt will remain");
      return Promise.resolve();
    }

    var direction = _convertDirection(sourceBridge || meta.bridge, opts.bridge);
    if (!direction) {
      _dbg("[sweep-resume] applying prompt_template same-bridge (len=" +
        (pt ? pt.length : 0) + ")");
      if (pt != null) _writeTextarea(pfx, "positive", pt);
      if (nt != null) _writeTextarea(pfx, "negative", nt);
      return Promise.resolve();
    }

    // Cross-bridge: send both prompt and negative through one batch call so
    // we make a single round-trip. Empty/missing entries are skipped above.
    var items = [];
    if (pt != null) items.push({ prompt: pt });
    if (nt != null) items.push({ prompt: nt });
    _dbg("[sweep-resume] converting prompt_template cross-bridge (" + direction +
      ", items=" + items.length + ")");
    return fetch("/ext/convert/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: items, direction: direction }),
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        var results = (d && Array.isArray(d.results)) ? d.results : [];
        var byOrig = {};
        results.forEach(function (item) {
          if (item && typeof item.original === "string" && typeof item.converted === "string") {
            byOrig[item.original] = item.converted;
          }
        });
        if (pt != null) {
          var convPos = byOrig[pt];
          if (typeof convPos !== "string") convPos = pt;
          _writeTextarea(pfx, "positive", convPos);
        }
        if (nt != null) {
          var convNeg = byOrig[nt];
          if (typeof convNeg !== "string") convNeg = nt;
          _writeTextarea(pfx, "negative", convNeg);
        }
      })
      .catch(function (e) {
        _dbg("[sweep-resume] template convert failed, using raw:", e);
        if (pt != null) _writeTextarea(pfx, "positive", pt);
        if (nt != null) _writeTextarea(pfx, "negative", nt);
      });
  }

  function maybeResume(opts) {
    if (!opts || !opts.bridge || !opts.prefix) return;
    var fileId = _qs("resume_sweep");
    if (!fileId) return;
    // Cross-bridge mode: prompt has been pre-loaded via the
    // `bridge_send_prompt` localStorage protocol from the Sweep View
    // page. Skip the source-bridge mismatch check and force seed omit
    // (SD/ComfyUI seeds aren't compatible across bridges).
    var crossBridge = _qs("cross") === "1";
    var omitSeed = crossBridge || _qs("omit_seed") === "1";
    _stripParam("resume_sweep");
    _stripParam("omit_seed");
    _stripParam("cross");

    fetch("/api/sweep/info/" + encodeURIComponent(fileId), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.ok || !d.meta) {
          if (window.showToast) {
            window.showToast(
              (window.tr ? window.tr("sweep.resume_not_found", "No sweep metadata found on that file.")
                         : "No sweep metadata found on that file."),
              true,
            );
          }
          return;
        }
        if (!crossBridge && d.meta.bridge && d.meta.bridge !== opts.bridge) {
          if (window.showToast) {
            window.showToast(
              (window.tr ? window.tr("sweep.resume_wrong_bridge", "Sweep was made on a different bridge: ")
                         : "Sweep was made on a different bridge: ") + d.meta.bridge,
              true,
            );
          }
          return;
        }

        // Cross-bridge: route macros (S/R) string fragments through the same
        // NAI<->SD/ComfyUI converter that `bridge_send_prompt` used for the
        // main prompt, so re-runs across bridges don't leave the per-axis
        // prompt syntax in the source bridge's dialect.
        var convertPromise = (crossBridge && d.meta.bridge)
          ? _convertMacrosForCrossBridge(d.meta, d.meta.bridge, opts.bridge)
          : Promise.resolve();
        return convertPromise.then(function () {
          _populate(opts, d.meta, { omitSeed: omitSeed });
          // Defense-in-depth: the same-bridge re-run flow already overrides
          // the prompt textarea via `bridge_send_prompt`, but we also apply
          // the unsubstituted template directly here so any race / cross-
          // bridge flow / XMP-edge case still gets the `$1` / `$x1` markers
          // back into the textarea instead of the baked-in substituted text.
          // For cross-bridge, _applyPromptTemplate routes the template through
          // /ext/convert/batch so NAI<->SD/ComfyUI syntax differences are
          // translated (mirrors what `bridge_send_prompt` does for the main
          // prompt — without it, cross-bridge re-runs were falling back to
          // BridgeLastParams.restore() because the substituted prompt path
          // through buildPromptPayload sometimes emptied the payload).
          return _applyPromptTemplate(opts, d.meta, d.meta.bridge);
        });
      })
      .catch(function (e) {
        if (window.showToast) {
          window.showToast("Sweep resume failed: " + ((e && e.message) || String(e)), true);
        }
      });
  }

  window.SweepResume = { maybeResume: maybeResume };
})();

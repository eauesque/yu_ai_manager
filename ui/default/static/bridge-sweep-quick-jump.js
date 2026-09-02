// bridge-sweep-quick-jump.js
// Common module shared by ComfyUI / NAI / SD-WebUI bridges to expose
// "Open Sweep page" + "history" UI and to keep a localStorage history.
//
// Schema (localStorage key "yu_ai_manager.bridgeSweepHistory"):
// { version: 1, entries: [
//     { id, bridge, started_at, status, first_saved_file_id, axes_summary }
//   ] }
(function () {
  "use strict";

  const KEY = "yu_ai_manager.bridgeSweepHistory";
  const LIST_COUNT_KEY = "yu_ai_manager.bridgeSweepHistoryListCount";
  const SCHEMA_VERSION = 1;
  // Storage cap. The popover slices its own display, so this can grow
  // without making the popover huge. The dedicated /sweep page renders a
  // user-selectable count (10/50/100/500) over the full stored history.
  const MAX_ENTRIES = 500;
  const POPOVER_DISPLAY = 20;
  const LIST_COUNT_OPTIONS = [10, 50, 100, 500];
  const LIST_COUNT_DEFAULT = 50;
  const STALE_UNKNOWN_SEC = 30 * 60;       // 30 min → "unknown" UI
  const STALE_FAILED_SEC = 24 * 60 * 60;   // 24 h → write status=failed

  function _now() { return Math.floor(Date.now() / 1000); }

  function _readRaw() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return { version: SCHEMA_VERSION, entries: [] };
      const parsed = JSON.parse(raw);
      if (!parsed || parsed.version !== SCHEMA_VERSION || !Array.isArray(parsed.entries)) {
        // forward-compat: silent reset on schema mismatch
        return { version: SCHEMA_VERSION, entries: [] };
      }
      return parsed;
    } catch (_e) {
      return { version: SCHEMA_VERSION, entries: [] };
    }
  }

  function _writeRaw(entries) {
    try {
      localStorage.setItem(KEY, JSON.stringify({
        version: SCHEMA_VERSION,
        entries: entries.slice(0, MAX_ENTRIES),
      }));
    } catch (_e) {
      // Quota / private mode: silent. Sweep itself must not be blocked.
    }
  }

  // mutator: (entries) => entries
  // Re-reads localStorage right before write to avoid losing other tabs' updates.
  function _mutate(mutator) {
    const cur = _readRaw().entries;
    const next = mutator(cur.slice());
    _writeRaw(next);
  }

  function _staleRescue(entry) {
    if (entry.status !== "running") return entry;
    const age = _now() - (entry.started_at || 0);
    if (age > STALE_FAILED_SEC) return Object.assign({}, entry, { status: "failed" });
    return entry;
  }

  function _summarize(axes) {
    if (!Array.isArray(axes) || axes.length === 0) return "";
    const head = axes.slice(0, 2).map((a) =>
      `${a.param}×${(a.total != null ? a.total : (Array.isArray(a.series) ? a.series.length : 0))}`
    ).join(" / ");
    if (axes.length <= 2) return head;
    return `${head} / +${axes.length - 2}`;
  }

  // Cap stored prompt/negative templates so 500 entries stay within
  // localStorage budget even when prompts are long.
  const TEMPLATE_MAX_LEN = 4000;
  function _capStr(s) {
    if (typeof s !== "string") return undefined;
    if (s.length <= TEMPLATE_MAX_LEN) return s;
    return s.slice(0, TEMPLATE_MAX_LEN);
  }

  // Strip per-axis details we don't need for filtering. Keep `param` only.
  function _axesParams(axes) {
    if (!Array.isArray(axes)) return [];
    return axes.map((a) => (a && typeof a.param === "string") ? a.param : "")
      .filter((p) => p.length > 0);
  }

  function _numOrUndef(v) {
    if (typeof v === "number" && Number.isFinite(v)) return v;
    return undefined;
  }

  function registerStart(meta) {
    if (!meta || !meta.id || !meta.bridge) return;
    const entry = {
      id: meta.id,
      bridge: meta.bridge,
      started_at: _now(),
      status: "running",
      first_saved_file_id: null,
      axes_summary: _summarize(meta.axes || []),
      // Extra fields used by the inline list filter on /sweep page.
      // All optional — missing fields just disable the matching checkbox.
      axes_params: _axesParams(meta.axes || []),
      prompt_template: _capStr(meta.prompt_template),
      negative_template: _capStr(meta.negative_template),
      checkpoint: typeof meta.checkpoint === "string" ? meta.checkpoint : undefined,
      vae: typeof meta.vae === "string" ? meta.vae : undefined,
      sampler: typeof meta.sampler === "string" ? meta.sampler : undefined,
      width: _numOrUndef(meta.width),
      height: _numOrUndef(meta.height),
      steps: _numOrUndef(meta.steps),
      cfg: _numOrUndef(meta.cfg),
      base_seed: _numOrUndef(meta.base_seed),
    };
    _mutate((entries) => {
      const filtered = entries.filter((e) => e.id !== entry.id);
      filtered.unshift(entry);
      return filtered.map(_staleRescue);
    });
  }

  function registerFirstSavedFileId(sweepId, fileId) {
    if (!sweepId || typeof fileId !== "number") return;
    _mutate((entries) => entries.map((e) =>
      e.id === sweepId && e.first_saved_file_id == null
        ? Object.assign({}, e, { first_saved_file_id: fileId })
        : e
    ));
  }

  function _markStatus(sweepId, status) {
    _mutate((entries) => entries.map((e) =>
      e.id === sweepId ? Object.assign({}, e, { status }) : e
    ));
  }
  function markCompleted(sweepId) { _markStatus(sweepId, "completed"); }
  function markFailed(sweepId) { _markStatus(sweepId, "failed"); }
  function markCancelled(sweepId) { _markStatus(sweepId, "cancelled"); }

  function buildUrl(sweepId, fileId) {
    if (!sweepId || typeof fileId !== "number") return null;
    return `/sweep/${encodeURIComponent(sweepId)}?from=${fileId}`;
  }

  function openInNewTab(sweepId, fileId) {
    const url = buildUrl(sweepId, fileId);
    if (!url) return false;
    window.open(url, "_blank", "noopener");
    return true;
  }

  function getHistory() {
    return _readRaw().entries.map(_staleRescue);
  }

  function clearHistory() { _writeRaw([]); }

  function _statusClass(entry) {
    if (entry.status === "running") {
      const age = _now() - (entry.started_at || 0);
      if (age > STALE_UNKNOWN_SEC) return "unknown";
      return "running";
    }
    return entry.status;
  }

  function _formatTime(unixSec) {
    const d = new Date(unixSec * 1000);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  }

  // Compact date+time for the popover: "yy/mm/dd HH:MM"
  // Keeps the timestamp readable without overflowing the narrow popover column.
  function _formatShortDate(unixSec) {
    const d = new Date(unixSec * 1000);
    const yy = String(d.getFullYear()).slice(2);
    const mo = String(d.getMonth() + 1).padStart(2, "0");
    const da = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${yy}/${mo}/${da} ${hh}:${mm}`;
  }

  // Bridge pages load the runtime tr() shim which consults `ui_runtime.*.json`,
  // not the main `i18n/<lang>.json` flat dict where `bridge.sweep.*` keys live.
  // Cache the flat dict by listening for the `i18n:changed` event that
  // core-shared.ts::applyTranslations dispatches, and consult it first.
  var _flatI18n = null;
  document.addEventListener("i18n:changed", function (ev) {
    if (ev && ev.detail && ev.detail.dict) _flatI18n = ev.detail.dict;
  });

  function _tr(key, fallback) {
    if (_flatI18n && Object.prototype.hasOwnProperty.call(_flatI18n, key)) {
      var v = _flatI18n[key];
      if (v) return v;
    }
    if (typeof window.tr === "function") {
      var t = window.tr(key, fallback);
      if (t && t !== key) return t;
    }
    return fallback;
  }

  function renderHistoryPopover(anchorEl) {
    if (!anchorEl) return null;
    let pop = document.getElementById("bsqj-popover");
    if (!pop) {
      pop = document.createElement("div");
      pop.id = "bsqj-popover";
      pop.className = "bsqj-popover";
      pop.setAttribute("role", "dialog");
      pop.setAttribute("aria-label", _tr("bridge.sweep.history", "履歴"));
      document.body.appendChild(pop);
    }

    function _redraw() {
      const entries = getHistory().slice(0, POPOVER_DISPLAY);
      while (pop.firstChild) pop.removeChild(pop.firstChild);
      const header = document.createElement("div");
      header.className = "bsqj-popover-header";
      const title = document.createElement("span");
      title.textContent = _tr("bridge.sweep.history", "履歴");
      header.appendChild(title);
      if (entries.length > 0) {
        const clearBtn = document.createElement("button");
        clearBtn.type = "button";
        clearBtn.className = "bsqj-clear-all";
        clearBtn.textContent = _tr("bridge.sweep.historyClearAll", "すべてクリア");
        clearBtn.addEventListener("click", async () => {
          const msg = _tr("bridge.sweep.historyClearConfirm", "履歴をすべて削除しますか？");
          const ok = window.atelierConfirm
            ? await window.atelierConfirm(msg)
            : await window.customConfirm(msg, { danger: true });
          if (ok) {
            clearHistory();
            _redraw();
          }
        });
        header.appendChild(clearBtn);
      }
      pop.appendChild(header);
      if (entries.length === 0) {
        const empty = document.createElement("div");
        empty.className = "bsqj-empty";
        empty.textContent = _tr(
          "bridge.sweep.historyEmpty",
          "履歴はまだありません。Sweep を実行すると追加されます。",
        );
        pop.appendChild(empty);
        return;
      }
      for (const e of entries) {
        const row = document.createElement("div");
        row.className = "bsqj-row";
        const cls = _statusClass(e);
        const status = document.createElement("span");
        status.className = `bsqj-status bsqj-status-${cls}`;
        const statusKey = `bridge.sweep.status${cls.charAt(0).toUpperCase()}${cls.slice(1)}`;
        status.setAttribute("aria-label", _tr(statusKey, cls));
        row.appendChild(status);
        const meta = document.createElement("span");
        meta.className = "bsqj-meta";
        const bridgeLabel = e.bridge.toUpperCase();
        meta.textContent = `${_formatShortDate(e.started_at)} · ${bridgeLabel} · ${e.axes_summary || "—"}`;
        row.appendChild(meta);
        const enabled = typeof e.first_saved_file_id === "number";
        row.setAttribute("role", "link");
        row.setAttribute("tabindex", enabled ? "0" : "-1");
        row.setAttribute("aria-disabled", enabled ? "false" : "true");
        if (!enabled) {
          row.title = _tr("bridge.sweep.notSaved", "画像が保存されていません");
        }
        const handle = () => {
          if (!enabled) return;
          openInNewTab(e.id, e.first_saved_file_id);
          _hide();
        };
        row.addEventListener("click", handle);
        row.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") handle();
        });
        pop.appendChild(row);
      }
    }

    function _position() {
      const rect = anchorEl.getBoundingClientRect();
      pop.style.top = `${window.scrollY + rect.bottom + 4}px`;
      pop.style.left = `${window.scrollX + Math.max(8, rect.right - 320)}px`;
    }

    function _hide() {
      pop.hidden = true;
      document.removeEventListener("click", _onDocClick, true);
      document.removeEventListener("keydown", _onKey, true);
      document.removeEventListener("bridge-sweep-history-changed", _redraw);
    }

    function _onDocClick(ev) {
      if (pop.contains(ev.target) || ev.target === anchorEl) return;
      _hide();
    }

    function _onKey(ev) { if (ev.key === "Escape") _hide(); }

    _redraw();
    _position();
    pop.hidden = false;
    document.addEventListener("click", _onDocClick, true);
    document.addEventListener("keydown", _onKey, true);
    document.addEventListener("bridge-sweep-history-changed", _redraw);
    return pop;
  }

  function _readListCount() {
    try {
      const raw = parseInt(localStorage.getItem(LIST_COUNT_KEY) || "", 10);
      if (LIST_COUNT_OPTIONS.indexOf(raw) >= 0) return raw;
    } catch (_e) { /* no-op */ }
    return LIST_COUNT_DEFAULT;
  }

  function _writeListCount(n) {
    try { localStorage.setItem(LIST_COUNT_KEY, String(n)); } catch (_e) { /* no-op */ }
  }

  function _formatDate(unixSec) {
    const d = new Date(unixSec * 1000);
    const y = d.getFullYear();
    const mo = String(d.getMonth() + 1).padStart(2, "0");
    const da = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${y}-${mo}-${da} ${hh}:${mm}`;
  }

  // Filter fields. Two flavours:
  //   - kind="match-exact": checkbox + getter; entry passes if entry's
  //     value strictly equals the reference's value (skipped if reference
  //     has no value — checkbox is then disabled).
  //   - kind="match-numeric": same but numeric, with a tolerance pull-down
  //     ("=", "±5%", "±10%", "±20%").
  //   - kind="constraint-bool": independent boolean (e.g. "completed only").
  //   - kind="constraint-select": independent select (e.g. axis count, date).
  // mode controls visibility: "simple" → always visible, "full" → only
  // when the user toggles to full mode.
  const FILTER_FIELDS = [
    // --- Group: basic (match) ---
    { key: "bridge", group: "basic", kind: "match-exact", mode: "simple",
      labelKey: "bridge.sweep.filterBridge", labelDefault: "プラットフォーム",
      get: (e) => e.bridge || "" },
    { key: "checkpoint", group: "basic", kind: "match-exact", mode: "simple",
      labelKey: "bridge.sweep.filterCheckpoint", labelDefault: "チェックポイント",
      get: (e) => e.checkpoint || "" },
    { key: "vae", group: "basic", kind: "match-exact", mode: "simple",
      labelKey: "bridge.sweep.filterVae", labelDefault: "VAE",
      get: (e) => e.vae || "" },
    // --- Group: prompt (match) ---
    { key: "positive", group: "prompt", kind: "match-exact", mode: "simple",
      labelKey: "bridge.sweep.filterPositive", labelDefault: "ポジティブ",
      get: (e) => e.prompt_template || "" },
    { key: "negative", group: "prompt", kind: "match-exact", mode: "simple",
      labelKey: "bridge.sweep.filterNegative", labelDefault: "ネガティブ",
      get: (e) => e.negative_template || "" },
    // --- Group: axes (match) ---
    { key: "axisX", group: "axes", kind: "match-exact", mode: "simple",
      labelKey: "bridge.sweep.filterAxisX", labelDefault: "X軸",
      get: (e) => (e.axes_params && e.axes_params[0]) || "" },
    { key: "axisY", group: "axes", kind: "match-exact", mode: "simple",
      labelKey: "bridge.sweep.filterAxisY", labelDefault: "Y軸",
      get: (e) => (e.axes_params && e.axes_params[1]) || "" },
    { key: "axisZ", group: "axes", kind: "match-exact", mode: "simple",
      labelKey: "bridge.sweep.filterAxisZ", labelDefault: "Z軸",
      get: (e) => (e.axes_params && e.axes_params[2]) || "" },
    // --- Group: numeric (match) ---
    { key: "sampler", group: "numeric", kind: "match-exact", mode: "simple",
      labelKey: "bridge.sweep.filterSampler", labelDefault: "サンプラー",
      get: (e) => e.sampler || "" },
    { key: "resolution", group: "numeric", kind: "match-exact", mode: "simple",
      labelKey: "bridge.sweep.filterResolution", labelDefault: "解像度",
      get: (e) => (typeof e.width === "number" && typeof e.height === "number")
        ? `${e.width}x${e.height}` : "" },
    { key: "steps", group: "numeric", kind: "match-numeric", mode: "simple",
      labelKey: "bridge.sweep.filterSteps", labelDefault: "ステップ数",
      get: (e) => (typeof e.steps === "number") ? e.steps : null },
    { key: "cfg", group: "numeric", kind: "match-numeric", mode: "simple",
      labelKey: "bridge.sweep.filterCfg", labelDefault: "CFG",
      get: (e) => (typeof e.cfg === "number") ? e.cfg : null },
    { key: "baseSeed", group: "numeric", kind: "match-exact", mode: "full",
      labelKey: "bridge.sweep.filterBaseSeed", labelDefault: "Base seed",
      get: (e) => (typeof e.base_seed === "number") ? String(e.base_seed) : "" },
    // --- Group: state (constraint - independent of reference) ---
    { key: "completedOnly", group: "state", kind: "constraint-bool", mode: "simple",
      labelKey: "bridge.sweep.filterCompletedOnly", labelDefault: "完了のみ",
      pass: (e) => e.status === "completed" },
    { key: "savedOnly", group: "state", kind: "constraint-bool", mode: "simple",
      labelKey: "bridge.sweep.filterSavedOnly", labelDefault: "保存済みのみ",
      pass: (e) => typeof e.first_saved_file_id === "number" },
    { key: "axisCount", group: "state", kind: "constraint-select", mode: "full",
      labelKey: "bridge.sweep.filterAxisCount", labelDefault: "軸数",
      options: [
        { value: "all", labelKey: "bridge.sweep.filterAxisCountAll", labelDefault: "すべて" },
        { value: "1", labelKey: "bridge.sweep.filterAxisCount1", labelDefault: "1軸" },
        { value: "2", labelKey: "bridge.sweep.filterAxisCount2", labelDefault: "2軸" },
        { value: "3", labelKey: "bridge.sweep.filterAxisCount3", labelDefault: "3軸" },
      ],
      pass: (e, val) => {
        if (val === "all") return true;
        const n = (e.axes_params || []).length;
        return String(n) === val;
      } },
    { key: "dateRange", group: "state", kind: "constraint-select", mode: "full",
      labelKey: "bridge.sweep.filterDateRange", labelDefault: "期間",
      options: [
        { value: "all", labelKey: "bridge.sweep.filterDateRangeAll", labelDefault: "全期間" },
        { value: "today", labelKey: "bridge.sweep.filterDateRangeToday", labelDefault: "今日" },
        { value: "week", labelKey: "bridge.sweep.filterDateRangeWeek", labelDefault: "1週間" },
        { value: "month", labelKey: "bridge.sweep.filterDateRangeMonth", labelDefault: "1ヶ月" },
      ],
      pass: (e, val) => {
        if (val === "all") return true;
        const now = _now();
        const age = now - (e.started_at || 0);
        if (val === "today") return age <= 24 * 60 * 60;
        if (val === "week") return age <= 7 * 24 * 60 * 60;
        if (val === "month") return age <= 30 * 24 * 60 * 60;
        return true;
      } },
  ];

  const TOLERANCE_OPTIONS = [
    { value: "exact", labelKey: "bridge.sweep.tolExact", labelDefault: "=" },
    { value: "5", labelKey: "bridge.sweep.tol5", labelDefault: "±5%" },
    { value: "10", labelKey: "bridge.sweep.tol10", labelDefault: "±10%" },
    { value: "20", labelKey: "bridge.sweep.tol20", labelDefault: "±20%" },
  ];

  function _numericMatches(refVal, entryVal, tol) {
    if (typeof refVal !== "number" || typeof entryVal !== "number") return false;
    if (tol === "exact") return refVal === entryVal;
    const pct = parseFloat(tol);
    if (!Number.isFinite(pct) || pct <= 0) return refVal === entryVal;
    const eps = Math.abs(refVal) * (pct / 100);
    return Math.abs(refVal - entryVal) <= eps;
  }

  const FILTER_MODE_KEY = "yu_ai_manager.bridgeSweepHistoryFilterMode";
  function _readFilterMode() {
    try {
      const v = localStorage.getItem(FILTER_MODE_KEY);
      if (v === "full" || v === "simple") return v;
    } catch (_e) { /* no-op */ }
    return "simple";
  }
  function _writeFilterMode(m) {
    try { localStorage.setItem(FILTER_MODE_KEY, m); } catch (_e) { /* no-op */ }
  }

  // Persist filter selections (match / tolerance / constraint) so navigating
  // from one sweep to another via the history list preserves the filter
  // (e.g., user filtered to "same checkpoint", clicks a row, lands on the
  // /sweep/<other> page → filter chips should still be checked).
  // Keyed globally (not per ref) because the chips describe field equality
  // against the current ref, which makes sense for any ref.
  const FILTER_STATE_KEY = "yu_ai_manager.bridgeSweepHistoryFilterState";
  function _readFilterState() {
    try {
      const v = localStorage.getItem(FILTER_STATE_KEY);
      if (!v) return null;
      const j = JSON.parse(v);
      if (j && typeof j === "object" && !Array.isArray(j)) return j;
    } catch (_e) { /* no-op */ }
    return null;
  }
  function _writeFilterState(state) {
    try { localStorage.setItem(FILTER_STATE_KEY, JSON.stringify(state)); }
    catch (_e) { /* no-op */ }
  }

  // Render a self-contained history list into `container`. Includes a
  // count selector (10/50/100/500), a Clear All action, and live refresh
  // when other tabs/pages mutate history. Used by the dedicated /sweep
  // page to let users browse past sweeps. `options.referenceSweepId`
  // (optional) enables the "match against this sweep" filter row.
  function renderHistoryList(container, options) {
    if (!container) return null;
    while (container.firstChild) container.removeChild(container.firstChild);
    container.classList.add("bsqj-list");
    const opts = options || {};
    const referenceSweepId = opts.referenceSweepId || null;

    const toolbar = document.createElement("div");
    toolbar.className = "bsqj-list-toolbar";
    const title = document.createElement("span");
    title.className = "bsqj-list-title";
    title.textContent = _tr("bridge.sweep.history", "履歴");
    toolbar.appendChild(title);

    const countLabel = document.createElement("label");
    countLabel.className = "bsqj-list-count-label";
    const countText = document.createElement("span");
    countText.textContent = _tr("bridge.sweep.historyShowCount", "表示件数:");
    countLabel.appendChild(countText);
    const select = document.createElement("select");
    select.className = "bsqj-list-count-select";
    let currentCount = _readListCount();
    for (const n of LIST_COUNT_OPTIONS) {
      const opt = document.createElement("option");
      opt.value = String(n);
      opt.textContent = String(n);
      if (n === currentCount) opt.selected = true;
      select.appendChild(opt);
    }
    select.addEventListener("change", () => {
      const n = parseInt(select.value, 10);
      if (LIST_COUNT_OPTIONS.indexOf(n) >= 0) {
        currentCount = n;
        _writeListCount(n);
        _redraw();
      }
    });
    countLabel.appendChild(select);
    toolbar.appendChild(countLabel);

    const clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "bsqj-clear-all";
    clearBtn.textContent = _tr("bridge.sweep.historyClearAll", "すべてクリア");
    clearBtn.addEventListener("click", async () => {
      const msg = _tr("bridge.sweep.historyClearConfirm", "履歴をすべて削除しますか？");
      const ok = window.atelierConfirm
        ? await window.atelierConfirm(msg)
        : await window.customConfirm(msg, { danger: true });
      if (ok) {
        clearHistory();
        _redraw();
      }
    });
    toolbar.appendChild(clearBtn);
    container.appendChild(toolbar);

    // Filter state — persisted to localStorage so navigation between sweeps
    // (clicking a history row to jump to another /sweep/<id>) preserves the
    // user's filter selections.
    //   match[<key>]      → boolean checked
    //   tolerance[<key>]  → string (e.g. "exact", "5", "10", "20")
    //   constraint[<key>] → boolean (for bool) or string (for select)
    let filterMode = _readFilterMode();
    const matchState = Object.create(null);
    const toleranceState = Object.create(null);
    const constraintState = Object.create(null);
    // initialize default tolerance / constraint values
    for (const def of FILTER_FIELDS) {
      if (def.kind === "match-numeric") toleranceState[def.key] = "exact";
      if (def.kind === "constraint-select" && def.options && def.options[0]) {
        constraintState[def.key] = def.options[0].value;
      }
    }
    // Overlay persisted state (only known keys, validated values).
    const _persisted = _readFilterState();
    if (_persisted) {
      for (const def of FILTER_FIELDS) {
        if (def.kind === "match-exact" || def.kind === "match-numeric") {
          if (_persisted.match && typeof _persisted.match[def.key] === "boolean") {
            matchState[def.key] = _persisted.match[def.key];
          }
        }
        if (def.kind === "match-numeric") {
          const t = _persisted.tolerance && _persisted.tolerance[def.key];
          if (TOLERANCE_OPTIONS.some((o) => o.value === t)) {
            toleranceState[def.key] = t;
          }
        }
        if (def.kind === "constraint-bool") {
          if (_persisted.constraint
              && typeof _persisted.constraint[def.key] === "boolean") {
            constraintState[def.key] = _persisted.constraint[def.key];
          }
        }
        if (def.kind === "constraint-select") {
          const v = _persisted.constraint && _persisted.constraint[def.key];
          if (def.options && def.options.some((o) => o.value === v)) {
            constraintState[def.key] = v;
          }
        }
      }
    }
    function _persistFilterState() {
      _writeFilterState({
        match: Object.assign({}, matchState),
        tolerance: Object.assign({}, toleranceState),
        constraint: Object.assign({}, constraintState),
      });
    }

    function _refEntry() {
      if (!referenceSweepId) return null;
      const local = getHistory();
      for (const e of local) if (e.id === referenceSweepId) return e;
      // Fall back to DB-fetched entries: a sweep run in another browser /
      // session won't be in this localStorage, but /api/sweeps/history
      // returns the same field shape (bridge, checkpoint, axes_params, ...).
      // Note: _entries is [] until _fetchHistory() completes — the initial
      // _buildFilterUI() call sees no DB ref; _renderEntries() rebuilds the
      // filter UI once entries arrive (see hasRef dataset check).
      for (const e of _entries) if (e.id === referenceSweepId) return e;
      return null;
    }

    let filterStatus = null;
    let filterContainer = null;

    const body = document.createElement("div");
    body.className = "bsqj-list-body";
    container.appendChild(body);

    function _buildFilterUI() {
      // Remove old filter container if any.
      if (filterContainer && filterContainer.parentNode) {
        filterContainer.parentNode.removeChild(filterContainer);
      }
      filterContainer = document.createElement("div");
      filterContainer.className = "bsqj-list-filter";
      if (!referenceSweepId) { return; }

      const ref = _refEntry();
      filterContainer.dataset.hasRef = ref ? "true" : "false";

      // Header row: lead text + select-all/clear-all + mode toggle
      const head = document.createElement("div");
      head.className = "bsqj-list-filter-head";
      const lead = document.createElement("span");
      lead.className = "bsqj-list-filter-lead";
      lead.textContent = _tr("bridge.sweep.filterMatch", "同条件で絞り込み:");
      head.appendChild(lead);

      const selectAllBtn = document.createElement("button");
      selectAllBtn.type = "button";
      selectAllBtn.className = "bsqj-list-filter-btn";
      selectAllBtn.textContent = _tr("bridge.sweep.filterSelectAll", "すべて選択");
      selectAllBtn.addEventListener("click", () => {
        for (const def of FILTER_FIELDS) {
          if (def.kind !== "match-exact" && def.kind !== "match-numeric") continue;
          if (def.mode === "full" && filterMode !== "full") continue;
          // skip if reference has no value for this field
          let hasRef = false;
          if (def.kind === "match-numeric") {
            hasRef = ref && typeof def.get(ref) === "number";
          } else {
            const v = ref ? def.get(ref) : "";
            hasRef = !!(v && v.length > 0);
          }
          if (hasRef) matchState[def.key] = true;
        }
        _persistFilterState();
        _buildFilterUI();
        _redraw();
      });
      head.appendChild(selectAllBtn);

      const clearSelBtn = document.createElement("button");
      clearSelBtn.type = "button";
      clearSelBtn.className = "bsqj-list-filter-btn";
      clearSelBtn.textContent = _tr("bridge.sweep.filterClearAll", "すべて解除");
      clearSelBtn.addEventListener("click", () => {
        for (const k of Object.keys(matchState)) matchState[k] = false;
        for (const def of FILTER_FIELDS) {
          if (def.kind === "constraint-bool") constraintState[def.key] = false;
          if (def.kind === "constraint-select" && def.options && def.options[0]) {
            constraintState[def.key] = def.options[0].value;
          }
        }
        _persistFilterState();
        _buildFilterUI();
        _redraw();
      });
      head.appendChild(clearSelBtn);

      const modeBtn = document.createElement("button");
      modeBtn.type = "button";
      modeBtn.className = "bsqj-list-filter-btn bsqj-list-filter-mode";
      const _modeLabel = () => filterMode === "full"
        ? _tr("bridge.sweep.filterModeSimpleSwitch", "簡易表示に切替")
        : _tr("bridge.sweep.filterModeFullSwitch", "詳細フィルタを表示");
      modeBtn.textContent = _modeLabel();
      modeBtn.addEventListener("click", () => {
        filterMode = filterMode === "full" ? "simple" : "full";
        _writeFilterMode(filterMode);
        _buildFilterUI();
        _redraw();
      });
      head.appendChild(modeBtn);

      filterStatus = document.createElement("span");
      filterStatus.className = "bsqj-list-filter-status";
      head.appendChild(filterStatus);
      filterContainer.appendChild(head);

      // Group rows
      const groups = ["basic", "prompt", "axes", "numeric", "state"];
      const groupTitles = {
        basic: _tr("bridge.sweep.filterGroupBasic", "基本"),
        prompt: _tr("bridge.sweep.filterGroupPrompt", "プロンプト"),
        axes: _tr("bridge.sweep.filterGroupAxes", "軸"),
        numeric: _tr("bridge.sweep.filterGroupNumeric", "数値"),
        state: _tr("bridge.sweep.filterGroupState", "状態"),
      };
      for (const grp of groups) {
        const fields = FILTER_FIELDS.filter((d) =>
          d.group === grp && (d.mode === "simple" || filterMode === "full"));
        if (fields.length === 0) continue;
        const row = document.createElement("div");
        row.className = "bsqj-list-filter-group";
        const gtitle = document.createElement("span");
        gtitle.className = "bsqj-list-filter-grp-title";
        gtitle.textContent = groupTitles[grp];
        row.appendChild(gtitle);
        for (const def of fields) {
          row.appendChild(_buildChip(def, ref));
        }
        filterContainer.appendChild(row);
      }
      // Insert before body if body already attached.
      if (body && body.parentNode === container) {
        container.insertBefore(filterContainer, body);
      } else {
        container.appendChild(filterContainer);
      }
    }

    function _buildChip(def, ref) {
      const chip = document.createElement("label");
      chip.className = "bsqj-list-filter-chip";
      chip.dataset.kind = def.kind;

      if (def.kind === "match-exact" || def.kind === "match-numeric") {
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = !!matchState[def.key];
        let hasRef;
        if (def.kind === "match-numeric") {
          hasRef = ref && typeof def.get(ref) === "number";
        } else {
          const v = ref ? def.get(ref) : "";
          hasRef = !!(v && v.length > 0);
        }
        if (!hasRef) {
          cb.disabled = true;
          chip.dataset.disabled = "true";
          chip.title = _tr("bridge.sweep.filterUnavailable",
            "この sweep にはこの情報がないので比較できません");
        }
        cb.addEventListener("change", () => {
          matchState[def.key] = cb.checked;
          _persistFilterState();
          _redraw();
        });
        chip.appendChild(cb);
        const txt = document.createElement("span");
        txt.textContent = _tr(def.labelKey, def.labelDefault);
        chip.appendChild(txt);
        if (def.kind === "match-numeric") {
          const sel = document.createElement("select");
          sel.className = "bsqj-list-filter-tol";
          sel.disabled = !hasRef;
          for (const o of TOLERANCE_OPTIONS) {
            const opt = document.createElement("option");
            opt.value = o.value;
            opt.textContent = _tr(o.labelKey, o.labelDefault);
            if (o.value === toleranceState[def.key]) opt.selected = true;
            sel.appendChild(opt);
          }
          sel.addEventListener("change", () => {
            toleranceState[def.key] = sel.value;
            _persistFilterState();
            _redraw();
          });
          chip.appendChild(sel);
        }
      } else if (def.kind === "constraint-bool") {
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = !!constraintState[def.key];
        cb.addEventListener("change", () => {
          constraintState[def.key] = cb.checked;
          _persistFilterState();
          _redraw();
        });
        chip.appendChild(cb);
        const txt = document.createElement("span");
        txt.textContent = _tr(def.labelKey, def.labelDefault);
        chip.appendChild(txt);
      } else if (def.kind === "constraint-select") {
        const txt = document.createElement("span");
        txt.textContent = _tr(def.labelKey, def.labelDefault);
        chip.appendChild(txt);
        const sel = document.createElement("select");
        sel.className = "bsqj-list-filter-sel";
        for (const o of def.options) {
          const opt = document.createElement("option");
          opt.value = o.value;
          opt.textContent = _tr(o.labelKey, o.labelDefault);
          if (o.value === constraintState[def.key]) opt.selected = true;
          sel.appendChild(opt);
        }
        sel.addEventListener("change", () => {
          constraintState[def.key] = sel.value;
          _persistFilterState();
          _redraw();
        });
        chip.appendChild(sel);
      }
      return chip;
    }

    function _anyFilterActive() {
      for (const def of FILTER_FIELDS) {
        if (def.kind === "match-exact" || def.kind === "match-numeric") {
          if (matchState[def.key]) return true;
        } else if (def.kind === "constraint-bool") {
          if (constraintState[def.key]) return true;
        } else if (def.kind === "constraint-select") {
          const v = constraintState[def.key];
          if (v && v !== "all") return true;
        }
      }
      return false;
    }

    // Normalize a localStorage entry (legacy shape) to the DB row shape so
    // both can flow through the same row renderer.
    function _normalizeLocal(e) {
      return {
        id: e.id,
        bridge: e.bridge,
        created_at: e.started_at,
        status: e.status,
        first_file_id: (typeof e.first_saved_file_id === "number")
          ? e.first_saved_file_id : null,
        axes_params: Array.isArray(e.axes_params) ? e.axes_params : [],
        axis_count: Array.isArray(e.axes_params) ? e.axes_params.length : 0,
        file_count: 0,
        sampler: e.sampler, width: e.width, height: e.height,
        steps: e.steps, cfg: e.cfg, base_seed: e.base_seed,
        checkpoint: e.checkpoint, vae: e.vae,
        prompt_template: e.prompt_template,
        negative_template: e.negative_template,
      };
    }

    function _entryStatusClass(e) {
      if (e.status === "running") {
        const age = _now() - (e.created_at || 0);
        if (age > STALE_UNKNOWN_SEC) return "unknown";
        return "running";
      }
      return e.status || "completed";
    }

    function _axesSummary(e) {
      const params = e.axes_params || [];
      if (params.length === 0) return "";
      const head = params.slice(0, 2).join(" / ");
      if (params.length <= 2) return head;
      return `${head} / +${params.length - 2}`;
    }

    let _entries = [];
    let _total = 0;
    let _abortCtl = null;
    let _fetchTimer = null;
    let _lastQuery = "";

    function _buildQuery() {
      const q = new URLSearchParams();
      q.set("limit", String(currentCount));
      if (referenceSweepId) q.set("ref", referenceSweepId);
      const matchKeys = [];
      for (const def of FILTER_FIELDS) {
        if (def.kind !== "match-exact" && def.kind !== "match-numeric") continue;
        if (matchState[def.key]) matchKeys.push(def.key);
      }
      if (matchKeys.length) q.set("match", matchKeys.join(","));
      if (toleranceState.steps && toleranceState.steps !== "exact") {
        q.set("tol_steps", toleranceState.steps);
      }
      if (toleranceState.cfg && toleranceState.cfg !== "exact") {
        q.set("tol_cfg", toleranceState.cfg);
      }
      if (constraintState.completedOnly) q.set("completed_only", "1");
      if (constraintState.savedOnly) q.set("saved_only", "1");
      if (constraintState.axisCount && constraintState.axisCount !== "all") {
        q.set("axis_count", constraintState.axisCount);
      }
      if (constraintState.dateRange && constraintState.dateRange !== "all") {
        q.set("date_range", constraintState.dateRange);
      }
      return q.toString();
    }

    async function _fetchHistory() {
      const qstr = _buildQuery();
      _lastQuery = qstr;
      if (_abortCtl) {
        try { _abortCtl.abort(); } catch (_e) { /* no-op */ }
      }
      _abortCtl = (typeof AbortController !== "undefined") ? new AbortController() : null;
      try {
        const r = await fetch("/api/sweeps/history?" + qstr, {
          signal: _abortCtl ? _abortCtl.signal : undefined,
          headers: { "Accept": "application/json" },
        });
        const j = await r.json();
        if (qstr !== _lastQuery) return; // a newer fetch superseded us
        if (j && j.ok && j.data) {
          _entries = Array.isArray(j.data.entries) ? j.data.entries : [];
          _total = typeof j.data.total === "number" ? j.data.total : 0;
        } else {
          _entries = []; _total = 0;
        }
      } catch (e) {
        if (e && e.name === "AbortError") return;
        // Fall back to empty list; localStorage running entries still shown.
        _entries = []; _total = 0;
      }
      _renderEntries();
    }

    function _renderEntries() {
      // If the filter row was built before /api/sweeps/history responded
      // and the reference sweep lives only in DB (not localStorage), the
      // chips will all be greyed out. Once entries arrive, rebuild so the
      // ref entry's fields enable the chips.
      if (referenceSweepId && filterContainer
          && filterContainer.dataset.hasRef === "false"
          && _refEntry()) {
        _buildFilterUI();
      }
      while (body.firstChild) body.removeChild(body.firstChild);
      // Merge in localStorage running entries (DB doesn't have them until
      // the first save lands). Skip ones already represented in DB result.
      const dbIds = new Set(_entries.map((e) => e.id));
      const running = getHistory()
        .filter((e) => e.status === "running" && !dbIds.has(e.id))
        .map(_normalizeLocal);
      const merged = running.concat(_entries);

      if (filterStatus) {
        if (_anyFilterActive()) {
          const tmpl = _tr("bridge.sweep.filterCount", "{shown} / {total} 件一致");
          filterStatus.textContent = tmpl
            .replace("{shown}", String(merged.length))
            .replace("{total}", String(_total));
        } else {
          filterStatus.textContent = "";
        }
      }

      if (merged.length === 0) {
        const empty = document.createElement("div");
        empty.className = "bsqj-empty";
        empty.textContent = _tr(
          "bridge.sweep.historyEmpty",
          "履歴はまだありません。Sweep を実行すると追加されます。",
        );
        body.appendChild(empty);
        return;
      }

      for (const e of merged) {
        const row = document.createElement("div");
        row.className = "bsqj-row bsqj-list-row";
        if (referenceSweepId && e.id === referenceSweepId) {
          row.classList.add("bsqj-list-row-current");
          row.setAttribute("aria-current", "true");
        }
        const cls = _entryStatusClass(e);
        const status = document.createElement("span");
        status.className = `bsqj-status bsqj-status-${cls}`;
        const statusKey = `bridge.sweep.status${cls.charAt(0).toUpperCase()}${cls.slice(1)}`;
        status.setAttribute("aria-label", _tr(statusKey, cls));
        row.appendChild(status);
        const meta = document.createElement("span");
        meta.className = "bsqj-meta";
        const bridgeLabel = (e.bridge || "").toUpperCase();
        const summary = _axesSummary(e) || "—";
        meta.textContent = `${_formatDate(e.created_at)} · ${bridgeLabel} · ${summary}`;
        row.appendChild(meta);
        const enabled = typeof e.first_file_id === "number";
        row.setAttribute("role", "link");
        row.setAttribute("tabindex", enabled ? "0" : "-1");
        row.setAttribute("aria-disabled", enabled ? "false" : "true");
        if (!enabled) {
          row.title = _tr("bridge.sweep.notSaved", "画像が保存されていません");
        }
        const handle = () => {
          if (!enabled) return;
          const url = buildUrl(e.id, e.first_file_id);
          if (url) window.location.href = url;
        };
        row.addEventListener("click", handle);
        row.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") handle();
        });
        body.appendChild(row);
      }
    }

    function _redraw() {
      // Debounce fetches when many checkboxes flip in quick succession
      // (e.g. "select all").
      if (_fetchTimer) clearTimeout(_fetchTimer);
      _fetchTimer = setTimeout(_fetchHistory, 80);
    }

    _buildFilterUI();
    _renderEntries();   // immediate skeleton (running entries + empty)
    _fetchHistory();    // populate from DB
    document.addEventListener("bridge-sweep-history-changed", _redraw);
    return { redraw: _redraw };
  }

  window.BridgeSweepQuickJump = {
    registerStart,
    registerFirstSavedFileId,
    markCompleted,
    markFailed,
    markCancelled,
    buildUrl,
    openInNewTab,
    getHistory,
    clearHistory,
    renderHistoryPopover,
    renderHistoryList,
  };

  // Cross-tab refresh hook: pages that have a popover open can listen.
  window.addEventListener("storage", (e) => {
    if (e.key !== KEY) return;
    document.dispatchEvent(new CustomEvent("bridge-sweep-history-changed"));
  });
})();

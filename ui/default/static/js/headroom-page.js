/** Headroom proxy statistics dashboard. Polls /api/headroom/health + /api/headroom/stats every 5s. */

const REFRESH_MS = 5000;
const HISTORY_MS = 60_000;

let tokenChart = null;
let costChart = null;
let historyCache = { daily: null, hourly: null };
let currentGranularity = 'daily';
let historyInterval = null;

function el(id) { return document.getElementById(id); }

function fmt(n) {
  if (n == null) return "—";
  if (typeof n !== "number") return String(n);
  return n >= 1_000_000
    ? (n / 1_000_000).toFixed(2) + "M"
    : n >= 1_000
    ? (n / 1_000).toFixed(1) + "K"
    : String(n);
}

function fmtMs(ms) {
  if (ms == null) return "—";
  return ms >= 1000 ? (ms / 1000).toFixed(2) + "s" : Math.round(ms) + "ms";
}

function fmtUsd(v) {
  if (v == null) return "—";
  return "$" + Number(v).toFixed(2);
}

function fmtUptime(seconds) {
  if (seconds == null) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function fmtPct(v) {
  if (v == null) return "—";
  return Number(v).toFixed(1) + "%";
}

function fmtReset(seconds) {
  if (seconds == null || seconds <= 0) return "";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `リセットまで ${h}h ${m}m`;
  return `リセットまで ${m}m`;
}

function fmtResetValue(v) {
  if (v == null) return "—";
  if (typeof v === "number") return fmtReset(v) || "—";
  const ts = new Date(v).getTime();
  if (!Number.isNaN(ts)) {
    const seconds = Math.max(0, Math.round((ts - Date.now()) / 1000));
    return fmtReset(seconds) || "今";
  }
  return String(v);
}

function fmtAgo(ts) {
  if (!ts) return "—";
  const diff = Math.round((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 60) return `${diff}s前`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m前`;
  return `${Math.floor(diff / 3600)}h前`;
}

function checkStatus(text, enabled, ready) {
  if (!enabled) return "無効";
  if (ready) return "✓";
  return text || "—";
}

async function fetchJSON(path) {
  const resp = await fetch(path);
  const body = await resp.json();
  return { ok: resp.ok, status: resp.status, data: body.data ?? body };
}

function setText(id, v) {
  const e = el(id);
  if (e) e.textContent = v;
}

function makeTd(text, cls) {
  const td = document.createElement("td");
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
}

function makeRow(...cells) {
  const tr = document.createElement("tr");
  for (const [text, cls] of cells) tr.appendChild(makeTd(text, cls));
  return tr;
}

function isPlainObject(v) {
  return v != null && typeof v === "object" && !Array.isArray(v);
}

function titleizeKey(key) {
  const value = String(key)
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase());
  return value
    .replace(/\bOpenai\b/g, "OpenAI")
    .replace(/\bGpt\b/g, "GPT");
}

function firstValue(obj, keys) {
  for (const key of keys) {
    if (obj?.[key] != null) return obj[key];
  }
  return null;
}

function quotaPct(v) {
  if (v == null) return null;
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return n <= 1 ? n * 100 : n;
}

function quotaRootCandidates(data) {
  const roots = [];
  for (const key of ["quota", "quotas", "provider_quota", "provider_quotas", "rate_limits", "provider_stats"]) {
    if (isPlainObject(data[key])) roots.push([key, data[key]]);
  }
  for (const key of ["openai", "codex", "chatgpt", "gpt", "openai_quota", "codex_quota"]) {
    if (isPlainObject(data[key])) roots.push([key.replace(/_quota$/, ""), data[key]]);
  }
  return roots;
}

function quotaLimitsFromProvider(providerData) {
  if (!isPlainObject(providerData)) return null;
  return providerData.limits
    ?? providerData.rate_limits
    ?? providerData.windows
    ?? providerData.usage_windows
    ?? null;
}

function hasQuotaFields(v) {
  if (!isPlainObject(v)) return false;
  return firstValue(v, [
    "limit", "total", "maximum", "max", "quota", "used", "consumed", "remaining",
    "utilization_pct", "usage_pct", "percent_used", "used_percent", "reset_seconds", "seconds_to_reset",
    "reset_at", "reset_time", "status",
  ]) != null;
}

function quotaProviderEntries(root) {
  if (isPlainObject(root.providers)) return Object.entries(root.providers);
  if (isPlainObject(root.provider_stats)) return Object.entries(root.provider_stats);
  if (isPlainObject(root.by_provider)) return Object.entries(root.by_provider);
  return Object.entries(root);
}

function _collectCodexRateLimits(data, rows, seen) {
  const cr = data.codex_rate_limits;
  if (!isPlainObject(cr)) return;
  for (const windowKey of ["primary", "secondary"]) {
    const w = cr[windowKey];
    if (!isPlainObject(w)) continue;
    const windowName = w.window_label ?? windowKey;
    const key = `codex:${windowName}`;
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({
      provider: "codex",
      windowName,
      limitValue: null,
      used: null,
      remaining: null,
      pct: quotaPct(w.used_percent),
      reset: w.seconds_until_reset ?? null,
      status: "",
    });
  }
}

function _collectCopilotQuota(data, rows, seen) {
  const cq = data.copilot_quota;
  if (!isPlainObject(cq)) return;
  const latest = cq.latest;
  if (!isPlainObject(latest)) return;
  const cats = latest.categories;
  if (!isPlainObject(cats)) return;
  const resetDate = latest.quota_reset_date_utc ?? null;
  for (const [catName, cat] of Object.entries(cats)) {
    if (!isPlainObject(cat)) continue;
    const key = `copilot:${catName}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const pctRaw = cat.used_percent ?? (cat.percent_remaining != null ? 100 - cat.percent_remaining : null);
    rows.push({
      provider: "copilot",
      windowName: catName,
      limitValue: cat.entitlement ?? null,
      used: cat.used ?? null,
      remaining: cat.remaining ?? null,
      pct: quotaPct(pctRaw),
      reset: resetDate,
      status: cat.unlimited ? "unlimited" : "",
    });
  }
}

function collectProviderQuotas(data) {
  const rows = [];
  const seen = new Set();
  _collectCodexRateLimits(data, rows, seen);
  _collectCopilotQuota(data, rows, seen);

  function addLimit(provider, limitName, rawLimit) {
    const limit = isPlainObject(rawLimit) ? rawLimit : { value: rawLimit };
    if (!hasQuotaFields(limit)) return;

    const limitValue = firstValue(limit, ["limit", "total", "maximum", "max", "quota"]);
    const used = firstValue(limit, ["used", "consumed", "current", "usage", "requests_used", "tokens_used"]);
    const remaining = firstValue(limit, ["remaining", "available", "requests_remaining", "tokens_remaining"])
      ?? (typeof limitValue === "number" && typeof used === "number" ? limitValue - used : null);
    const pct = quotaPct(firstValue(limit, ["utilization_pct", "usage_pct", "percent_used", "used_percent", "used_pct", "percentage"]));
    const windowName = firstValue(limit, ["label", "name", "window", "period", "scope"]) ?? limitName;
    const reset = firstValue(limit, ["seconds_to_reset", "reset_seconds", "reset_in_seconds", "reset_at", "reset_time", "window_reset_at"]);
    const status = firstValue(limit, ["status", "state", "message"]) ?? "";
    const key = `${provider}:${windowName}`;
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({ provider, windowName, limitValue, used, remaining, pct, reset, status });
  }

  function collectProvider(provider, providerData) {
    const limits = quotaLimitsFromProvider(providerData);
    if (Array.isArray(limits)) {
      limits.forEach((limit, index) => addLimit(provider, limit?.name ?? limit?.label ?? `limit ${index + 1}`, limit));
      return;
    }
    if (isPlainObject(limits)) {
      for (const [limitName, limit] of Object.entries(limits)) addLimit(provider, limitName, limit);
      return;
    }
    if (hasQuotaFields(providerData)) addLimit(provider, providerData.name ?? provider, providerData);
  }

  for (const [rootName, root] of quotaRootCandidates(data)) {
    if (quotaLimitsFromProvider(root) || hasQuotaFields(root)) {
      collectProvider(root.provider ?? rootName, root);
      continue;
    }
    for (const [provider, providerData] of quotaProviderEntries(root)) {
      collectProvider(provider, providerData);
    }
  }

  return rows.sort((a, b) => String(a.provider).localeCompare(String(b.provider)) || String(a.windowName).localeCompare(String(b.windowName)));
}

function renderProviderQuotas(data) {
  const section = el("hrProviderQuotaSection");
  const tbody = el("hrProviderQuotaTbody");
  if (!section || !tbody) return;

  const rows = collectProviderQuotas(data);
  section.style.display = rows.length ? "" : "none";
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
  if (rows.length === 0) return;

  for (const row of rows) {
    const usedText = row.limitValue != null && row.used != null
      ? `${fmt(row.used)} / ${fmt(row.limitValue)}`
      : fmt(row.used ?? row.limitValue);
    tbody.appendChild(makeRow(
      [titleizeKey(row.provider)],
      [titleizeKey(row.windowName)],
      [usedText, "hr-num"],
      [fmt(row.remaining), "hr-num"],
      [row.pct != null ? fmtPct(row.pct) : "—", "hr-num"],
      [fmtResetValue(row.reset)],
      [row.status ? String(row.status) : "—"],
    ));
  }
}

function applyHealth(data) {
  const badge = el("hrStatusBadge");
  if (data.code === "offline") {
    badge.textContent = "オフライン";
    badge.className = "headroom-badge headroom-badge--offline";
    showError("headroom proxy が起動していません (port 8787)");
    return;
  }
  clearError();
  const status = data.status ?? "unknown";
  badge.textContent = status === "healthy" ? "稼働中" : status;
  badge.className = `headroom-badge headroom-badge--${status === "healthy" ? "healthy" : "unhealthy"}`;

  setText("hrVersion", data.version ?? "—");
  setText("hrUptime", fmtUptime(data.uptime_seconds));
  setText("hrBackend", data.config?.backend ?? "—");

  const checks = data.checks ?? {};
  setText("hrHttpClient", checkStatus(
    checks.http_client?.status, checks.http_client?.enabled ?? true, checks.http_client?.ready
  ));
  setText("hrCache", checkStatus(
    checks.cache?.status, checks.cache?.enabled, checks.cache?.ready
  ));

  // Compression executor is in health.runtime
  const exec = data.runtime?.compression_executor ?? {};
  setText("hrExecWorkers", exec.max_workers ?? "—");
  setText("hrExecQueued", exec.queued ?? "—");
  setText("hrExecRunning", exec.running ?? "—");
  setText("hrExecInFlightMax", exec.in_flight_max ?? "—");
  setText("hrExecLeaked", exec.leaked_threads_total ?? "—");
}

function applyStats(data) {
  if (data.code) { showError(data.error ?? "stats 取得エラー"); return; }
  clearError();

  // Token savings
  const tokens = data.tokens ?? {};
  setText("hrTokensSaved", fmt(tokens.saved));
  setText("hrSavingsPct", fmtPct(tokens.active_savings_percent ?? tokens.savings_percent));
  setText("hrTokBefore", fmt(tokens.proxy_total_before_compression ?? tokens.total_before_compression));
  setText("hrTokRtk", fmt(tokens.rtk_saved ?? tokens.cli_filtering_saved));
  setText("hrTokProxy", fmt(tokens.proxy_compression_saved));
  setText("hrTokensIn", fmt(tokens.input));
  setText("hrTokensOut", fmt(tokens.output));

  // Request stats
  const reqs = data.requests ?? {};
  setText("hrReqTotal", fmt(reqs.total));
  setText("hrReqCached", fmt(reqs.cached));
  setText("hrReqRateLimited", fmt(reqs.rate_limited));
  setText("hrReqFailed", fmt(reqs.failed));

  const lat = data.latency ?? {};
  setText("hrLatencyAvg", lat.average_ms != null ? fmtMs(lat.average_ms) : "—");
  if (lat.min_ms != null && lat.max_ms != null) {
    setText("hrLatencyRange", fmtMs(lat.min_ms) + " – " + fmtMs(lat.max_ms));
  }

  // Cost breakdown
  const cost = data.cost ?? {};
  const saved = cost.savings_usd ?? 0;
  const cacheSaved = cost.cache_savings_usd ?? 0;
  const comprSaved = cost.compression_savings_usd ?? 0;
  setText("hrCostTotalSaved", fmtUsd(saved + cacheSaved));
  setText("hrCostCache", fmtUsd(cacheSaved));
  setText("hrCostCompression", fmtUsd(comprSaved));
  setText("hrCostInput", fmtUsd(cost.total_input_cost_usd ?? cost.cost_with_headroom_usd));

  // Prefix cache
  const pc = data.prefix_cache?.totals ?? data.prefix_cache ?? {};
  setText("hrCacheHitRate", pc.hit_rate != null ? fmtPct(pc.hit_rate) : "—");
  setText("hrCacheNetSaved", pc.net_savings_usd != null ? fmtUsd(pc.net_savings_usd) : (pc.savings_usd != null ? fmtUsd(pc.savings_usd) : "—"));
  setText("hrCacheReads", fmt(pc.cache_read_tokens));
  setText("hrCacheWrites", fmt(pc.cache_write_tokens));
  setText("hrCacheBusts", pc.bust_count != null ? String(pc.bust_count) : "—");

  // TTL mix
  const ttlMix = data.prefix_cache?.totals?.observed_ttl_mix ?? data.prefix_cache?.observed_ttl_mix;
  if (ttlMix) {
    setText("hrCacheTtl", `1h ${fmtPct(ttlMix["1h_pct"])} / 5m ${fmtPct(ttlMix["5m_pct"])}`);
  }

  // Subscription window
  const subWin = data.subscription_window?.latest;
  const subSection = el("hrSubWindowSection");
  if (subWin && subSection) {
    subSection.style.display = "";
    const fh = subWin.five_hour ?? {};
    const sd = subWin.seven_day ?? {};
    const ss = subWin.seven_day_sonnet ?? {};

    setText("hrSub5h", fmtPct(fh.utilization_pct));
    setText("hrSub5hReset", fmtReset(fh.seconds_to_reset));
    const bar5h = el("hrSub5hBar");
    if (bar5h) bar5h.style.width = Math.min(100, fh.utilization_pct ?? 0) + "%";

    setText("hrSub7d", fmtPct(sd.utilization_pct));
    setText("hrSub7dReset", fmtReset(sd.seconds_to_reset));
    const bar7d = el("hrSub7dBar");
    if (bar7d) bar7d.style.width = Math.min(100, sd.utilization_pct ?? 0) + "%";

    if (ss.utilization_pct != null) {
      setText("hrSubSonnet", fmtPct(ss.utilization_pct));
      setText("hrSubSonnetReset", fmtReset(ss.seconds_to_reset));
      const barSs = el("hrSubSonnetBar");
      if (barSs) barSs.style.width = Math.min(100, ss.utilization_pct ?? 0) + "%";
    }
  }
  renderProviderQuotas(data);

  // Performance detail
  const oh = data.overhead ?? {};
  setText("hrOhAvg", oh.average_ms != null ? fmtMs(oh.average_ms) : "—");
  if (oh.min_ms != null && oh.max_ms != null) {
    setText("hrOhRange", fmtMs(oh.min_ms) + " – " + fmtMs(oh.max_ms));
  }
  const ttfb = data.ttfb ?? {};
  setText("hrTtfbAvg", ttfb.average_ms != null ? fmtMs(ttfb.average_ms) : "—");
  if (ttfb.min_ms != null && ttfb.max_ms != null) {
    setText("hrTtfbRange", fmtMs(ttfb.min_ms) + " – " + fmtMs(ttfb.max_ms));
  }

  // Pipeline timing table
  const pipeline = data.pipeline_timing ?? {};
  const ptbody = el("hrPipelineTbody");
  if (ptbody) {
    while (ptbody.firstChild) ptbody.removeChild(ptbody.firstChild);
    const pEntries = Object.entries(pipeline).sort((a, b) => (b[1].average_ms ?? 0) - (a[1].average_ms ?? 0));
    if (pEntries.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 4; td.style.color = "var(--muted,#888)"; td.textContent = "データなし";
      tr.appendChild(td); ptbody.appendChild(tr);
    } else {
      for (const [step, v] of pEntries) {
        ptbody.appendChild(makeRow(
          [step],
          [fmtMs(v.average_ms), "hr-num"],
          [fmtMs(v.max_ms), "hr-num"],
          [v.count != null ? String(v.count) : "—", "hr-num"],
        ));
      }
    }
  }

  // Per-model table (requests + token savings)
  const perModel = cost.per_model ?? {};
  const byModel = reqs.by_model ?? {};
  const tbody = el("hrModelTbody");
  if (tbody) {
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
    const models = new Set([...Object.keys(perModel), ...Object.keys(byModel)]);
    const entries = [...models].map(m => {
      const pm = perModel[m] ?? {};
      return {
        model: m,
        requests: pm.requests ?? byModel[m] ?? 0,
        saved: pm.tokens_saved ?? 0,
        sent: pm.tokens_sent ?? 0,
        reduction: pm.reduction_pct ?? 0,
      };
    }).sort((a, b) => b.requests - a.requests);

    if (entries.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 5; td.style.color = "var(--muted,#888)"; td.textContent = "データなし";
      tr.appendChild(td); tbody.appendChild(tr);
    } else {
      for (const e of entries) {
        tbody.appendChild(makeRow(
          [e.model],
          [fmt(e.requests), "hr-num"],
          [fmt(e.saved), "hr-num"],
          [fmt(e.sent), "hr-num"],
          [fmtPct(e.reduction), "hr-num"],
        ));
      }
    }
  }

  // Recent requests table
  const recent = data.recent_requests ?? [];
  const rtbody = el("hrRecentTbody");
  if (rtbody) {
    while (rtbody.firstChild) rtbody.removeChild(rtbody.firstChild);
    if (recent.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7; td.style.color = "var(--muted,#888)"; td.textContent = "データなし";
      tr.appendChild(td); rtbody.appendChild(tr);
    } else {
      for (const r of recent.slice(-10).reverse()) {
        const cacheTd = document.createElement("td");
        const cacheSpan = document.createElement("span");
        cacheSpan.textContent = r.cache_hit ? "✓ hit" : "miss";
        cacheSpan.className = r.cache_hit ? "hr-cache-hit" : "hr-cache-miss";
        cacheTd.appendChild(cacheSpan);
        const tr = makeRow(
          [fmtAgo(r.timestamp)],
          [r.model ?? "—"],
          [fmt(r.input_tokens_original), "hr-num"],
          [fmt(r.output_tokens), "hr-num"],
          [fmtPct(r.savings_percent), "hr-num"],
          [fmtMs(r.total_latency_ms), "hr-num"],
        );
        tr.appendChild(cacheTd);
        rtbody.appendChild(tr);
      }
    }
  }
  applyLifetimeCards(data);
}

function showError(msg) {
  const div = el("hrError");
  if (div) { div.textContent = "⚠️ " + msg; div.style.display = "block"; }
}

function clearError() {
  const div = el("hrError");
  if (div) div.style.display = "none";
}

function applyReadyz(data) {
  const sec = el('hrReadyz');
  if (!sec) return;
  if (!data || data.code) { sec.style.display = 'none'; return; }
  sec.style.display = '';
  setText('hrRzVersion', data.version ?? '—');
  setText('hrRzTimeout', data.compression_timeout_seconds != null
    ? `${data.compression_timeout_seconds}s` : '—');
  setText('hrRzMaxBody', data.max_body_bytes != null
    ? fmt(data.max_body_bytes) + ' bytes' : '—');
  setText('hrRzUpstream', data.upstream_url ?? '—');
  setText('hrRzContentTypes', data.supported_content_types?.length != null
    ? `${data.supported_content_types.length} types` : '—');
}

function applyLifetimeCards(data) {
  const tokens = data.tokens ?? {};
  const cost = data.cost ?? {};
  const reqs = data.requests ?? {};
  setText('hrLtTokensSaved', fmt(tokens.saved));
  setText('hrLtSavingsPct', fmtPct(tokens.active_savings_percent ?? tokens.savings_percent));
  setText('hrLtCompressionUsd', fmtUsd(cost.compression_savings_usd));
  setText('hrLtTotalUsd', fmtUsd((cost.savings_usd ?? 0) + (cost.cache_savings_usd ?? 0)));
  setText('hrLtRequests', fmt(reqs.total));
}

function applyHistory(cache, granularity) {
  const buckets = cache[granularity];
  if (!buckets || !tokenChart || !costChart) return;

  const labels = buckets.map(b => {
    const ts = b.ts ?? b.timestamp ?? b.date ?? b.bucket ?? '';
    const d = new Date(ts);
    if (isNaN(d.getTime())) return String(ts).slice(0, 13);
    return granularity === 'hourly'
      ? d.toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric' }) + ' ' +
        d.toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString('ja-JP', { month: 'numeric', day: 'numeric' });
  });

  const rawTokens = buckets.map(b => Number(b.tokens_saved ?? 0));
  const isMonotone = rawTokens.every((v, i) => i === 0 || v >= rawTokens[i - 1]);
  const tokenData = isMonotone && rawTokens.some((v, i) => i > 0 && v > rawTokens[i - 1])
    ? rawTokens.map((v, i) => i === 0 ? v : Math.max(0, v - rawTokens[i - 1]))
    : rawTokens;

  const costData = buckets.map(b =>
    parseFloat(Number(b.compression_savings_usd_delta ?? b.cost_delta ?? 0).toFixed(4))
  );

  tokenChart.data.labels = labels;
  tokenChart.data.datasets[0].data = tokenData;
  tokenChart.update();

  costChart.data.labels = labels;
  costChart.data.datasets[0].data = costData;
  costChart.update();
}

function initCharts() {
  const C = globalThis.Chart;
  if (!C) return;
  const style = getComputedStyle(document.documentElement);
  C.defaults.color = style.getPropertyValue('--text-muted').trim() || '#888';
  const barColor = style.getPropertyValue('--accent').trim() || '#6b46c1';
  const costColor = (style.getPropertyValue('--accent').trim() || '#6b46c1') + '99';

  tokenChart = new C(el('hrTokenChart'), {
    type: 'bar',
    data: { labels: [], datasets: [{ label: '節約トークン', data: [], backgroundColor: barColor }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
  });
  costChart = new C(el('hrCostChart'), {
    type: 'bar',
    data: { labels: [], datasets: [{ label: 'コスト節約 USD', data: [], backgroundColor: costColor }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
  });
}

function groupByGranularity(entries, granularity) {
  // entries: headroom history array with cumulative total_tokens_saved / compression_savings_usd
  const keyOf = granularity === 'daily'
    ? ts => new Date(ts).toISOString().slice(0, 10)        // YYYY-MM-DD
    : ts => new Date(ts).toISOString().slice(0, 13) + ':00:00Z'; // YYYY-MM-DDTHH:00:00Z (parseable)

  const groups = new Map();
  for (const e of entries) {
    const key = keyOf(e.timestamp ?? e.ts ?? e.date ?? e.bucket ?? '');
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(e);
  }

  const sorted = [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  let prevEntry = null; // ponytail: carry previous bucket's tail as baseline so single-entry buckets aren't zero
  return sorted.map(([key, items]) => {
    const baseline = prevEntry ?? { total_tokens_saved: 0, tokens_saved: 0, compression_savings_usd: 0 };
    const last = items[items.length - 1];
    prevEntry = last;
    return {
      timestamp: key,
      tokens_saved: Math.max(0, (last.total_tokens_saved ?? last.tokens_saved ?? 0)
                              - (baseline.total_tokens_saved ?? baseline.tokens_saved ?? 0)),
      compression_savings_usd_delta: Math.max(0, (last.compression_savings_usd ?? 0)
                                               - (baseline.compression_savings_usd ?? 0)),
    };
  });
}

async function fetchHistory() {
  const errEl = el('hrHistoryError');
  const [d] = await Promise.allSettled([
    fetchJSON('/api/headroom/stats-history'),
  ]);
  let hasErr = false;
  if (d.status === 'fulfilled' && d.value.ok) {
    const raw = d.value.data;
    // headroom returns {history:[...]} or {buckets:[...]} or bare array
    const entries = Array.isArray(raw) ? raw : (raw?.history ?? raw?.buckets ?? []);
    historyCache.daily = groupByGranularity(entries, 'daily');
    historyCache.hourly = groupByGranularity(entries, 'hourly');
  } else { hasErr = true; }
  if (errEl) errEl.style.display = hasErr ? '' : 'none';
  if (errEl && hasErr) errEl.textContent = '履歴取得エラー';
  applyHistory(historyCache, currentGranularity);
}

async function refresh() {
  try {
    const [h, s, r] = await Promise.allSettled([
      fetchJSON("/api/headroom/health"),
      fetchJSON("/api/headroom/stats"),
      fetchJSON("/api/headroom/readyz"),
    ]);
    if (h.status === "fulfilled") applyHealth(h.value.data);
    else showError("health 取得失敗");
    if (s.status === "fulfilled" && s.value.ok) applyStats(s.value.data);
    else if (s.status === "fulfilled") showError(s.value.data?.error ?? "stats 取得エラー");
    if (r.status === "fulfilled") applyReadyz(r.value.data);
  } catch (e) {
    showError(e.message);
  }
}

initCharts();

el('hrHistoryDaily')?.addEventListener('click', () => {
  currentGranularity = 'daily';
  el('hrHistoryDaily').classList.add('hr-toggle-btn--active');
  el('hrHistoryHourly').classList.remove('hr-toggle-btn--active');
  applyHistory(historyCache, 'daily');
});
el('hrHistoryHourly')?.addEventListener('click', () => {
  currentGranularity = 'hourly';
  el('hrHistoryHourly').classList.add('hr-toggle-btn--active');
  el('hrHistoryDaily').classList.remove('hr-toggle-btn--active');
  applyHistory(historyCache, 'hourly');
});

fetchHistory();
historyInterval = setInterval(fetchHistory, HISTORY_MS);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    clearInterval(historyInterval);
    historyInterval = null;
  } else {
    fetchHistory();
    historyInterval = setInterval(fetchHistory, HISTORY_MS);
  }
});

refresh();
setInterval(refresh, REFRESH_MS);

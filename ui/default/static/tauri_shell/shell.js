// Tauri Shell — tab manager + history + postMessage router.
// Spec: docs/superpowers/specs/2026-05-04-tauri-multi-tab-ux-design.md

const ORIGIN = window.location.origin;
const LS_PREFIX = "tauriShell:";
const PENDING_MAX = 16;
const READY_TIMEOUT_MS = 5000;

const state = {
  tabsConfig: null,
  iframes: new Map(),       // tabId -> {el, ready, pending: [], lastVisible: false}
  activeCategory: null,
  activeTab: null,
  breadcrumb: [],           // dedup, max 5
  navStack: [],             // no dedup, max 50, in-memory only
  navIndex: -1,
  lastVisibleTab: null,
};

async function init() {
  const resp = await fetch("/api/tauri-shell/tabs", {cache: "no-cache"});
  state.tabsConfig = await resp.json();
  loadBreadcrumb();
  renderCategoryBar();
  preMountEager();
  const restored = restoreLastActive();
  switchTo(restored.category, restored.tab, {pushNav: false});
  attachKeyHandlers();
  attachMessageHandlers();
  attachExtLauncherNavInterceptor();
  exposeApi();
}

function exposeApi() {
  window.__tauriShell = {
    version: 1,
    api: {
      switchTo: (c, t) => switchTo(c, t),
      sendTo: (target, payload) => switchAndSend(target, payload),
      getActive: () => ({category: state.activeCategory, tab: state.activeTab}),
      getHistory: () => ({breadcrumb: [...state.breadcrumb], navStack: [...state.navStack]}),
      reloadTab: (tabId) => reloadTab(tabId),
    },
  };
}

function loadBreadcrumb() {
  try {
    const raw = localStorage.getItem(LS_PREFIX + "breadcrumb");
    if (raw) state.breadcrumb = JSON.parse(raw).slice(0, 5);
  } catch (_) { /* ignore */ }
}

function saveBreadcrumb() {
  try {
    localStorage.setItem(LS_PREFIX + "breadcrumb", JSON.stringify(state.breadcrumb));
  } catch (_) { /* ignore */ }
}

function restoreLastActive() {
  const cat = localStorage.getItem(LS_PREFIX + "activeCategory")
              || state.tabsConfig.categories[0].id;
  const tab = localStorage.getItem(LS_PREFIX + "lastActiveTab:" + cat)
              || state.tabsConfig.categories.find(c => c.id === cat).tabs[0].id;
  return {category: cat, tab};
}

function renderCategoryBar() {
  const bar = document.getElementById("category-bar");
  // Clear existing children safely
  while (bar.firstChild) bar.removeChild(bar.firstChild);
  state.tabsConfig.categories.forEach(cat => {
    const btn = document.createElement("button");
    btn.className = "category-btn";
    btn.dataset.categoryId = cat.id;
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-controls", "tab-bar");
    btn.textContent = cat.icon;
    btn.title = (window.tr ? window.tr(cat.labelKey) : cat.labelKey);
    btn.addEventListener("click", () => {
      const lastTab = localStorage.getItem(LS_PREFIX + "lastActiveTab:" + cat.id)
                      || cat.tabs[0].id;
      switchTo(cat.id, lastTab);
    });
    bar.appendChild(btn);
  });
}

function renderTabBar(categoryId) {
  const bar = document.getElementById("tab-bar");
  // Clear tab buttons only (preserve #shell-tab-utils)
  bar.querySelectorAll('.tab-btn').forEach(b => b.remove());
  const cat = state.tabsConfig.categories.find(c => c.id === categoryId);
  cat.tabs.forEach(tab => {
    const btn = document.createElement("button");
    btn.className = "tab-btn";
    btn.dataset.tabId = tab.id;
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-controls", "iframe-" + tab.id);
    btn.textContent = (window.tr ? window.tr(tab.labelKey) : tab.labelKey);
    btn.addEventListener("click", () => switchTo(categoryId, tab.id));
    btn.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      reloadTab(tab.id);
    });
    bar.appendChild(btn);
  });
  applyBreadcrumbGlow();
}

function preMountEager() {
  state.tabsConfig.categories.forEach(cat => {
    cat.tabs.forEach(tab => {
      if (tab.mount === "eager") mountIframe(tab);
    });
  });
}

function mountIframe(tab) {
  if (state.iframes.has(tab.id)) return state.iframes.get(tab.id);
  const el = document.createElement("iframe");
  el.id = "iframe-" + tab.id;
  el.dataset.tabId = tab.id;
  el.src = tab.url;
  el.style.display = "none";
  el.style.width = "100%";
  el.style.height = "100%";
  el.style.border = "0";
  el.setAttribute("role", "tabpanel");
  document.getElementById("shell-iframe-container").appendChild(el);
  const entry = {el, ready: false, pending: [], lastVisible: false};
  state.iframes.set(tab.id, entry);
  el.addEventListener("load", () => injectShortcutBridge(el));
  return entry;
}

function injectShortcutBridge(iframe) {
  try {
    const doc = iframe.contentDocument;
    if (!doc) return;
    if (doc.querySelector('script[data-tauri-shell-injected]')) return;
    const s = doc.createElement("script");
    s.src = "/static/tauri_shell/shortcut_bridge.js";
    s.dataset.tauriShellInjected = "1";
    s.dataset.tabId = iframe.dataset.tabId;
    doc.head.appendChild(s);
  } catch (e) {
    console.error("[tauri-shell] inject failed", e);
  }
}

function switchTo(categoryId, tabId, opts = {}) {
  const tab = findTab(categoryId, tabId);
  if (!tab) return;
  let entry = state.iframes.get(tabId);
  if (!entry) entry = mountIframe(tab);

  // hide all, show target
  state.iframes.forEach((e) => { e.el.style.display = "none"; });
  entry.el.style.display = "block";

  state.activeCategory = categoryId;
  state.activeTab = tabId;
  localStorage.setItem(LS_PREFIX + "activeCategory", categoryId);
  localStorage.setItem(LS_PREFIX + "lastActiveTab:" + categoryId, tabId);

  pushBreadcrumb(categoryId, tabId);
  if (opts.pushNav !== false) pushNavStack(categoryId, tabId);

  renderTabBar(categoryId);
  highlightActive();
  sendVisibleIfChanged(tabId);
  entry.el.focus();
}

function findTab(categoryId, tabId) {
  const cat = state.tabsConfig.categories.find(c => c.id === categoryId);
  return cat ? cat.tabs.find(t => t.id === tabId) : null;
}

function pushBreadcrumb(category, tab) {
  const key = category + ":" + tab;
  state.breadcrumb = state.breadcrumb.filter(k => k !== key);
  state.breadcrumb.unshift(key);
  if (state.breadcrumb.length > 5) state.breadcrumb.length = 5;
  saveBreadcrumb();
}

function pushNavStack(category, tab) {
  // discard forward region
  state.navStack = state.navStack.slice(0, state.navIndex + 1);
  state.navStack.push({category, tab});
  if (state.navStack.length > 50) state.navStack.shift();
  state.navIndex = state.navStack.length - 1;
}

function navBack() {
  if (state.navIndex <= 0) return;
  state.navIndex--;
  const {category, tab} = state.navStack[state.navIndex];
  switchTo(category, tab, {pushNav: false});
}

function navForward() {
  if (state.navIndex >= state.navStack.length - 1) return;
  state.navIndex++;
  const {category, tab} = state.navStack[state.navIndex];
  switchTo(category, tab, {pushNav: false});
}

function applyBreadcrumbGlow() {
  document.querySelectorAll(".tab-btn, .category-btn").forEach(b => {
    b.style.removeProperty("--glow");
    b.classList.remove("history-1","history-2","history-3","history-4","history-5","is-active");
  });
  state.breadcrumb.forEach((key, i) => {
    const [cat, tab] = key.split(":");
    const tabBtn = document.querySelector(`.tab-btn[data-tab-id="${tab}"]`);
    const catBtn = document.querySelector(`.category-btn[data-category-id="${cat}"]`);
    const cls = i === 0 ? "is-active" : "history-" + i;
    if (tabBtn) tabBtn.classList.add(cls);
    if (catBtn) catBtn.classList.add(cls);
  });
}

function highlightActive() {
  document.querySelectorAll(".category-btn").forEach(b =>
    b.setAttribute("aria-selected", b.dataset.categoryId === state.activeCategory ? "true" : "false"));
  document.querySelectorAll(".tab-btn").forEach(b =>
    b.setAttribute("aria-selected", b.dataset.tabId === state.activeTab ? "true" : "false"));
}

function sendVisibleIfChanged(tabId) {
  if (state.lastVisibleTab === tabId) return;
  state.lastVisibleTab = tabId;
  const entry = state.iframes.get(tabId);
  if (entry && entry.el.contentWindow) {
    try {
      entry.el.contentWindow.postMessage({type: "tauri-shell:visible"}, ORIGIN);
    } catch (_) {}
  }
}

function switchAndSend(target, payload) {
  const entry = state.iframes.has(target.tab)
    ? state.iframes.get(target.tab)
    : mountIframe(findTab(target.category, target.tab));
  // queue payload (max PENDING_MAX, drop oldest)
  entry.pending.push(payload);
  if (entry.pending.length > PENDING_MAX) entry.pending.shift();

  switchTo(target.category, target.tab);

  if (entry.ready) {
    flushPending(target.tab);
  } else {
    setTimeout(() => {
      if (!entry.ready) {
        entry.pending = [];
        showToast("Bridge の起動に失敗しました");
      }
    }, READY_TIMEOUT_MS);
  }
}

function flushPending(tabId) {
  const entry = state.iframes.get(tabId);
  if (!entry || !entry.el.contentWindow) return;
  while (entry.pending.length) {
    const payload = entry.pending.shift();
    try {
      entry.el.contentWindow.postMessage({type: "bridge:receive", payload}, ORIGIN);
    } catch (e) {
      console.error("[tauri-shell] flush failed", e);
    }
  }
}

function reloadTab(tabId) {
  const entry = state.iframes.get(tabId);
  if (!entry) return;
  const tab = findTabById(tabId);
  if (!tab) return;
  entry.el.remove();
  state.iframes.delete(tabId);
  // re-mount and (if active) show
  const fresh = mountIframe(tab);
  if (state.activeTab === tabId) {
    fresh.el.style.display = "block";
    state.lastVisibleTab = null;
    sendVisibleIfChanged(tabId);
  }
}

function findTabById(tabId) {
  for (const cat of state.tabsConfig.categories) {
    const t = cat.tabs.find(t => t.id === tabId);
    if (t) return t;
  }
  return null;
}

function attachMessageHandlers() {
  window.addEventListener("message", (e) => {
    if (e.origin !== ORIGIN) return;
    const msg = e.data || {};
    switch (msg.type) {
      case "tauri-shell:ready": {
        const entry = state.iframes.get(msg.tab);
        if (entry && !entry.ready) {
          entry.ready = true;
          flushPending(msg.tab);
        }
        break;
      }
      case "tauri-shell:switch-and-send":
        switchAndSend(msg.target, msg.payload);
        break;
      case "tauri-shell:shortcut":
        handleShortcut(msg.key, msg.modifiers);
        break;
    }
  });
}

function attachKeyHandlers() {
  window.addEventListener("keydown", (e) => {
    const handled = handleShortcutEvent(e);
    if (handled) e.preventDefault();
  });
}

function handleShortcutEvent(e) {
  if (e.ctrlKey && !e.shiftKey && !e.altKey && /^[1-4]$/.test(e.key)) {
    selectCategoryByIndex(parseInt(e.key, 10) - 1);
    return true;
  }
  if (e.ctrlKey && e.key === "Tab") {
    cycleTab(e.shiftKey ? -1 : 1);
    return true;
  }
  if (e.altKey && e.key === "ArrowLeft") { navBack(); return true; }
  if (e.altKey && e.key === "ArrowRight") { navForward(); return true; }
  return false;
}

function handleShortcut(key, modifiers) {
  const fake = {key, ctrlKey: !!modifiers.ctrl, shiftKey: !!modifiers.shift, altKey: !!modifiers.alt};
  handleShortcutEvent(fake);
}

function selectCategoryByIndex(idx) {
  const cat = state.tabsConfig.categories[idx];
  if (!cat) return;
  const lastTab = localStorage.getItem(LS_PREFIX + "lastActiveTab:" + cat.id) || cat.tabs[0].id;
  switchTo(cat.id, lastTab);
}

function cycleTab(direction) {
  const cat = state.tabsConfig.categories.find(c => c.id === state.activeCategory);
  if (!cat) return;
  const idx = cat.tabs.findIndex(t => t.id === state.activeTab);
  const next = (idx + direction + cat.tabs.length) % cat.tabs.length;
  switchTo(cat.id, cat.tabs[next].id);
}

function findTabByUrl(pathname) {
  if (!state.tabsConfig) return null;
  for (const cat of state.tabsConfig.categories) {
    for (const tab of cat.tabs) {
      const tabPath = tab.url.replace(/\/$/, '');
      if (tabPath === pathname.replace(/\/$/, '') || pathname.startsWith(tabPath + '/')) {
        return { category: cat.id, tab: tab.id };
      }
    }
  }
  return null;
}

function attachExtLauncherNavInterceptor() {
  document.addEventListener('click', (e) => {
    const link = e.target.closest('a.ext-launcher-card, a.ext-launcher-child-link, .ext-launcher-footer a');
    if (!link || !link.href) return;
    let url;
    try { url = new URL(link.href); } catch { return; }
    if (url.hostname !== '127.0.0.1') return;
    e.preventDefault();

    // Close extension launcher overlay
    document.querySelectorAll('.ext-launcher-overlay').forEach(o => o.classList.remove('open'));
    document.body.style.overflow = '';

    // Navigate: use existing tab if URL matches, otherwise load in active iframe
    const match = findTabByUrl(url.pathname);
    if (match) {
      switchTo(match.category, match.tab);
    } else {
      const entry = state.iframes.get(state.activeTab);
      if (entry) {
        entry.el.src = url.pathname + url.search + url.hash;
        entry.ready = false;
        entry.pending = [];
      }
    }
  }, true);
}

init();

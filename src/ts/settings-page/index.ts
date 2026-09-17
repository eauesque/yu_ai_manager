import { loadConfig, loadTomlConfig, loadLegacyMigrationStatus } from './config-form';
import { loadServerStatus } from './server-status';
import { initTheme } from './theme-init';
import { installSettingsPageWindowBridges } from './bridges';
import { bindRfsInputs } from './security-actions';
import { createPagePerfTracker } from '../shared/page-perf';
import { saveSettings } from './save';

// bridgeNav localStorage - migrated from _scripts.html inline JS
(function () {
  const cb = document.getElementById('cfg-bridge-nav-newtab') as HTMLInputElement | null;
  if (!cb) return;
  cb.checked = localStorage.getItem('bridgeNav:openInNewTab') === 'true';
  cb.addEventListener('change', function () {
    localStorage.setItem('bridgeNav:openInNewTab', cb.checked ? 'true' : 'false');
  });
})();

installSettingsPageWindowBridges();
const _perf = createPagePerfTracker('settings');
_perf.markOnce('module_ready');

// --- Category constants ---
const CAT_IDS = [
  'cat-server', 'cat-scan', 'cat-tagging',
  'cat-appearance', 'cat-auth', 'cat-dev',
] as const;
type CatId = typeof CAT_IDS[number];

// Categories that have a collectForm() save bar
const CONFIG_SAVE_CATS = new Set<CatId>([
  'cat-server', 'cat-scan', 'cat-tagging', 'cat-appearance', 'cat-dev',
]);

// --- Lazy loaders ---
type CatLoader = () => void | Promise<void>;
const _loadedCats = new Set<CatId>();
let _disconnectLogStream: (() => void) | null = null;

function _runCatLoader(catId: CatId, loader: CatLoader): void {
  if (_loadedCats.has(catId)) return;
  _loadedCats.add(catId);
  void Promise.resolve()
    .then(loader)
    .catch((err) => {
      _loadedCats.delete(catId);
      console.warn(`[settings] ${catId} load failed:`, err);
    });
}

const _catLoaders: Record<CatId, CatLoader> = {
  'cat-server': async () => { /* server status loaded at boot */ },
  'cat-scan': async () => {
    const mod = await import('./roots-extensions');
    mod.loadScanRoots();
  },
  'cat-tagging': async () => {
    const [taggerMod, tagDictMod] = await Promise.all([
      import('./tagger-servers'),
      import('./tag-dict-tab'),
    ]);
    taggerMod.loadTaggerServers();
    tagDictMod.initTagDictTab();
  },
  'cat-appearance': async () => {
    const [extMod, uiMod] = await Promise.all([
      import('./extensions-tab'),
      import('./ui-tab'),
    ]);
    extMod.loadExtensionsFull();
    uiMod.initUiTab();
  },
  'cat-auth': async () => {
    const [apiKeysMod, gatewayMod, snsMod, secretsMod] = await Promise.all([
      import('./apikeys-ui'),
      import('./gateway-keys'),
      import('./sns-tab'),
      import('./secrets-tab'),
    ]);
    apiKeysMod.loadApiKeys();
    gatewayMod.loadGatewayKeys();
    gatewayMod.initGatewayKeysTab();
    snsMod.initSnsTab();
    snsMod.initBskyMonitor();
    secretsMod.loadSecretsStatus();
  },
  'cat-dev': async () => {
    const [logMod, nativeMod] = await Promise.all([
      import('./logs-tab'),
      import('./native-logs-panel'),
    ]);
    _disconnectLogStream = () => {
      logMod.disconnectLogStream();
      nativeMod.disconnect();
    };
    logMod.initLogTab();
    void nativeMod.init();
  },
};

// --- Category activation ---
let _currentCat: CatId = 'cat-server';

function _activateCat(catId: CatId): void {
  document.querySelectorAll<HTMLElement>('[data-settings-cat]').forEach((el) => {
    const active = el.dataset.settingsCat === catId;
    el.classList.toggle('tools-sidebar-item--active', active);
    el.setAttribute('aria-selected', active ? 'true' : 'false');
  });
  document.querySelectorAll<HTMLElement>('[data-settings-panel]').forEach((el) => {
    const active = el.dataset.settingsPanel === catId;
    el.setAttribute('aria-hidden', active ? 'false' : 'true');
    (el as HTMLElement).style.display = active ? '' : 'none';
  });
}

function _handleCatShown(catId: CatId): void {
  if (catId !== 'cat-dev') _disconnectLogStream?.();
  _runCatLoader(catId, _catLoaders[catId]);
  document.dispatchEvent(new CustomEvent('settings:cat-shown', { detail: { catId } }));
  _perf.markOnce(`cat_${catId}_started`);
}

function _switchCat(catId: CatId): void {
  _currentCat = catId;
  _activateCat(catId);
  _handleCatShown(catId);
  history.replaceState(null, '', `#${catId}`);
}

// --- DirtyTracker ---
const _dirtyByPanel: Partial<Record<CatId, boolean>> = {};

function _isDirtyAnywhere(): boolean {
  return Object.values(_dirtyByPanel).some(Boolean);
}

function _setDirty(catId: CatId, dirty: boolean): void {
  _dirtyByPanel[catId] = dirty;
  const hint = document.getElementById(`save-hint-${catId}`);
  if (hint) hint.hidden = !dirty;
}

function _initDirtyTracker(): void {
  document.addEventListener('change', (e) => {
    const target = e.target as HTMLElement;
    if (!target.closest('[data-settings-field]')) return;
    const panel = target.closest<HTMLElement>('[data-settings-panel]');
    if (!panel) return;
    const raw = panel.dataset.settingsPanel;
    if (!raw || !CAT_IDS.includes(raw as CatId)) return;
    const catId = raw as CatId;
    if (!CONFIG_SAVE_CATS.has(catId)) return;
    _setDirty(catId, true);
  });
}

// --- UnsavedGuard ---
window.addEventListener('beforeunload', (e) => {
  if (_isDirtyAnywhere()) {
    e.preventDefault();
    e.returnValue = '';
  }
});

// --- SidebarNav ---
function _onSidebarClick(e: Event): void {
  const target = (e.target as HTMLElement).closest<HTMLElement>('[data-settings-cat]');
  if (!target) return;
  const catId = target.dataset.settingsCat as CatId;
  if (!CAT_IDS.includes(catId)) return;
  if (_isDirtyAnywhere() && _currentCat !== catId) {
    if (!confirm('このカテゴリの変更を破棄しますか？')) return;
    CAT_IDS.forEach((id) => _setDirty(id, false));
  }
  e.preventDefault();
  _switchCat(catId);
}

// --- CategorySaver ---
function _initCategorySavers(): void {
  CONFIG_SAVE_CATS.forEach((catId) => {
    const btn = document.getElementById(`save-btn-${catId}`);
    if (!btn) return;
    btn.addEventListener('click', async () => {
      try {
        const { ok } = await saveSettings({
          btnId: `save-btn-${catId}`,
          statusId: `save-status-${catId}`,
        });
        if (ok) _setDirty(catId, false);
      } catch {
        const statusEl = document.getElementById(`save-status-${catId}`);
        if (statusEl) statusEl.textContent = '保存に失敗しました';
      }
    });
  });
}

// --- HashNav ---
function _activateCatFromHash(): void {
  const m = location.hash.match(/^#(cat-[a-z-]+)$/);
  const catId = (m && CAT_IDS.includes(m[1] as CatId)) ? (m[1] as CatId) : 'cat-server';
  _switchCat(catId);
}

window.addEventListener('hashchange', () => {
  const m = location.hash.match(/^#(cat-[a-z-]+)$/);
  if (m && CAT_IDS.includes(m[1] as CatId)) _switchCat(m[1] as CatId);
});

// --- Appearance (existing DOMContentLoaded pattern) ---
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    void import('./appearance').then((mod) => mod.initAppearanceTab());
  });
} else {
  void import('./appearance').then((mod) => mod.initAppearanceTab());
}

// --- Boot sequence ---
initTheme();
bindRfsInputs();
loadConfig();
loadTomlConfig();
loadLegacyMigrationStatus();
loadServerStatus();
_perf.markOnce('server_bootstrap_started');

document.addEventListener('tr-runtime:ready', () => {
  loadServerStatus();
  if (_loadedCats.has('cat-appearance')) {
    void import('./extensions-tab').then((mod) => mod.loadExtensionsFull());
  }
});

const _sidebar = document.getElementById('settingsSidebarNav');
if (_sidebar) _sidebar.addEventListener('click', _onSidebarClick);

_initDirtyTracker();
_initCategorySavers();

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _activateCatFromHash);
} else {
  _activateCatFromHash();
}

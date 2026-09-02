import '../floating-grid/index';
import '../i18n/index';
import '../dock/index';
import '../meta-renderer/index';
import '../condition-builder/index';
import '../runtime-pre/index';
import '../main/index';
import '../search-results/index';
import '../prompt-highlight/index';
import '../runtime-tools-ui/index';
import '../a11y/index';
import '../runtime-init/index';
import '../keyboard/index';
import '../scan-banner/index';
import '../context-menu/index';
import '../container-view/index';
import '../shared/background-preload';
import '../dock-zoom/index';
import { installWindowApi } from '../shared/window-api';

let _semanticModulePromise: Promise<typeof import('../semantic-search/index')> | null = null;
let _bossLockModulePromise: Promise<typeof import('../boss-lock/index')> | null = null;
let _detailModalModulePromise: Promise<typeof import('../detail-modal/index')> | null = null;
let _unionModulePromise: Promise<typeof import('../union-search/index')> | null = null;
let _tagEditModulePromise: Promise<typeof import('../tag-edit/index')> | null = null;
let _snsShareModulePromise: Promise<typeof import('../sns-share/index')> | null = null;

function _loadSemanticModule() {
  if (!_semanticModulePromise) {
    _semanticModulePromise = import('../semantic-search/index');
  }
  return _semanticModulePromise;
}

function _loadBossLockModule() {
  if (!_bossLockModulePromise) {
    _bossLockModulePromise = import('../boss-lock/index');
  }
  return _bossLockModulePromise;
}

async function _withBossLockApi<T>(fn: (api: any) => T | Promise<T>): Promise<T | undefined> {
  await _loadBossLockModule();
  const api = (window as any).bossLockApi;
  if (!api || typeof api !== 'object') return undefined;
  return fn(api);
}

function _loadDetailModalModule() {
  if (!_detailModalModulePromise) {
    _detailModalModulePromise = import('../detail-modal/index');
  }
  return _detailModalModulePromise;
}

async function _withDetailModalApi<T>(fn: (api: any) => T | Promise<T>): Promise<T | undefined> {
  await _loadDetailModalModule();
  const api = (window as any).detailModalApi;
  if (!api || typeof api !== 'object') return undefined;
  return fn(api);
}

function _detailRuntimeControl(name: string) {
  return (...args: any[]) => _withDetailModalApi((api) => {
    const target = api.runtimeControls?.[name];
    if (typeof target === 'function') return target(...args);
    return undefined;
  });
}

function _loadUnionModule() {
  if (!_unionModulePromise) {
    _unionModulePromise = import('../union-search/index');
  }
  return _unionModulePromise;
}

function _loadTagEditModule() {
  if (!_tagEditModulePromise) {
    _tagEditModulePromise = import('../tag-edit/index');
  }
  return _tagEditModulePromise;
}

function _loadSnsShareModule() {
  if (!_snsShareModulePromise) {
    _snsShareModulePromise = import('../sns-share/index');
  }
  return _snsShareModulePromise;
}

function _scheduleIdleImport(loader: () => Promise<unknown>, timeout = 2500): void {
  const run = (): void => {
    if (document.hidden) return;
    void loader().catch(() => {});
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      if ('requestIdleCallback' in window) {
        window.requestIdleCallback(run, { timeout });
      } else {
        setTimeout(run, 1200);
      }
    }, { once: true });
    return;
  }

  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(run, { timeout });
    return;
  }

  setTimeout(run, 1200);
}

installWindowApi('bossLockApi', {
  activateQuickLock: () => _withBossLockApi((api) => api.activateQuickLock?.()),
  hideBossMode: () => _withBossLockApi((api) => api.hideBossMode?.()),
  stopAllMediaPlayback: () => _withBossLockApi((api) => api.stopAllMediaPlayback?.()),
}, {
  activateQuickLock: 'activateQuickLock',
  hideBossMode: 'hideBossMode',
  stopAllMediaPlayback: 'stopAllMediaPlayback',
});

installWindowApi('detailModalApi', {
  async showDetail(id: number, opts?: any): Promise<unknown> {
    return _withDetailModalApi((api) => api.showDetail?.(id, opts));
  },
  async closeModal(): Promise<unknown> {
    return _withDetailModalApi((api) => api.closeModal?.());
  },
  async copyToClipboard(text: string): Promise<boolean> {
    const result = await _withDetailModalApi((api) => api.copyToClipboard?.(text));
    return !!result;
  },
  async searchByTag(tag: string): Promise<unknown> {
    return _withDetailModalApi((api) => api.searchByTag?.(tag));
  },
  initOcrTab: (fileId: number) => _withDetailModalApi((api) => api.initOcrTab?.(fileId)),
  initS2tTab: (fileId: number) => _withDetailModalApi((api) => api.initS2tTab?.(fileId)),
  initAnnotationsTab: (fileId: number) => _withDetailModalApi((api) => api.initAnnotationsTab?.(fileId)),
  initAnalysisTraceTab: (fileId: number) => _withDetailModalApi((api) => api.initAnalysisTraceTab?.(fileId)),
  runtimeControls: {
    toggleImmersiveMode: _detailRuntimeControl('toggleImmersiveMode'),
    applyImmersiveIfStored: _detailRuntimeControl('applyImmersiveIfStored'),
    toggleModalInfo: _detailRuntimeControl('toggleModalInfo'),
    collapseControlsBar: _detailRuntimeControl('collapseControlsBar'),
    expandControlsBar: _detailRuntimeControl('expandControlsBar'),
    cycleModalPlaybackRate: _detailRuntimeControl('cycleModalPlaybackRate'),
    openRandomResult: _detailRuntimeControl('openRandomResult'),
    rewindModalMedia: _detailRuntimeControl('rewindModalMedia'),
    closeModal: _detailRuntimeControl('closeModal'),
    toggleMediaResumeMode: _detailRuntimeControl('toggleMediaResumeMode'),
    toggleModalRepeat: _detailRuntimeControl('toggleModalRepeat'),
    updateRepeatButtonLabel: _detailRuntimeControl('updateRepeatButtonLabel'),
    toggleModalMediaPlayback: _detailRuntimeControl('toggleModalMediaPlayback'),
    updateResumeModeButtonLabel: _detailRuntimeControl('updateResumeModeButtonLabel'),
    forwardModalMedia: _detailRuntimeControl('forwardModalMedia'),
    toggleModalMute: _detailRuntimeControl('toggleModalMute'),
    initModalMediaUi: _detailRuntimeControl('initModalMediaUi'),
    updateModalSeekUi: _detailRuntimeControl('updateModalSeekUi'),
    initFilmstripHover: _detailRuntimeControl('initFilmstripHover'),
    toggleSpreadView: _detailRuntimeControl('toggleSpreadView'),
    toggleSpreadDirection: _detailRuntimeControl('toggleSpreadDirection'),
    reloadCurrentDetail: _detailRuntimeControl('reloadCurrentDetail'),
    toggleKbGuide: _detailRuntimeControl('toggleKbGuide'),
  },
}, {
  detailModalRuntimeControls: 'runtimeControls',
});

installWindowApi('unionSearchApi', {
  async runUnionSearch(): Promise<void> {
    const mod = await _loadUnionModule();
    return mod.runUnionSearch();
  },
});

installWindowApi('tagEditApi', {
  async addUserTag(fileId: number, tag?: string): Promise<void> {
    const mod = await _loadTagEditModule();
    return mod.addUserTag(fileId, tag);
  },
  async removeUserTag(fileId: number, tag: string): Promise<void> {
    const mod = await _loadTagEditModule();
    return mod.removeUserTag(fileId, tag);
  },
  handleTagInputKey(e: KeyboardEvent, fileId: number): void {
    void _loadTagEditModule().then((mod) => {
      mod.handleTagInputKey(e, fileId);
    }).catch(() => {});
  },
  fetchSuggestionsForTagInput(input: HTMLInputElement): void {
    void _loadTagEditModule().then((mod) => {
      mod.fetchSuggestionsForTagInput(input);
    }).catch(() => {});
  },
}, {
  addUserTag: 'addUserTag',
  removeUserTag: 'removeUserTag',
  handleTagInputKey: 'handleTagInputKey',
  fetchSuggestionsForTagInput: '_fetchSuggestionsForTagInput',
});

installWindowApi('snsShareApi', {
  async showSnsShare(fileId: number): Promise<void> {
    const mod = await _loadSnsShareModule();
    return mod.showSnsShareModal(fileId);
  },
  async closeSnsShare(): Promise<void> {
    const mod = await _loadSnsShareModule();
    mod.closeSnsShareModal();
  },
}, {
  showSnsShare: 'showSnsShare',
  closeSnsShare: 'closeSnsShare',
});

_scheduleIdleImport(_loadSemanticModule);

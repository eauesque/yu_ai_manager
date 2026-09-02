/**
 * Bridge Wildcard Cache — singleton that fetches wildcard data once
 * from /ext/prompt-sim/wildcards and caches it for autocomplete + browser.
 */

export interface WildcardData {
  [name: string]: string[];
}

let _wildcards: WildcardData | null = null;
let _names: string[] | null = null;
let _dirsConfigured: boolean | null = null;
let _pending: Promise<void> | null = null;

function doFetch(): Promise<void> {
  if (_wildcards) return Promise.resolve();
  if (_pending) return _pending;

  _pending = fetch('/ext/prompt-sim/wildcards')
    .then((r) => r.json())
    .then((data: { error?: string; wildcards?: WildcardData; dirs?: string[] }) => {
      if (data.error) {
        _wildcards = {};
        _dirsConfigured = null;
      } else {
        _wildcards = data.wildcards || {};
        _dirsConfigured = Array.isArray(data.dirs) ? data.dirs.length > 0 : null;
      }
      // Merge Wildcard Manager data from localStorage
      _mergeLocalWildcards();
      _names = Object.keys(_wildcards).sort();
      _pending = null;
    })
    .catch(() => {
      _wildcards = {};
      _dirsConfigured = null;
      _mergeLocalWildcards();
      _names = Object.keys(_wildcards).sort();
      _pending = null;
    });
  return _pending;
}

function _mergeLocalWildcards(): void {
  try {
    const wmRaw = localStorage.getItem('wm_wildcards');
    if (!wmRaw || !_wildcards) return;
    const wmData = JSON.parse(wmRaw) as Record<string, unknown>;
    for (const k of Object.keys(wmData)) {
      if (Array.isArray(wmData[k])) {
        _wildcards[k] = wmData[k] as string[];
      }
    }
  } catch (_) {
    // ignore parse errors
  }
}

function getNames(): string[] {
  return _names || [];
}

function getData(): WildcardData {
  return _wildcards || {};
}

function isDirsConfigured(): boolean | null {
  return _dirsConfigured;
}

function invalidate(): void {
  _wildcards = null;
  _names = null;
  _dirsConfigured = null;
  _pending = null;
}

export const BridgeWildcardCache = {
  fetch: doFetch,
  getNames,
  getData,
  isDirsConfigured,
  invalidate,
};

// Auto-invalidate when WC Manager updates localStorage from another tab
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e: StorageEvent) => {
    if (e.key === 'wm_wildcards') {
      invalidate();
      doFetch();
    }
  });
}

type MarkMap = Record<string, number>;

declare global {
  interface Window {
    __yuPagePerf?: Record<string, MarkMap>;
  }
}

function _isEnabled(): boolean {
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get('perf') === '1') return true;
    return localStorage.getItem('yu_page_perf') === '1';
  } catch {
    return false;
  }
}

export interface PagePerfTracker {
  mark(label: string): void;
  markOnce(label: string): void;
}

export function createPagePerfTracker(page: string): PagePerfTracker {
  const enabled = _isEnabled();
  const startedAt = performance.now();
  const seen = new Set<string>();

  if (enabled) {
    window.__yuPagePerf ||= {};
    window.__yuPagePerf[page] ||= {};
  }

  function _record(label: string): void {
    const elapsed = Math.round(performance.now() - startedAt);
    if (!enabled) return;
    window.__yuPagePerf![page][label] = elapsed;
    console.info(`[page-perf] ${page}:${label} ${elapsed}ms`);
  }

  return {
    mark(label: string): void {
      _record(label);
    },
    markOnce(label: string): void {
      if (seen.has(label)) return;
      seen.add(label);
      _record(label);
    },
  };
}

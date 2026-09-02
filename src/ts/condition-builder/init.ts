import { setActiveConditions, renderActiveConditions } from './state';

function restoreConditions(): void {
  try {
    const saved = localStorage.getItem('tagdb_active_conditions');
    if (saved) {
      const keys = JSON.parse(saved) as string[];
      if (Array.isArray(keys) && !keys.includes('sort')) {
        keys.unshift('sort');
      }
      setActiveConditions(keys);
      return;
    }
  } catch (_e) { /* ignore */ }
  setActiveConditions(['sort']);
}

// Auto-run on load — but only after the entry point has set up bridges
export function autoInit(): void {
  restoreConditions();
}

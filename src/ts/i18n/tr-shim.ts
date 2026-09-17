/**
 * tr-shim — Early fallback for tr() before adaptive runtime loads.
 * Once main-adaptive.js loads, it overwrites this with the real version.
 * Converted from static/js/i18n/tr-shim.js
 */

import { getI18nDictionary } from './runtime-state';

if (typeof window.tr !== 'function') {
  window.tr = function (path: string, a?: unknown, b?: unknown): string {
    // Try runtime if available
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const fn = (window as any).adaptiveRuntime && (window as any).adaptiveRuntime.tr;
    if (typeof fn === 'function') return fn(path, a, b);
    // Try flat i18n dict (set by applyTranslations in core-shared.ts)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const flatDict = getI18nDictionary();
    if (flatDict && Object.prototype.hasOwnProperty.call(flatDict, path)) return String(flatDict[path]);
    // Fallback: return second arg (if string) or path
    if (typeof a === 'string') return a;
    if (typeof b === 'string') return b;
    return String(path || '');
  };
}

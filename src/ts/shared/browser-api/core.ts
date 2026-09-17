import { pickFunction } from './common';
import type { ApiFetchOpts } from '../../main/api-utils';
export function getAppApi() {
  return {
    apiFetch: pickFunction(
      window.appApi?.apiFetch,
      window.apiFetch,
      (path: string, opts?: ApiFetchOpts) => fetch(path, opts),
    ) as (path: string, opts?: ApiFetchOpts) => Promise<Response>,
    apiUrl: pickFunction(
      window.appApi?.apiUrl,
      window.apiUrl,
      (path: string) => path,
    ) as (path: string) => string,
    clamp: pickFunction(
      window.appApi?.clamp,
      window.clamp,
      (n: number) => n,
    ) as (n: number, min: number, max: number) => number,
    escapeHtml: pickFunction(
      window.appApi?.escapeHtml,
      window.escapeHtml,
      (text: unknown) => String(text ?? ''),
    ) as (text: unknown) => string,
    decodeHtmlEntities: pickFunction(
      window.appApi?.decodeHtmlEntities,
      undefined,
      (text: string) => { const ta = document.createElement('textarea'); ta.innerHTML = text; return ta.value; },
    ) as (text: string) => string,
    getAdaptiveCatalog: pickFunction(
      window.appApi?.getAdaptiveCatalog,
      undefined,
      () => ({}),
    ) as (type: string) => Record<string, any>,
    getStartupMode: pickFunction(
      window.appApi?.getStartupMode,
      undefined,
      () => '',
    ) as () => string,
    pickAdaptiveMessage: pickFunction(
      window.appApi?.pickAdaptiveMessage,
      undefined,
      () => '',
    ) as (catalog: Record<string, any>, slot?: string) => string,
    startLoadingTips: pickFunction(
      window.appApi?.startLoadingTips,
      undefined,
      () => undefined,
    ) as () => void,
    stopLoadingTips: pickFunction(
      window.appApi?.stopLoadingTips,
      undefined,
      () => undefined,
    ) as () => void,
    tr: pickFunction(
      window.appApi?.tr,
      window.tr,
      (path: string, fallback?: unknown) => typeof fallback === 'string' ? fallback : path,
    ) as (path: string, a?: unknown, b?: unknown) => string,
    setResultsCount: pickFunction(
      window.appApi?.setResultsCount,
      window.setResultsCount,
      () => undefined,
    ) as (text: string | number) => void,
    updateKeyboardGuideVisibility: pickFunction(
      window.appApi?.updateKeyboardGuideVisibility,
      window.updateKeyboardGuideVisibility,
      () => undefined,
    ) as () => void,
    reportError: pickFunction(
      window.appApi?.reportError,
      undefined,
      // Stub: error-reporter not installed on this page (e.g. share page).
      // detail is intentionally omitted — stub has no access to sanitizeDetail.
      (component: string, error: unknown, _detail?: Record<string, unknown>) => {
        console.warn('[reportError:stub]', component, error);
      },
    ) as (component: string, error: unknown, detail?: Record<string, unknown>) => void,
  };
}

export function getNavApi() {
  return {
    showToast: pickFunction(
      window.navApi?.showToast,
      undefined,
      () => undefined,
    ) as (message: string, isError?: boolean) => void,
    sseSubscribe: pickFunction(
      window.navApi?.sseSubscribe,
      undefined,
      () => undefined,
    ) as typeof window.sseSubscribe,
    sseUnsubscribe: pickFunction(
      window.navApi?.sseUnsubscribe,
      undefined,
      () => undefined,
    ) as typeof window.sseUnsubscribe,
    activateQuickLockFromNav: pickFunction(
      window.navApi?.activateQuickLockFromNav,
      undefined,
      () => undefined,
    ) as () => void,
  };
}

export function getBossLockApi() {
  return {
    activateQuickLock: pickFunction(
      window.bossLockApi?.activateQuickLock,
      undefined,
      () => undefined,
    ) as () => void,
    hideBossMode: pickFunction(
      window.bossLockApi?.hideBossMode,
      undefined,
      () => undefined,
    ) as () => void,
    stopAllMediaPlayback: pickFunction(
      window.bossLockApi?.stopAllMediaPlayback,
      undefined,
      () => undefined,
    ) as () => void,
  };
}

export function getKeyboardApi() {
  return {
    showKeyboardHelp: pickFunction(
      window.keyboardApi?.showKeyboardHelp,
      window.showKeyboardHelp,
      () => undefined,
    ) as () => void,
    hideKeyboardHelp: pickFunction(
      window.keyboardApi?.hideKeyboardHelp,
      window.hideKeyboardHelp,
      () => undefined,
    ) as () => void,
  };
}

export function getPromptHighlightApi() {
  return {
    highlightPrompt: pickFunction(
      window.promptHighlightApi?.highlightPrompt,
      undefined,
      (prompt: string) => prompt,
    ) as (prompt: string) => string,
  };
}

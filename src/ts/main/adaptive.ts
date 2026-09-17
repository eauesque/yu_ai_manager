/**
 * Adaptive runtime facade — global function wrappers + DOMContentLoaded init.
 * Converted from static/js/main/main-adaptive.js
 *
 * These global functions delegate to window.adaptiveRuntime, which is set up
 * by the index.ts entry point. This module also handles event listeners for
 * i18n:changed and DOMContentLoaded.
 */

import { getCurrentLang } from './adaptive-runtime-buckets';
import {
  getAdaptiveCatalog,
  tr,
  trList,
  refreshAdaptiveMessages,
  refreshUiRuntime,
} from './adaptive-runtime-i18n';
import {
  setResultsCount,
  renderResultKeyboardGuide,
  updateKeyboardGuideVisibility,
  pickAdaptiveMessage,
  startLoadingTips,
  stopLoadingTips,
} from './adaptive-runtime-ui';
import { renderConditionMenu } from '../condition-builder/menu-core';
import { renderActiveConditions } from '../condition-builder/state';

export {
  getCurrentLang,
  getAdaptiveCatalog,
  tr,
  trList,
  setResultsCount,
  renderResultKeyboardGuide,
  updateKeyboardGuideVisibility,
  pickAdaptiveMessage,
  startLoadingTips,
  stopLoadingTips,
  refreshAdaptiveMessages,
  refreshUiRuntime,
};

export function applyAdaptiveRuntimeUi(): void {
  renderActiveConditions();
  renderConditionMenu();
  renderResultKeyboardGuide();
  updateKeyboardGuideVisibility();
}

document.addEventListener('DOMContentLoaded', () => {
  const lang = getCurrentLang();
  refreshAdaptiveMessages(lang).catch(() => {});
  refreshUiRuntime(lang).then(applyAdaptiveRuntimeUi).catch(() => {});
});

document.addEventListener('i18n:changed', ((ev: CustomEvent<{ lang: string }>) => {
  const lang = ev && ev.detail ? ev.detail.lang : getCurrentLang();
  refreshAdaptiveMessages(lang).catch(() => {});
  refreshUiRuntime(lang).then(applyAdaptiveRuntimeUi).catch(() => {});
}) as EventListener);

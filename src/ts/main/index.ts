/**
 * Main utilities entry point — bundles showToast, API utils, adaptive runtime.
 */

import { getStartupMode, setStartupMode } from './main';
import { apiUrl, apiFetch, escapeHtml, decodeHtmlEntities, clamp } from './api-utils';
import './adaptive-runtime-state';
import './adaptive-runtime-buckets';
import './adaptive-runtime-i18n';
import {
  setResultsCount,
  renderResultKeyboardGuide,
  updateKeyboardGuideVisibility,
  pickAdaptiveMessage,
  startLoadingTips,
  stopLoadingTips,
} from './adaptive-runtime-ui';
import {
  getCurrentLang,
  getAdaptiveCatalog,
  tr,
  trList,
  refreshAdaptiveMessages,
  refreshUiRuntime,
  applyAdaptiveRuntimeUi,
} from './adaptive';
import { installWindowApi } from '../shared/window-api';
import { reportCaughtError } from '../shared/error-reporter-events';

// Bridge: global functions used by onclick handlers and cross-module callers
// NOTE: showToast is bridged in nav/index.ts so it's available on ALL pages
//       (including Extension blueprint pages that don't load main-app.js)
installWindowApi('appApi', {
  getStartupMode,
  setStartupMode,
  apiUrl,
  apiFetch,
  escapeHtml,
  decodeHtmlEntities,
  clamp,
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
  applyAdaptiveRuntimeUi,
  reportError: reportCaughtError,
}, {
  // Legacy alias: window.tr() is the public i18n API for extension inline scripts (300+ references)
  tr: 'tr',
});

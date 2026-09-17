/**
 * Adaptive runtime state — shared mutable state for the adaptive message system.
 * Converted from static/js/main/main-adaptive-runtime-state.js
 */

export interface AdaptiveMessages {
  loadingTipsByTime: Record<string, string[]>;
  emptySearchCheersByTime: Record<string, string[]>;
}

export interface AdaptiveRuntimeState {
  ADAPTIVE_MESSAGES_VERSION: string;
  UI_RUNTIME_VERSION: string;
  DEFAULT_ADAPTIVE_MESSAGES: AdaptiveMessages;
  DEFAULT_UI_RUNTIME: Record<string, unknown>;
  adaptiveMessages: AdaptiveMessages;
  uiRuntimeTexts: Record<string, unknown>;
  lastMessageBySlot: Record<string, string>;
  // Added by buckets module
  getTimeBucket: (now?: Date) => string;
  getSeasonBucket: (now?: Date) => string;
  getDayTypeBucket: (now?: Date) => string;
  getMonthEventBucket: (now?: Date) => string;
  getCurrentLang: () => string;
  // Added by i18n module
  refreshAdaptiveMessages: (lang: string) => Promise<void>;
  refreshUiRuntime: (lang: string) => Promise<void>;
  getAdaptiveCatalog: (type: string) => Record<string, string[]>;
  tr: (path: string, a?: unknown, b?: unknown) => string;
  trList: (path: string, fallback?: string[]) => string[];
}

const DEFAULT_ADAPTIVE_MESSAGES: AdaptiveMessages = {
  loadingTipsByTime: { common: [] },
  emptySearchCheersByTime: { common: [] },
};

const DEFAULT_UI_RUNTIME: Record<string, unknown> = {};

export const state: AdaptiveRuntimeState = {
  ADAPTIVE_MESSAGES_VERSION: '20260217a',
  UI_RUNTIME_VERSION: '20260219a',
  DEFAULT_ADAPTIVE_MESSAGES,
  DEFAULT_UI_RUNTIME,
  adaptiveMessages: { ...DEFAULT_ADAPTIVE_MESSAGES },
  uiRuntimeTexts: { ...DEFAULT_UI_RUNTIME },
  lastMessageBySlot: {},
  // Placeholders — filled by subsequent modules
  getTimeBucket: () => 'night',
  getSeasonBucket: () => 'winter',
  getDayTypeBucket: () => 'weekday',
  getMonthEventBucket: () => 'normal_month',
  getCurrentLang: () => 'en',
  refreshAdaptiveMessages: () => Promise.resolve(),
  refreshUiRuntime: () => Promise.resolve(),
  getAdaptiveCatalog: () => ({}),
  tr: (path: string) => path,
  trList: (_path: string, fallback: string[] = []) => fallback,
};

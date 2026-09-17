type WindowApiMap = Record<string, unknown>;

export type PublicBrowserApiNamespace =
  | 'appApi'
  | 'navApi'
  | 'searchResultsApi'
  | 'conditionBuilderApi'
  | 'detailModalApi'
  | 'runtimeToolsApi'
  | 'runtimeInitApi'
  | 'containerViewApi'
  | 'toolsPageApi'
  | 'settingsPageApi'
  | 'extensionsPageApi'
  | 'sharePageApi'
  | 'inspectPageApi'
  | 'scanBannerApi'
  | 'promptHighlightApi'
  | 'keyboardApi'
  | 'bossLockApi'
  | 'unionSearchApi'
  | 'tagEditApi'
  | 'ratingsApi'
  | 'similarApi'
  | 'contextMenuApi'
  | 'floatingGridApi'
  | 'snsShareApi'
  | 'storyPageApi'
  | 'dockApi'
  | 'statsPageApi'
  | 'extensionHealthApi';

export type InternalBrowserApiNamespace =
  | 'runtimePreApi';

export type BrowserApiNamespace =
  | PublicBrowserApiNamespace
  | InternalBrowserApiNamespace;

export function installWindowApi<T extends WindowApiMap>(
  namespace: BrowserApiNamespace,
  api: T,
  legacyAliases: Record<string, keyof T | unknown> = {},
): T {
  const win = window as unknown as Record<string, unknown>;
  const existing = win[namespace];
  const namespaced =
    existing && typeof existing === 'object'
      ? existing as WindowApiMap
      : {};

  Object.assign(namespaced, api);
  win[namespace] = namespaced;

  for (const [legacyName, source] of Object.entries(legacyAliases)) {
    win[legacyName] =
      typeof source === 'string' && source in namespaced
        ? namespaced[source]
        : source;
  }

  return namespaced as T;
}

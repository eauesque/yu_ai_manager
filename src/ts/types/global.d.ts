/**
 * Window type extensions for cross-bundle communication.
 * After bundle consolidation (31 IIFE → 9 page bundles), only
 * onclick handler functions and minimal cross-bundle state remain.
 */

interface Window {
  /* ---- i18n ---- */
  tr: (path: string, a?: unknown, b?: unknown) => string;

  /* ---- main utilities ---- */
  customConfirm: (message: string, options?: { okText?: string; cancelText?: string; danger?: boolean }) => Promise<boolean>;
  customAlert?: (message: string, options?: { okText?: string }) => Promise<void>;
  customPrompt?: (
    message: string,
    defaultValue?: string | null,
    options?: { okText?: string; cancelText?: string; placeholder?: string; multiline?: boolean },
  ) => Promise<string | null>;
  showToast: (message: string, isError?: boolean) => void;
  openErrorReportModal?: () => void;
  getStartupMode: () => string;
  setStartupMode: (mode: string) => void;
  apiUrl: (path: string) => string;
  apiFetch: (path: string, opts?: RequestInit & { silent?: boolean }) => Promise<Response>;
  escapeHtml: (text: unknown) => string;
  decodeHtmlEntities: (text: string) => string;
  clamp: (n: number, min: number, max: number) => number;

  /* ---- adaptive runtime ---- */
  getCurrentLang: () => string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getAdaptiveCatalog: (type: string) => Record<string, any>;
  trList: (path: string, fallback?: string[]) => string[];
  setResultsCount: (text: string) => void;
  renderResultKeyboardGuide: () => void;
  updateKeyboardGuideVisibility: () => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  pickAdaptiveMessage: (catalog: Record<string, any>, slot?: string) => string;
  startLoadingTips: () => void;
  stopLoadingTips: () => void;
  refreshAdaptiveMessages: (lang: string) => Promise<void>;
  refreshUiRuntime: (lang: string) => Promise<void>;
  applyAdaptiveRuntimeUi: () => void;

  /* ---- condition-builder ---- */
  /* ---- detail-modal ---- */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  detailModalViewer: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  detailModalRuntimeState: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  detailModalRuntimeControls: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  modalDetailState: Record<string, any>;

  /* ---- search-results ---- */
  modalDetailHasMore?: () => boolean;
  modalDetailIsLoading?: () => boolean;
  modalDetailLoadMore?: () => Promise<void>;
  setSearchMode?: (mode: string) => void;
  onRegexToggleChange?: () => void;
  loadStats?: () => Promise<void>;
  showSearchState?: (type: string, message?: string) => void;
  showPartialWarning?: (_total: number, limit: number) => void;
  MAX_DOM_CARDS?: number;
  toggleLiveSearch?: () => void;
  setupResultCardA11y?: () => void;
  ensureSingleTabstopOnResultCards?: (card: HTMLElement) => void;
  announceResultCardStatus?: (card: HTMLElement) => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  _appendResults?: (results: any[], append?: boolean) => void;
  updateExportCsvVisibility?: () => void;
  updateExportCsvLabel?: () => void;
  exportResultsCsv?: () => void;
  exportResultsRecipeJson?: () => void;
  setCsvLimit?: (n: number) => void;
  showCsvLimitDropdown?: (triggerEl: HTMLElement) => void;

  /* ---- runtime-pre ---- */
  openContainerViewForFile?: (fileId: number) => Promise<void>;
  openContainerViewForCurrentDetail?: () => Promise<void>;

  /* ---- runtime-init: novelai ---- */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  parseNovelAICharacterPrompts?: (raw: string) => any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  renderCharacterPrompts?: (container: HTMLElement, data: any) => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  renderCharacterGrid?: (wrapper: HTMLElement, imgEl: HTMLElement, characters: any[]) => void;
  removeCharacterGrid?: (wrapper: HTMLElement) => void;
  toggleCharacterGrid?: (wrapper: HTMLElement) => boolean;
  showKeyboardHint?: () => void;
  hideKeyboardHint?: () => void;

  /* ---- runtime-init: nav ---- */
  setGridColumns?: (n: string | number) => void;
  openSearchOrModal?: () => void;
  openSearchModal?: () => void;
  closeSearchModal?: () => void;
  executeSearchModal?: () => void;
  showScrollBackBtn?: (scrollY: number) => void;
  scrollBackToPosition?: () => void;
  toggleHeaderInfo?: () => void;

  isRegexModeOn: () => boolean;

  /* ---- boss-lock ---- */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  buildBossModeEdition: () => any;
  stopAllMediaPlayback: () => void;
  showBossMode: () => void;
  hideBossMode: () => void;
  maybeLaunchBossModeFromQuery: () => void;
  activateQuickLock: () => void;

  /* ---- keyboard ---- */
  keyboardHelpApi?: {
    show: () => void;
    hide: () => void;
    isVisible: () => boolean;
  };
  showKeyboardHelp: () => void;
  hideKeyboardHelp?: () => void;

  /* ---- union-search ---- */
  runUnionSearch?: () => Promise<void>;

  /* ---- cross-bundle shared state ---- */

  /* ---- floating-grid ---- */
  updateGridCompactMode?: () => void;

  /* ---- inspect-page (cross-bundle: used by meta-renderer) ---- */
  openInSimulator?: (type: string) => void;

  /* ---- runtime-tools-ui bundle ---- */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  copyWithFeedback?: (text: string, triggerEl: HTMLElement | null | undefined, label?: string) => Promise<boolean>;
  notifyCopy?: (btn: HTMLElement | null | undefined, ok: boolean) => void;
  openFileDirectory?: (fileId: number) => Promise<void>;
  copySeed?: (seed: string | number, event?: Event) => Promise<void>;
  searchByCheckpoint?: (modelName: string, event?: Event) => Promise<void>;
  analyzeCurrentImage?: (fileId: number) => Promise<void>;
  loadSavedAnalysis?: (id: number) => void;
  loadWdTags?: (fileId: number) => Promise<void>;
  wtTestVlm?: () => Promise<void>;
  wtLoadVlmModels?: (url?: string) => Promise<void>;
  wtToggleEngineUI?: () => void;
  convertAndCopy?: (targetId: string, mode: string, evt?: Event) => Promise<void>;
  convertAndShow?: (targetId: string, mode: string, evt?: Event) => Promise<void>;
  loadServerInfo?: () => Promise<void>;
  openRegexIntro?: () => void;
  closeRegexIntro?: () => void;
  _serverInfoPollingSetup?: boolean;
  _serverInfoInterval?: ReturnType<typeof setInterval> | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  updateModalFavButton?: (id: number) => void;
  loadCollectionFilter?: () => Promise<void>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  refreshCollectionSidebar?: () => Promise<void>;

  /* ---- prompt library ---- */
  saveToPromptLibrary?: (fileId: number) => void;

  /* ---- tag-edit ---- */
  addUserTag: (fileId: number, tag?: string) => Promise<void>;
  removeUserTag: (fileId: number, tag: string) => Promise<void>;
  handleTagInputKey: (e: KeyboardEvent, fileId: number) => void;
  _fetchSuggestionsForTagInput: (input: HTMLInputElement) => void;

  /* ---- ratings ---- */

  /* ---- bridge: syntax detection banner ---- */
  setupSyntaxBanner?: (
    textarea: HTMLTextAreaElement,
    bannerId: string,
    mode: 'sd_to_nai' | 'nai_to_sd',
    convertAction: string,
    dismissAction: string,
  ) => void;
}

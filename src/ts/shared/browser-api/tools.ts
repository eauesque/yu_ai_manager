import { pickFunction } from './common';

export function getRuntimeToolsApi() {
  return {
    toggleFavorite: pickFunction(
      window.runtimeToolsApi?.toggleFavorite,
      undefined,
      async () => undefined,
    ) as (id: number) => Promise<void>,
    checkFavorites: pickFunction(
      window.runtimeToolsApi?.checkFavorites,
      undefined,
      () => undefined,
    ) as (ids: number[]) => void,
    updateModalFavButton: pickFunction(
      window.runtimeToolsApi?.updateModalFavButton,
      window.updateModalFavButton,
      () => undefined,
    ) as (id: number) => void,
    notifyCopy: pickFunction(
      window.runtimeToolsApi?.notifyCopy,
      window.notifyCopy,
      () => undefined,
    ) as (btn: HTMLElement | null | undefined, ok: boolean) => void,
    renderFileName: pickFunction(
      window.runtimeToolsApi?.renderFileName,
      undefined,
      (path: string) => path,
    ) as (path: string) => string,
    renderPathDisplay: pickFunction(
      window.runtimeToolsApi?.renderPathDisplay,
      undefined,
      () => '',
    ) as (path: string, id: number) => string,
    searchByCheckpoint: pickFunction(
      window.runtimeToolsApi?.searchByCheckpoint,
      undefined,
      async () => undefined,
    ) as (modelName: string, event?: Event) => Promise<void>,
    copySeed: pickFunction(
      window.runtimeToolsApi?.copySeed,
      undefined,
      async () => undefined,
    ) as (seed: string | number, event?: Event) => Promise<void>,
    showQRShare: pickFunction(
      window.runtimeToolsApi?.showQRShare,
      undefined,
      async () => undefined,
    ) as (fileId: number) => Promise<void>,
    saveToPromptLibrary: pickFunction(
      window.runtimeToolsApi?.saveToPromptLibrary,
      undefined,
      () => undefined,
    ) as (fileId: number) => void,
    viewXmpModal: pickFunction(
      window.runtimeToolsApi?.viewXmpModal,
      undefined,
      async () => undefined,
    ) as (fileId: number) => Promise<void>,
    loadWdTags: pickFunction(
      window.runtimeToolsApi?.loadWdTags,
      window.loadWdTags,
      async () => undefined,
    ) as (fileId: number) => Promise<void>,
    loadSavedAnalysis: pickFunction(
      window.runtimeToolsApi?.loadSavedAnalysis,
      window.loadSavedAnalysis,
      async () => undefined,
    ) as (fileId: number) => Promise<void>,
    analyzeCurrentImage: pickFunction(
      window.runtimeToolsApi?.analyzeCurrentImage,
      window.analyzeCurrentImage,
      async () => undefined,
    ) as (fileId: number) => Promise<void>,
    openFileDirectory: pickFunction(
      window.runtimeToolsApi?.openFileDirectory,
      window.openFileDirectory,
      async () => undefined,
    ) as (fileId: number) => Promise<void>,
    loadServerInfo: pickFunction(
      window.runtimeToolsApi?.loadServerInfo,
      window.loadServerInfo,
      async () => undefined,
    ) as () => Promise<void>,
    refreshCollectionSidebar: pickFunction(
      window.runtimeToolsApi?.refreshCollectionSidebar,
      window.refreshCollectionSidebar,
      () => undefined,
    ) as () => void,
    openRegexIntro: pickFunction(
      window.runtimeToolsApi?.openRegexIntro,
      window.openRegexIntro,
      () => undefined,
    ) as () => void,
    closeRegexIntro: pickFunction(
      window.runtimeToolsApi?.closeRegexIntro,
      window.closeRegexIntro,
      () => undefined,
    ) as () => void,
  };
}

export function getConditionBuilderApi() {
  return {
    activateCondition: pickFunction(
      window.conditionBuilderApi?.activateCondition,
      undefined,
      () => undefined,
    ) as (key: string) => void,
    hasCondition: pickFunction(
      window.conditionBuilderApi?.hasCondition,
      undefined,
      () => false,
    ) as (key: string) => boolean,
    getActiveConditions: pickFunction(
      window.conditionBuilderApi?.getActiveConditions,
      undefined,
      () => [],
    ) as () => string[],
    setActiveConditions: pickFunction(
      window.conditionBuilderApi?.setActiveConditions,
      undefined,
      () => undefined,
    ) as (keys: string[]) => void,
    getConditionMenuButtons: pickFunction(
      window.conditionBuilderApi?.getConditionMenuButtons,
      undefined,
      () => [],
    ) as () => HTMLButtonElement[],
    openConditionMenu: pickFunction(
      window.conditionBuilderApi?.openConditionMenu,
      undefined,
      () => undefined,
    ) as (opts?: { focusFirst?: boolean }) => void,
    closeConditionMenu: pickFunction(
      window.conditionBuilderApi?.closeConditionMenu,
      undefined,
      () => undefined,
    ) as (opts?: { restoreFocus?: boolean }) => void,
    setLastConditionTriggerEl: pickFunction(
      window.conditionBuilderApi?.setLastConditionTriggerEl,
      undefined,
      () => undefined,
    ) as (el: HTMLElement | null) => void,
    announceA11yStatus: pickFunction(
      window.conditionBuilderApi?.announceA11yStatus,
      undefined,
      () => undefined,
    ) as (text: string) => void,
    renderActiveConditions: pickFunction(
      window.conditionBuilderApi?.renderActiveConditions,
      undefined,
      () => undefined,
    ) as () => void,
    removeCondition: pickFunction(
      window.conditionBuilderApi?.removeCondition,
      undefined,
      () => undefined,
    ) as (key: string) => void,
    clearAllConditions: pickFunction(
      window.conditionBuilderApi?.clearAllConditions,
      undefined,
      () => undefined,
    ) as () => void,
  };
}

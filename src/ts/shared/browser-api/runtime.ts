import { pickFunction } from './common';

export function getRuntimeInitApi() {
  return {
    setGridColumns: pickFunction(
      window.runtimeInitApi?.setGridColumns,
      undefined,
      () => undefined,
    ) as (n: string | number) => void,
    openSearchOrModal: pickFunction(
      window.runtimeInitApi?.openSearchOrModal,
      undefined,
      () => undefined,
    ) as () => void,
    closeSearchModal: pickFunction(
      window.runtimeInitApi?.closeSearchModal,
      undefined,
      () => undefined,
    ) as () => void,
    saveSearchState: pickFunction(
      window.runtimeInitApi?.saveSearchState,
      undefined,
      () => undefined,
    ) as () => void,
    restoreSearchState: pickFunction(
      window.runtimeInitApi?.restoreSearchState,
      undefined,
      () => false,
    ) as () => boolean,
    clearInput: pickFunction(
      window.runtimeInitApi?.clearInput,
      undefined,
      () => undefined,
    ) as (inputId: string) => void,
    clearAllInputs: pickFunction(
      window.runtimeInitApi?.clearAllInputs,
      undefined,
      () => undefined,
    ) as () => void,
    showScrollBackBtn: pickFunction(
      window.runtimeInitApi?.showScrollBackBtn,
      undefined,
      () => undefined,
    ) as (scrollY: number) => void,
    scrollBackToPosition: pickFunction(
      window.runtimeInitApi?.scrollBackToPosition,
      undefined,
      () => undefined,
    ) as () => void,
    toggleHeaderInfo: pickFunction(
      window.runtimeInitApi?.toggleHeaderInfo,
      undefined,
      () => undefined,
    ) as () => void,
    parseNovelAICharacterPrompts: pickFunction(
      window.runtimeInitApi?.parseNovelAICharacterPrompts,
      undefined,
      () => null,
    ) as (raw: string) => unknown,
    renderCharacterPrompts: pickFunction(
      window.runtimeInitApi?.renderCharacterPrompts,
      undefined,
      () => undefined,
    ) as (container: HTMLElement, data: unknown) => void,
    renderCharacterGrid: pickFunction(
      window.runtimeInitApi?.renderCharacterGrid,
      undefined,
      () => Promise.resolve(),
    ) as (wrapper: HTMLElement, imgEl: HTMLElement, characters: unknown[]) => Promise<void>,
    removeCharacterGrid: pickFunction(
      window.runtimeInitApi?.removeCharacterGrid,
      undefined,
      () => Promise.resolve(),
    ) as (wrapper: HTMLElement) => Promise<void>,
    toggleCharacterGrid: pickFunction(
      window.runtimeInitApi?.toggleCharacterGrid,
      undefined,
      () => Promise.resolve(false),
    ) as (wrapper: HTMLElement) => Promise<boolean>,
    showKeyboardHint: pickFunction(
      window.runtimeInitApi?.showKeyboardHint,
      undefined,
      () => undefined,
    ) as () => void,
    hideKeyboardHint: pickFunction(
      window.runtimeInitApi?.hideKeyboardHint,
      undefined,
      () => undefined,
    ) as () => void,
  };
}

export function getUnionSearchApi() {
  return {
    runUnionSearch: pickFunction(
      window.unionSearchApi?.runUnionSearch,
      undefined,
      async () => undefined,
    ) as () => Promise<void>,
  };
}

export function getScanBannerApi() {
  return {
    cancelScan: pickFunction(
      window.scanBannerApi?.cancelScan,
      undefined,
      async () => undefined,
    ) as () => Promise<void>,
    resumeScan: pickFunction(
      window.scanBannerApi?.resumeScan,
      undefined,
      () => undefined,
    ) as () => void,
    dismissScan: pickFunction(
      window.scanBannerApi?.dismissScan,
      undefined,
      () => undefined,
    ) as () => void,
  };
}

export function getFloatingGridApi() {
  return {
    isPanelOpen: pickFunction(
      window.floatingGridApi?.isPanelOpen,
      undefined,
      () => false,
    ) as () => boolean,
    closePanel: pickFunction(
      window.floatingGridApi?.closePanel,
      undefined,
      () => undefined,
    ) as () => void,
  };
}

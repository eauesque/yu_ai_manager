import { pickFunction } from './common';

let _ratingsPromise: Promise<typeof import('../../ratings/ratings')> | null = null;
let _similarPromise: Promise<typeof import('../../similar/index')> | null = null;

function _loadRatings() {
  if (!_ratingsPromise) {
    _ratingsPromise = import('../../ratings/ratings');
  }
  return _ratingsPromise;
}

function _loadSimilar() {
  if (!_similarPromise) {
    _similarPromise = import('../../similar/index');
  }
  return _similarPromise;
}

export function getSearchResultsApi() {
  return {
    checkFavorites: pickFunction(
      window.runtimeToolsApi?.checkFavorites,
      undefined,
      () => undefined,
    ) as (ids: number[]) => void,
    runSearch: pickFunction(
      window.searchResultsApi?.runSearch,
      undefined,
      () => undefined,
    ) as (event?: Event) => void,
    searchPager: (window.searchResultsApi?.searchPager || null) as any,
    getResultCards: pickFunction(
      window.searchResultsApi?.getResultCards,
      undefined,
      () => [],
    ) as () => HTMLElement[],
    estimateCardsPerRow: pickFunction(
      window.searchResultsApi?.estimateCardsPerRow,
      undefined,
      () => 1,
    ) as (cards?: HTMLElement[]) => number,
    focusResultCardByIndex: pickFunction(
      window.searchResultsApi?.focusResultCardByIndex,
      undefined,
      () => undefined,
    ) as (index: number) => void,
    ensureSingleTabstopOnResultCards: pickFunction(
      window.searchResultsApi?.ensureSingleTabstopOnResultCards,
      window.ensureSingleTabstopOnResultCards,
      () => undefined,
    ) as (card: HTMLElement) => void,
    setExportData: pickFunction(
      window.searchResultsApi?.setExportData,
      undefined,
      () => undefined,
    ) as (data: unknown) => void,
    accumExportData: pickFunction(
      window.searchResultsApi?.accumExportData,
      undefined,
      () => undefined,
    ) as (results: unknown[]) => void,
    displayResults: pickFunction(
      window.searchResultsApi?.displayResults,
      undefined,
      () => undefined,
    ) as (results: unknown[], totalCount?: number, opts?: unknown) => void,
    togglePrompt: pickFunction(
      window.searchResultsApi?.togglePrompt,
      undefined,
      () => undefined,
    ) as (id: number, evt?: Event) => void,
    copyPrompt: pickFunction(
      window.searchResultsApi?.copyPrompt,
      undefined,
      () => undefined,
    ) as (id: number, type: string, evt?: Event) => void,
  };
}

export function getDetailModalApi() {
  return {
    showDetail: pickFunction(
      window.detailModalApi?.showDetail,
      undefined,
      () => undefined,
    ) as (id: number, opts?: any) => void,
    closeModal: pickFunction(
      window.detailModalApi?.closeModal,
      undefined,
      () => undefined,
    ) as () => void,
    copyToClipboard: pickFunction(
      window.detailModalApi?.copyToClipboard,
      undefined,
      async () => false,
    ) as (text: string) => Promise<boolean>,
    initOcrTab: pickFunction(
      window.detailModalApi?.initOcrTab,
      undefined,
      () => undefined,
    ) as ((fileId: number) => void) | undefined,
    initS2tTab: pickFunction(
      window.detailModalApi?.initS2tTab,
      undefined,
      () => undefined,
    ) as ((fileId: number) => void) | undefined,
    initAnnotationsTab: pickFunction(
      window.detailModalApi?.initAnnotationsTab,
      undefined,
      () => undefined,
    ) as ((fileId: number) => void) | undefined,
    initAnalysisTraceTab: pickFunction(
      window.detailModalApi?.initAnalysisTraceTab,
      undefined,
      () => undefined,
    ) as unknown as ((fileId: number) => Promise<void>) | undefined,
  };
}

export function getContainerViewApi() {
  return {
    isContainerViewOpen: pickFunction(
      window.containerViewApi?.isContainerViewOpen,
      undefined,
      () => false,
    ) as () => boolean,
    openContainerViewPanel: pickFunction(
      window.containerViewApi?.openContainerViewPanel,
      undefined,
      () => undefined,
    ) as (opts: {
      containerType: 'zip' | 'folder';
      containerKey: string;
      containerPath: string;
      memberIds: number[];
      focusFileId?: number | null;
    }) => void,
    closeContainerViewPanel: pickFunction(
      window.containerViewApi?.closeContainerViewPanel,
      undefined,
      () => undefined,
    ) as () => void,
    returnToContainerView: pickFunction(
      window.containerViewApi?.returnToContainerView,
      undefined,
      () => undefined,
    ) as () => void,
  };
}

export function getRatingsApi() {
  return {
    setRating: ((fileId: number, rating: number) =>
      _loadRatings().then((mod) => mod.setRating(fileId, rating))) as (fileId: number, rating: number) => Promise<void>,
    getRatingsBatch: ((fileIds: number[]) =>
      _loadRatings().then((mod) => mod.getRatingsBatch(fileIds))) as (fileIds: number[]) => Promise<Record<number, number>>,
    getRating: ((fileId: number) =>
      _loadRatings().then((mod) => mod.getRating(fileId))) as (fileId: number) => Promise<number>,
    createRatingWidget: ((fileId: number) => {
      const placeholder = document.createElement('span');
      void _loadRatings().then((mod) => {
        const widget = mod.createRatingWidget(fileId);
        placeholder.replaceWith(widget);
      }).catch(() => {});
      return placeholder;
    }) as (fileId: number) => HTMLElement,
    getCardRatingHtml: ((fileId: number) => '') as (fileId: number) => string,
  };
}

export function getSimilarApi() {
  return {
    findSimilarImages: ((fileId: number) =>
      _loadSimilar().then((mod) => mod.findSimilarImages(fileId))) as (fileId: number) => Promise<void>,
  };
}

export function getContextMenuApi() {
  return {
    showContextMenu: pickFunction(
      window.contextMenuApi?.showContextMenu,
      undefined,
      () => undefined,
    ) as (e: MouseEvent, fileId: number, cardEl: HTMLElement) => void,
  };
}

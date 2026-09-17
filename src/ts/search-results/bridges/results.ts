import {
  getResultCards, estimateCardsPerRow, focusResultCardByIndex,
  setupResultCardA11y, ensureSingleTabstopOnResultCards, announceResultCardStatus,
} from '../results/a11y';
import { appendResults, displayResults, togglePrompt, copyPrompt } from '../results/render';
import { setExportData, updateExportCsvVisibility, updateExportCsvLabel, exportResultsCsv, exportResultsRecipeJson, setCsvLimit, showCsvLimitDropdown, accumExportData } from '../results/export';

export function createSearchResultsRenderBridgeApi() {
  return {
    getResultCards,
    estimateCardsPerRow,
    focusResultCardByIndex,
    setupResultCardA11y,
    ensureSingleTabstopOnResultCards,
    announceResultCardStatus,
    appendResults,
    displayResults,
    togglePrompt,
    copyPrompt,
    setExportData,
    updateExportCsvVisibility,
    updateExportCsvLabel,
    exportResultsCsv,
    exportResultsRecipeJson,
    setCsvLimit,
    showCsvLimitDropdown,
    accumExportData,
  };
}

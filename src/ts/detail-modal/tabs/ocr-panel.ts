/**
 * ocr-panel.ts -- OCR tab: HTML rendering and initialization entry point.
 *
 * Action handlers (run, translate, export, overlay) are in ocr-actions.ts.
 * Shared types and constants are in ocr-types.ts.
 */

import { TASKS, LANGUAGES, EXPORT_FMTS } from './ocr-types';
import {
  bindRunBtn, bindBboxBtn, bindTranslateBtn,
  bindExportBtns, bindOverlayBtn, loadExistingResult,
} from './ocr-actions';

// Re-export types for external consumers
export type { OcrRegion, OcrData, TranslationData } from './ocr-types';

/** Generate OCR tab HTML (called from meta-renderer) */
export function renderOcrTabContent(fileId: number): string {
  let html = '';

  // -- OCR execution section --
  html += '<div class="ocr-actions">';
  html += '<select id="ocrTask-' + fileId + '" class="input-sm" aria-label="OCR Task">';
  for (const t of TASKS) {
    html += '<option value="' + t.value + '">' + t.label + '</option>';
  }
  html += '</select>';
  html += '<button type="button" id="ocrRunBtn-' + fileId + '" class="btn-small ocr-btn-run" aria-label="Run OCR">';
  html += '\uD83D\uDD0D OCR</button>';
  html += '<button type="button" id="ocrBboxBtn-' + fileId + '" class="btn-small ocr-btn-bbox" style="display:none;" aria-label="Detect Positions">';
  html += '\uD83D\uDCCD Detect</button>';
  html += '<span id="ocrStatus-' + fileId + '" class="meta-status"></span>';
  html += '</div>';

  // -- OCR results panel --
  html += '<div id="ocrResultPanel-' + fileId + '" class="ocr-result-panel" style="display:none;">';

  // Results header
  html += '<div id="ocrResultHeader-' + fileId + '" class="ocr-result-header"></div>';

  // Text display
  html += '<div id="ocrTextDisplay-' + fileId + '" class="ocr-text-display"></div>';

  // -- Translation section --
  html += '<div class="ocr-translate-section">';
  html += '<div class="ocr-actions">';
  html += '<select id="ocrTargetLang-' + fileId + '" class="input-sm" aria-label="Target Language">';
  for (const l of LANGUAGES) {
    html += '<option value="' + l.value + '">' + l.label + '</option>';
  }
  html += '</select>';
  html += '<button type="button" id="ocrTranslateBtn-' + fileId + '" class="btn-small ocr-btn-translate" aria-label="Translate">';
  html += '\uD83C\uDF10 Translate</button>';
  html += '<span id="ocrTranslateStatus-' + fileId + '" class="meta-status"></span>';
  html += '</div>';
  html += '<div id="ocrTranslationDisplay-' + fileId + '" class="ocr-translation-display" style="display:none;"></div>';
  html += '</div>';

  // -- Export + overlay --
  html += '<div class="ocr-export-actions">';
  html += '<span class="ocr-export-label">Export:</span>';
  for (const fmt of EXPORT_FMTS) {
    html += '<button type="button" class="btn-small ocr-btn-export" data-fmt="' + fmt + '" data-fid="' + fileId + '">';
    html += fmt.toUpperCase() + '</button>';
  }
  html += '<select id="ocrOverlayMode-' + fileId + '" class="input-sm" aria-label="Overlay Mode">';
  html += '<option value="translated">Translated</option>';
  html += '<option value="both">Both</option>';
  html += '<option value="original">Original</option>';
  html += '</select>';
  html += '<button type="button" id="ocrOverlayBtn-' + fileId + '" class="btn-small ocr-btn-overlay" aria-label="Overlay">';
  html += '\uD83D\uDDBC Image</button>';
  html += '</div>';

  html += '</div>'; // ocrResultPanel

  return html;
}

/** Initialize OCR tab (called when modal is displayed) */
export function initOcrTab(fileId: number): void {
  bindRunBtn(fileId);
  bindBboxBtn(fileId);
  bindTranslateBtn(fileId);
  bindExportBtns(fileId);
  bindOverlayBtn(fileId);
  loadExistingResult(fileId);
}

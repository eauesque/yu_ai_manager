/**
 * ocr-types.ts -- Shared types and constants for OCR panel.
 */

export interface OcrRegion {
  region_id: number;
  bbox: number[];
  text: string;
  confidence: number;
  direction: string;
  label: string;
}

export interface OcrData {
  file_id: number;
  engine: string;
  task: string;
  full_text: string;
  language: string;
  regions: OcrRegion[];
}

export interface TranslationData {
  target_lang: string;
  translated_text: string;
  engine: string;
  region_translations: { region_id: number; original: string; translated: string; label: string }[];
}

export const TASKS = [
  { value: 'ocr', label: 'General OCR' },
  { value: 'ocr_document', label: 'Document' },
  { value: 'ocr_manga', label: 'Manga' },
  { value: 'ocr_pdf', label: 'PDF' },
];

export const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'ja', label: '\u65E5\u672C\u8A9E' },
  { value: 'zh', label: '\u4E2D\u6587' },
  { value: 'ko', label: '\uD55C\uAD6D\uC5B4' },
  { value: 'fr', label: 'Fran\u00E7ais' },
  { value: 'de', label: 'Deutsch' },
  { value: 'es', label: 'Espa\u00F1ol' },
];

export const EXPORT_FMTS = ['txt', 'md', 'json', 'pdf'];

/** HTML-escape a string */
export function _esc(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

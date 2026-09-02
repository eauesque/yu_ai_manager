/**
 * Meta-renderer core — main renderMetaInfo orchestrator.
 * Converted from static/js/meta-renderer/core.js + sections.js
 */

import { esc, escAttr } from './utils';
import { renderFileHeader, renderParams } from './sections-file';
import { renderPrompt, renderTags, renderTagsSection, renderSections } from './sections-content';
import { renderOcrTabContent } from '../detail-modal/tabs/ocr-panel';
import { renderS2tTabContent } from '../detail-modal/tabs/s2t-panel';
import { renderAnnotationsTabContent } from '../detail-modal/tabs/annotations-panel';
import { renderAnalysisTraceTabContent } from '../detail-modal/tabs/analysis-trace-panel';
import { getRuntimeToolsApi } from '../shared/browser-apis';

interface MetaData {
  id?: number;
  path?: string;
  params?: unknown;
  parameters?: unknown;
  positive?: string;
  positive_prompt?: string;
  negative?: string;
  negative_prompt?: string;
  tags?: { tag: string; namespace?: string; ns?: string }[];
  sections?: { title: string; content: unknown; display_type: string }[];
  [key: string]: unknown;
}

interface MetaOptions {
  context?: string;
  mode?: string;
  showActions?: boolean;
  showCopyButtons?: boolean;
  showConvertButtons?: boolean;
  maxPromptLen?: number;
  showTagSearch?: boolean;
  showSimulatorLink?: boolean;
  /** Window namespace for convertAndCopy/convertAndShow (default: 'runtimeToolsApi') */
  convertApiNs?: string;
}

function _tr(key: string, fallback: string): string {
  return (typeof window.tr === 'function' ? window.tr(key, fallback) : fallback) || fallback;
}

export function renderMetaInfo(data: MetaData, options?: MetaOptions): string {
  const opts = options || {};
  const context = opts.context || opts.mode || 'modal';
  const showActions = opts.showActions !== false && context === 'modal';
  const isModal = context === 'modal';

  /* ── Info content (always rendered) ── */
  let info = '';
  info += renderFileHeader(data as Record<string, unknown>);
  const params = data.params || data.parameters;
  if (params) info += renderParams(params);

  const positive = data.positive || data.positive_prompt || '';
  if (positive) info += renderPrompt(positive, 'positive', opts);
  const negative = data.negative || data.negative_prompt || '';
  if (negative) info += renderPrompt(negative, 'negative', opts);

  const tagOpts = { ...opts, fileId: data.id };
  if ((data.tags && data.tags.length > 0) || data.id) info += renderTags(data.tags || [], tagOpts);
  if (isModal) info += '<div id="characterPromptsContainer"></div>';
  if (data.sections) info += renderSections(data.sections);

  if (data.id !== undefined) {
    info += '<div class="meta-footer">';
    info += esc(data.path || '');
    info +=
      ' <span class="copy-target meta-footer-id" data-copy-b64="' +
      btoa(String(data.id)) +
      '" data-copy-label="ID " title="' + _tr('result.copy_id_title', 'Copy file ID') + '">#' +
      data.id +
      '</span>';
    info += '</div>';
  }

  /* Info tab action buttons (QR, Library, XMP) */
  if (showActions && data.id !== undefined) {
    info += '<div class="meta-actions">';
    info += '<button type="button" data-action="runtimeToolsApi.showQRShare" data-action-arg="' + escAttr(String(data.id)) + '" class="btn-small meta-btn-qr" aria-label="' + _tr('result.qr_share', 'QR Share') + '">\uD83D\uDCF1 ' + _tr('result.qr_share', 'QR Share') + '</button>';
    info += '<button type="button" data-action="runtimeToolsApi.saveToPromptLibrary" data-action-arg="' + escAttr(String(data.id)) + '" class="btn-small meta-btn-library" aria-label="' + _tr('result.save_to_library', 'Save to Library') + '">' + _tr('result.save_to_library', 'Save to Library') + '</button>';
    info += '<button type="button" data-action="runtimeToolsApi.viewXmpModal" data-action-arg="' + escAttr(String(data.id)) + '" class="btn-small meta-btn-xmp" aria-label="XMP">\uD83D\uDCC4 XMP</button>';
    info += '<button type="button" data-action="snsShareApi.showSnsShare" data-action-arg="' + escAttr(String(data.id)) + '" class="btn-small meta-btn-sns" aria-label="' + _tr('result.sns_share', 'SNS Share') + '">\uD83D\uDCE4 ' + _tr('result.sns_share', 'SNS Share') + '</button>';
    info += '</div>';
    info += '<div id="qrPanel-' + data.id + '" class="meta-panel-qr"></div>';
    info += '<div id="recipeSectionPlaceholder-' + data.id + '" class="meta-panel-recipe" data-file-id="' + data.id + '"></div>';
  }

  /* ── AI Analysis content (modal only) ── */
  let ai = '';
  if (showActions && data.id !== undefined) {
    ai += '<div class="ai-controls">';
    ai += '<div class="ai-controls-row">';
    ai += '<select id="aiEngineSelect-' + data.id + '" class="input-sm ai-ctl-select" aria-label="' + _tr('analysis.engine', 'AI Engine') + '">';
    ai += '<option value="">' + _tr('analysis.engine_default', 'Auto') + '</option>';
    ai += '</select>';
    ai += '<select id="aiModelSelect-' + data.id + '" class="input-sm ai-ctl-select" style="display:none;" aria-label="' + _tr('analysis.model', 'AI Model') + '">';
    ai += '</select>';
    ai += '</div>';
    ai += '<div class="ai-controls-row">';
    ai += '<select id="aiAnalysisMode-' + data.id + '" class="input-sm ai-ctl-select" aria-label="' + _tr('analysis.mode', 'Analysis Mode') + '">';
    ai += '<option value="full">' + _tr('analysis.mode_full', 'Full Analysis') + '</option>';
    ai += '<option value="simple">' + _tr('analysis.mode_simple', 'Color + Composition') + '</option>';
    ai += '</select>';
    ai += '<button type="button" id="aiAnalyzeBtn-' + data.id + '" data-action="runtimeToolsApi.analyzeCurrentImage" data-action-arg="' + data.id + '" class="btn-small meta-btn-analyze" aria-label="' + _tr('result.ai_analysis', 'AI Analysis') + '">\uD83E\uDDE0 ' + _tr('result.ai_analysis', 'AI Analysis') + '</button>';
    ai += '<span id="aiAnalysisStatus-' + data.id + '" class="meta-status"></span>';
    ai += '</div>';
    ai += '</div>';
    ai += '<div id="aiAnalysisPanel-' + data.id + '" class="meta-panel-hidden" style="font-size:13px;"></div>';
  }
  if (isModal) ai += '<div id="wdTagsContainer" style="display:none;"></div>';

  /* ── OCR content (modal only) ── */
  let ocr = '';
  if (showActions && data.id !== undefined) {
    ocr = renderOcrTabContent(data.id);
  }

  /* ── S2T content (modal only, video/audio files) ── */
  const _videoExts = ['.webm', '.mp4', '.avi', '.mov', '.mkv', '.m4v', '.ogv'];
  const _audioExts = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.opus'];
  const pathLower = String(data.path || '').toLowerCase();
  const extMatch = pathLower.match(/(\.[a-z0-9]+)$/);
  const fileExt = extMatch ? extMatch[1] : '';
  const isMediaFile = _videoExts.includes(fileExt) || _audioExts.includes(fileExt);

  let s2t = '';
  if (showActions && data.id !== undefined && isMediaFile) {
    s2t = renderS2tTabContent(data.id);
  }

  /* ── Annotations (Notes) tab content (modal only) ── */
  let annotations = '';
  if (showActions && data.id !== undefined) {
    annotations = renderAnnotationsTabContent(data.id);
  }

  /* ── Analysis Trace tab content (modal only) ── */
  let analysisTrace = '';
  if (showActions && data.id !== undefined) {
    analysisTrace = renderAnalysisTraceTabContent(data.id);
  }

  /* ── Assemble output ── */
  if (!isModal) return info;

  let html = '';
  html += '<div class="mi-tabs" role="tablist">';
  html += '<button type="button" class="mi-tab active" data-tab="info" role="tab" aria-selected="true" aria-controls="miPanel-info">' + _tr('detail.tab_info', 'Info') + '</button>';
  html += '<button type="button" class="mi-tab" data-tab="ai" role="tab" aria-selected="false" aria-controls="miPanel-ai">' + _tr('detail.tab_ai', 'AI Analysis');
  html += '<span class="mi-tab-badge" style="display:none;"></span>';
  html += '</button>';
  html += '<button type="button" class="mi-tab" data-tab="ocr" role="tab" aria-selected="false" aria-controls="miPanel-ocr">' + _tr('detail.tab_ocr', 'OCR');
  html += '<span class="mi-tab-badge-ocr" style="display:none;"></span>';
  html += '</button>';
  if (s2t) {
    html += '<button type="button" class="mi-tab" data-tab="s2t" role="tab" aria-selected="false" aria-controls="miPanel-s2t">' + _tr('detail.tab_s2t', 'S2T');
    html += '<span class="mi-tab-badge-s2t" style="display:none;"></span>';
    html += '</button>';
  }
  if (annotations) {
    html += '<button type="button" class="mi-tab" data-tab="annotations" role="tab" aria-selected="false" aria-controls="miPanel-annotations">' + _tr('detail.tab_annotations', 'Notes') + '</button>';
  }
  if (analysisTrace) {
    html += '<button type="button" class="mi-tab" data-tab="analysis-trace" role="tab" aria-selected="false" aria-controls="miPanel-analysis-trace">' + _tr('detail.tab_analysis_trace', 'Trace') + '</button>';
  }
  html += '</div>';
  html += '<div class="mi-tab-panel active" id="miPanel-info" role="tabpanel" aria-labelledby="miTab-info">' + info + '</div>';
  html += '<div class="mi-tab-panel" id="miPanel-ai" role="tabpanel" aria-labelledby="miTab-ai">' + ai + '</div>';
  html += '<div class="mi-tab-panel" id="miPanel-ocr" role="tabpanel" aria-labelledby="miTab-ocr">' + ocr + '</div>';
  if (s2t) {
    html += '<div class="mi-tab-panel" id="miPanel-s2t" role="tabpanel" aria-labelledby="miTab-s2t">' + s2t + '</div>';
  }
  if (annotations) {
    html += '<div class="mi-tab-panel" id="miPanel-annotations" role="tabpanel" aria-labelledby="miTab-annotations">' + annotations + '</div>';
  }
  if (analysisTrace) {
    html += '<div class="mi-tab-panel" id="miPanel-analysis-trace" role="tabpanel" aria-labelledby="miTab-analysis-trace">' + analysisTrace + '</div>';
  }
  return html;
}

export { esc, renderFileHeader, renderParams, renderPrompt, renderTags, renderTagsSection, renderSections };

/**
 * analysis-trace-panel.ts — Analysis trace tab for the image detail modal.
 *
 * Renders a summary of which analysis engines have processed the file,
 * including WD Tagger, Hailo Tagger, quality analysis, etc.
 */

import { getAppApi } from '../../shared/browser-apis';
import { openRetagModal } from '../../tools-page/wd-tagger/retag-modal';

interface TraceEngine {
  engine: string;
  model?: string;
  source_label?: string;
  tag_count?: number;
  quality_score?: number;
  analyzed_at?: number;
  source?: string;
}

interface TraceData {
  meta_source: string;
  engines: TraceEngine[];
}

function _tr(key: string, fb: string): string {
  return (typeof window.tr === 'function' ? window.tr(key, fb) : fb) || fb;
}

function _esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function _formatTs(ts: number | undefined): string {
  if (!ts) return '—';
  try {
    return new Date(ts * 1000).toLocaleDateString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  } catch {
    return String(ts);
  }
}

function _engineLabel(e: TraceEngine): string {
  const labels: Record<string, string> = {
    wd_tagger: 'WD Tagger',
    hailo_tagger: 'Hailo Tagger',
    quality_analysis: _tr('detail.trace_quality', '品質解析'),
    ocr: 'OCR',
    s2t: _tr('detail.trace_s2t', '音声認識'),
    yolo: 'YOLO',
  };
  return labels[e.engine] || e.engine;
}

/* -- HTML generation (called by meta-renderer/core.ts) -- */

export function renderAnalysisTraceTabContent(fileId: number): string {
  return (
    '<div id="analysisTracePanel-' +
    fileId +
    '" style="font-size:12px;color:var(--muted);">' +
    _tr('detail.trace_loading', '読み込み中...') +
    '</div>'
  );
}

/* -- Initialization (called by show-detail-deferred.ts) -- */

export async function initAnalysisTraceTab(fileId: number): Promise<void> {
  const container = document.getElementById(`analysisTracePanel-${fileId}`);
  if (!container) return;

  try {
    const resp = await getAppApi().apiFetch(`/api/files/${fileId}/analysis-trace`);
    if (!resp.ok) {
      // api_success merges payload into top-level: { ok, error, data, ...payload }
      container.textContent = _tr('detail.trace_none', '解析履歴なし');
      return;
    }
    const json = await resp.json();
    const data: TraceData = { meta_source: json.meta_source, engines: json.engines || [] };

    if (data.engines.length === 0 && data.meta_source === 'unknown') {
      container.textContent = _tr('detail.trace_none', '解析履歴なし');
      return;
    }

    // Build DOM nodes instead of raw innerHTML to avoid XSS risk
    container.textContent = '';

    // Meta source row
    const sourceRow = document.createElement('div');
    sourceRow.style.cssText = 'font-size:11px;color:var(--muted);margin-bottom:8px;';
    const sourceLabel = document.createTextNode(
      _tr('detail.trace_meta_source', 'メタデータソース') + ': '
    );
    const sourceStrong = document.createElement('strong');
    sourceStrong.style.color = 'var(--text)';
    sourceStrong.textContent = data.meta_source;
    sourceRow.appendChild(sourceLabel);
    sourceRow.appendChild(sourceStrong);
    container.appendChild(sourceRow);

    // Retag button: opens the wd-tagger retag modal pre-filled with
    // the wd_tagger engine's model (if any) so the user can re-run
    // inference with different thresholds or a different model.
    const retagBtn = document.createElement('button');
    retagBtn.type = 'button';
    retagBtn.className = 'btn btn-secondary';
    retagBtn.style.cssText =
      'margin-bottom:8px;font-size:11px;padding:4px 10px;';
    retagBtn.textContent = _tr('tools.wt_retag_title', 'Retag image');
    retagBtn.addEventListener('click', () => {
      const wdEngine = data.engines.find((eng) => eng.engine === 'wd_tagger');
      openRetagModal(fileId, wdEngine?.model || '');
    });
    container.appendChild(retagBtn);

    if (data.engines.length > 0) {
      const list = document.createElement('div');
      list.style.cssText = 'display:flex;flex-direction:column;gap:6px;';

      for (const e of data.engines) {
        const card = document.createElement('div');
        card.style.cssText =
          'padding:8px 10px;border-radius:6px;border:1px solid rgba(128,128,128,0.15);background:rgba(128,128,128,0.03);';

        const title = document.createElement('div');
        title.style.cssText = 'font-weight:600;font-size:12px;';
        title.textContent = _engineLabel(e);
        card.appendChild(title);

        const parts: string[] = [];
        if (e.model) parts.push(_tr('detail.trace_model', 'モデル') + ': ' + e.model);
        else if (e.source_label)
          parts.push(_tr('detail.trace_source', 'ソース') + ': ' + e.source_label);
        if (e.tag_count != null)
          parts.push(e.tag_count + ' ' + _tr('detail.trace_tags', 'タグ'));
        if (e.quality_score != null)
          parts.push(
            _tr('detail.trace_quality_score', '品質') +
              ': ' +
              Math.round(e.quality_score * 100) +
              '%'
          );
        const dateStr = _formatTs(e.analyzed_at);
        if (dateStr !== '—')
          parts.push(_tr('detail.trace_date', '解析日') + ': ' + dateStr);

        if (parts.length > 0) {
          const detail = document.createElement('div');
          detail.style.cssText = 'font-size:11px;color:var(--muted);margin-top:2px;';
          detail.textContent = parts.join(' / ');
          card.appendChild(detail);
        }
        list.appendChild(card);
      }
      container.appendChild(list);
    }
  } catch {
    container.textContent = _tr('detail.trace_error', '解析履歴を読み込めませんでした');
  }
}

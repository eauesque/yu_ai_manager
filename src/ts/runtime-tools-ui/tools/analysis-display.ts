/**
 * tools/analysis-display.ts -- AI analysis result rendering: single and
 * multiple result display, color palette, quality badges.
 */

import { getAppApi, getSearchResultsApi } from '../../shared/browser-apis';

/** CSS name -> color map for common color names */
const COLOR_NAME_MAP: Record<string, string> = {
  red: '#e74c3c', blue: '#3498db', green: '#2ecc71', yellow: '#f1c40f',
  orange: '#e67e22', purple: '#9b59b6', pink: '#e91e63', black: '#333',
  white: '#f5f5f5', brown: '#8d6e63', grey: '#9e9e9e', gray: '#9e9e9e',
  gold: '#ffd700', silver: '#c0c0c0', cyan: '#00bcd4', magenta: '#e91e63',
  teal: '#009688', navy: '#1a237e', maroon: '#800000', beige: '#f5f5dc',
  coral: '#ff7f50', crimson: '#dc143c', ivory: '#fffff0', lavender: '#e6e6fa',
  indigo: '#4b0082', violet: '#ee82ee', khaki: '#f0e68c', olive: '#808000',
};

const { escapeHtml, tr } = getAppApi();
const { runSearch } = getSearchResultsApi();

export interface AnalysisResult {
  quality_score?: number;
  quality_notes?: string;
  description?: string;
  style?: string;
  composition?: string;
  mood?: string;
  color_palette?: string[];
  prompt_suggestion?: string;
  tags?: string[];
  engine?: string;
  analyzed_at?: string | number;
}

function colorNameToCss(name: string): string {
  const lower = name.toLowerCase().trim();
  return COLOR_NAME_MAP[lower] || '#888';
}

/** Convert Unix epoch (seconds) or date string to a human-readable local time string */
export function formatAnalyzedAt(value: string | number): string {
  const epoch = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(epoch)) return String(value);
  const d = new Date(epoch * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function qualityClass(score: number): string {
  if (score >= 8) return 'ai-quality-badge--green';
  if (score >= 6) return 'ai-quality-badge--yellow';
  if (score >= 4) return 'ai-quality-badge--orange';
  return 'ai-quality-badge--red';
}

function esc(s: string): string {
  return escapeHtml(s);
}

/** Map engine type IDs to short display names. */
function _engineDisplayName(engine: string): string {
  const map: Record<string, string> = {
    claude_api: 'Claude API',
    claude_vision: 'Claude API',
    openai: 'OpenAI',
    openai_vision: 'OpenAI',
    ollama: 'Ollama',
    local: 'Local Model',
  };
  return map[engine] || engine;
}

export function displayAnalysisResult(panel: HTMLElement, r: AnalysisResult): void {
  let html = '<div class="ai-result">';

  // Engine badge
  if (r.engine) {
    const name = _engineDisplayName(r.engine);
    html += `<div class="ai-result-row">`
      + `<span class="ai-result-label">${esc(tr('analysis.label.engine'))}</span>`
      + `<span class="ai-chip ai-chip--engine">${esc(name)}</span></div>`;
  }

  // Description
  if (r.description) {
    html += `<div class="ai-description">${esc(r.description)}</div>`;
  }

  // Quality score
  if (r.quality_score) {
    html += `<div class="ai-result-row">`
      + `<span class="ai-result-label">${esc(tr('analysis.label.quality'))}</span>`
      + `<span class="ai-quality-badge ${qualityClass(r.quality_score)}">${r.quality_score}/10</span>`
      + (r.quality_notes ? `<span class="ai-quality-notes">${esc(r.quality_notes)}</span>` : '')
      + `</div>`;
  }

  // Style / Composition / Mood chips
  if (r.style) {
    html += `<div class="ai-result-row">`
      + `<span class="ai-result-label">${esc(tr('analysis.label.style'))}</span>`
      + `<span class="ai-chip ai-chip--style">${esc(r.style)}</span></div>`;
  }
  if (r.composition) {
    html += `<div class="ai-result-row">`
      + `<span class="ai-result-label">${esc(tr('analysis.label.composition'))}</span>`
      + `<span class="ai-chip ai-chip--comp">${esc(r.composition)}</span></div>`;
  }
  if (r.mood) {
    html += `<div class="ai-result-row">`
      + `<span class="ai-result-label">${esc(tr('analysis.label.mood'))}</span>`
      + `<span class="ai-chip ai-chip--mood">${esc(r.mood)}</span></div>`;
  }

  // Color palette with actual color dots
  if (r.color_palette?.length) {
    html += `<div class="ai-result-row">`
      + `<span class="ai-result-label">${esc(tr('analysis.label.color'))}</span>`
      + `<div class="ai-palette">`;
    for (const c of r.color_palette) {
      const css = colorNameToCss(c);
      html += `<span class="ai-color-dot" style="background:${css}" title="${esc(c)}"></span>`
        + `<span class="ai-color-name">${esc(c)}</span>`;
    }
    html += '</div></div>';
  }

  // Prompt suggestion
  if (r.prompt_suggestion) {
    html += `<div class="ai-suggestion">`
      + `<span class="ai-suggestion-label">${esc(tr('analysis.label.suggestion'))}</span>`
      + `${esc(r.prompt_suggestion)}</div>`;
  }

  // AI Tags
  if (r.tags?.length) {
    html += `<div class="ai-result-row">`
      + `<span class="ai-result-label">${esc(tr('analysis.label.ai_tags'))}</span>`
      + `<div class="ai-tag-list">`;
    for (const t of r.tags) {
      const safe = esc(t);
      html += `<span class="ai-tag" data-tag="${safe}">${safe}</span>`;
    }
    html += '</div></div>';
  }

  // Analyzed at
  if (r.analyzed_at) {
    const dateStr = formatAnalyzedAt(r.analyzed_at);
    html += `<div class="ai-analyzed-at">${esc(tr('analysis.analyzed_at', { date: dateStr }))}</div>`;
  }

  html += '</div>';
  panel.innerHTML = html;

  // Attach tag click handlers (search by tag)
  panel.querySelectorAll('.ai-tag').forEach((el) => {
    el.addEventListener('click', () => {
      const tag = (el as HTMLElement).dataset.tag || '';
      const input = document.getElementById('tagQuery') as HTMLInputElement | null;
      if (input) {
        input.value = tag;
        runSearch();
      }
    });
  });
}

export function displayMultipleResults(panel: HTMLElement, results: AnalysisResult[]): void {
  if (results.length <= 1) {
    displayAnalysisResult(panel, results[0] || {});
    return;
  }
  let html = '';
  for (let i = 0; i < results.length; i++) {
    const r = results[i];
    const engineLabel = esc(r.engine || `Analysis ${i + 1}`);
    const dateStr = r.analyzed_at ? formatAnalyzedAt(r.analyzed_at) : '';
    const open = i === 0 ? ' open' : '';
    html += `<details class="ai-multi-result"${open}>`;
    html += `<summary class="ai-multi-summary">${engineLabel}`;
    if (dateStr) html += ` <span class="ai-multi-date">${esc(dateStr)}</span>`;
    html += `</summary>`;
    html += '<div class="ai-multi-body">';
    // Render into temp container to get HTML
    const tmp = document.createElement('div');
    displayAnalysisResult(tmp, r);
    html += tmp.innerHTML;
    html += '</div></details>';
  }
  panel.innerHTML = html;
}

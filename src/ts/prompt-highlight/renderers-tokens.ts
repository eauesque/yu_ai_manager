/* prompt-highlight/renderers-tokens.ts — Operator, embedding, normal text highlight renderers */
import { getAppApi } from '../shared/browser-apis';

const _esc = (v: unknown) => getAppApi().escapeHtml(v);

export function highlightOperator(op: string): string {
  const upper = String(op || '').toUpperCase();
  if (upper === 'AND') {
    return '<span style="display:inline-block;padding:2px 8px;border-radius:999px;background:rgba(59,130,246,0.18);color:var(--text);border:1px solid rgba(59,130,246,0.25);font-weight:600;">AND</span> ';
  }
  if (upper === 'BREAK') {
    return '<span style="display:inline-block;padding:2px 8px;border-radius:999px;background:rgba(245,158,11,0.18);color:var(--text);border:1px solid rgba(245,158,11,0.28);font-weight:700;">BREAK</span> ';
  }
  return `<span>${_esc(upper)}</span> `;
}

export function highlightEmbedding(name: string): string {
  const bg = 'rgba(236, 72, 153, 0.2)';
  const border = 'rgba(236, 72, 153, 0.35)';
  const textColor = '#9f1239';
  return `<span style="display:inline-block;padding:2px 6px;border-radius:6px;background:${bg};border:1px solid ${border};color:${textColor};font-weight:600;" title="Textual Inversion (Embedding)">${_esc(name)}</span> `;
}

export function highlightRandomChoice(choices: string): string {
  const bgColor = 'rgba(168, 85, 247, 0.25)';
  const textColor = '#6b21a8';
  const borderColor = 'rgba(168, 85, 247, 0.4)';
  return `<span style="display:inline-block;padding:2px 6px;border-radius:3px;background:${bgColor};color:${textColor};border:1px dashed ${borderColor};font-weight:500;" title="Random choice">||${_esc(choices)}||</span>`;
}

export function highlightNormal(text: string): string {
  if (!text) return '';
  const isLongSentence = text.length > 40 && /\s/.test(text);
  if (isLongSentence) return `<span class="prompt-plain">${_esc(text)}</span> `;
  return `<span class="prompt-pill">${_esc(text)}</span> `;
}

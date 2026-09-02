/* prompt-highlight/renderers-weights.ts — LoRA, weight, paren highlight renderers */
import { getAppApi } from '../shared/browser-apis';

const _esc = (v: unknown) => getAppApi().escapeHtml(v);

export function highlightLora(name: string, params: string, type: string = 'lora'): string {
  // Extract leading weight from params (e.g. "1" or "1:1:lbw=0,0,0,1,1,1")
  const leadingNum = params.match(/^(-?\d*\.?\d+)/);
  const w = leadingNum ? parseFloat(leadingNum[1]) : 1.0;
  const hasExtra = params !== String(w) && params !== leadingNum?.[1];
  let bg: string, border: string, textColor: string;
  if (w < 0) {
    const absW = Math.abs(w);
    const intensity = Math.min(1.0, absW / 2.0);
    const alpha = 0.25 + intensity * 0.25;
    bg = `rgba(239, 68, 68, ${alpha})`;
    border = `rgba(239, 68, 68, ${Math.min(0.7, alpha + 0.2)})`;
    textColor = '#7f1d1d';
  } else if (w < 1.0) {
    const intensity = Math.min(1.0, (1.0 - w) / 0.5);
    const alpha = 0.18 + intensity * 0.22;
    bg = `rgba(139, 92, 246, ${alpha})`;
    border = `rgba(139, 92, 246, ${Math.min(0.6, alpha + 0.15)})`;
    textColor = '#5b21b6';
  } else {
    const intensity = Math.min(1.0, (w - 1.0) / 1.5);
    const alpha = 0.18 + intensity * 0.22;
    bg = `rgba(16, 185, 129, ${alpha})`;
    border = `rgba(16, 185, 129, ${Math.min(0.6, alpha + 0.15)})`;
    textColor = '#065f46';
  }
  const label = `<${type}:${name}:${params}>`;
  const tooltip = hasExtra ? `${type.toUpperCase()} weight: ${w} | params: ${params}` : `${type.toUpperCase()} weight: ${w}`;
  return `<span style="display:inline-block;padding:2px 6px;border-radius:6px;background:${bg};border:1px solid ${border};color:${textColor};font-weight:600;" title="${_esc(tooltip)}">${_esc(label)}</span> `;
}

export function highlightWeight(tag: string, weight: number): string {
  let bgColor: string, textColor: string, fontWeight = 'normal';
  if (weight >= 1.5) {
    bgColor = 'rgba(255, 0, 0, 0.4)'; textColor = '#600'; fontWeight = '600';
  } else if (weight >= 1.3) {
    bgColor = 'rgba(255, 50, 50, 0.35)'; textColor = '#700'; fontWeight = '500';
  } else if (weight >= 1.1) {
    bgColor = 'rgba(255, 100, 100, 0.3)'; textColor = '#800';
  } else if (weight <= 0.5) {
    bgColor = 'rgba(0, 50, 255, 0.45)'; textColor = '#014'; fontWeight = '500';
  } else if (weight <= 0.7) {
    bgColor = 'rgba(50, 100, 255, 0.35)'; textColor = '#025';
  } else if (weight <= 0.9) {
    bgColor = 'rgba(100, 150, 255, 0.25)'; textColor = '#036';
  } else {
    bgColor = 'rgba(200, 200, 200, 0.2)'; textColor = '#333';
  }
  return `<span style="display:inline-block;padding:2px 6px;border-radius:3px;background:${bgColor};color:${textColor};font-weight:${fontWeight};" title="Weight: ${weight}">${_esc(tag)}</span>`;
}

export function highlightNovelAIWeight(weight: string | number, content: string): string {
  const w = parseFloat(String(weight));
  let bgColor: string, textColor: string, fontWeight = 'normal';
  if (w < 0) {
    // Negative weight: suppress / counteract
    const absW = Math.abs(w);
    const intensity = Math.min(1.0, absW / 2.0);
    const alpha = 0.3 + intensity * 0.3;
    bgColor = `rgba(239, 68, 68, ${alpha})`; textColor = '#7f1d1d'; fontWeight = '600';
  } else if (w >= 1.5) {
    bgColor = 'rgba(255, 0, 0, 0.4)'; textColor = '#600'; fontWeight = '600';
  } else if (w >= 1.3) {
    bgColor = 'rgba(255, 50, 50, 0.35)'; textColor = '#700'; fontWeight = '500';
  } else if (w >= 1.1) {
    bgColor = 'rgba(255, 100, 100, 0.3)'; textColor = '#800';
  } else if (w <= 0.5) {
    bgColor = 'rgba(0, 50, 255, 0.45)'; textColor = '#014'; fontWeight = '500';
  } else if (w <= 0.7) {
    bgColor = 'rgba(50, 100, 255, 0.35)'; textColor = '#025';
  } else if (w <= 0.9) {
    bgColor = 'rgba(100, 150, 255, 0.25)'; textColor = '#036';
  } else {
    bgColor = 'rgba(200, 200, 200, 0.2)'; textColor = '#333';
  }
  return `<span style="display:inline-block;padding:2px 6px;border-radius:3px;background:${bgColor};color:${textColor};font-weight:${fontWeight};" title="NovelAI Weight: ${w}">${_esc(content)}</span>`;
}

export function highlightParen(tag: string, parenCount: number, weight: number): string {
  let bgColor: string, fontWeight = 'normal';
  if (parenCount >= 3) {
    bgColor = 'rgba(255, 160, 0, 0.4)'; fontWeight = '500';
  } else if (parenCount >= 2) {
    bgColor = 'rgba(255, 180, 0, 0.3)';
  } else {
    bgColor = 'rgba(255, 200, 0, 0.2)';
  }
  return `<span style="display:inline-block;padding:2px 6px;border-radius:3px;background:${bgColor};font-weight:${fontWeight};" title="Weight: ${weight.toFixed(2)} (${parenCount} parens)">${_esc(tag)}</span>`;
}

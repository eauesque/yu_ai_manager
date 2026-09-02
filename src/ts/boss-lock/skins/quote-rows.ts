/**
 * boss-lock / skins / quote-rows — shared quote row markup used by all skins.
 *
 * Each skin styles `.bm-q-row[data-delta="up|down|flat"]` differently.
 */

import type { EscFn } from './types';

export interface LiveQuoteRow {
  label: string;
  value: string;
}

function deltaInfo(value: string): { sign: 'up' | 'down' | 'flat'; glyph: string } {
  const s = String(value);
  if (s.startsWith('-')) return { sign: 'down', glyph: '▼' };
  if (s.startsWith('+')) return { sign: 'up',   glyph: '▲' };
  return { sign: 'flat', glyph: '·' };
}

function renderQuoteRow(label: string, value: string, escFn: EscFn): string {
  const { sign, glyph } = deltaInfo(value);
  return (
    `<div class="bm-q-row" data-delta="${sign}">`
    + `<span class="bm-q-label">${escFn(label)}</span>`
    + `<span class="bm-q-val"><span class="bm-q-glyph">${glyph}</span>${escFn(value)}</span>`
    + `</div>`
  );
}

export function renderStaticQuoteRows(quotes: string[], escFn: EscFn): string {
  return (quotes || []).map((q) => {
    const s   = String(q);
    const idx = s.indexOf('  ');
    const label = idx >= 0 ? s.slice(0, idx).trim() : s;
    const value = idx >= 0 ? s.slice(idx).trim()     : '';
    return renderQuoteRow(label, value, escFn);
  }).join('');
}

export function renderLiveQuoteRows(rows: LiveQuoteRow[], escFn: EscFn): string {
  return rows.map((q) => {
    const label = String(q.label || '').slice(0, 8);
    const value = String(q.value || '');
    return renderQuoteRow(label, value, escFn);
  }).join('');
}

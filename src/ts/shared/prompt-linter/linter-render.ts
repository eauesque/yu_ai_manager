import type { DupMark } from './linter-duplicate';
import type { SpellError } from './linter-spell';

export function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function buildOverlayHtml(text: string, dups: DupMark[], spells: SpellError[]): string {
  const boundaries = new Set<number>([0, text.length]);
  for (const d of dups) { boundaries.add(d.start); boundaries.add(d.end); }
  for (const s of spells) { boundaries.add(s.start); boundaries.add(s.end); }
  const sorted = Array.from(boundaries).sort((a, b) => a - b);
  let html = '';
  for (let i = 0; i < sorted.length - 1; i++) {
    const sS = sorted[i], sE = sorted[i + 1];
    if (sS >= sE) continue;
    const seg = escHtml(text.slice(sS, sE));
    let dup: number | null = null, spell = false;
    for (const d of dups) { if (d.start <= sS && sE <= d.end) { dup = d.groupIdx; break; } }
    for (const s of spells) { if (s.start <= sS && sE <= s.end) { spell = true; break; } }
    if (dup !== null && spell) html += `<mark class="ps-lint-dup-${dup}"><u class="ps-lint-spell">${seg}</u></mark>`;
    else if (dup !== null) html += `<mark class="ps-lint-dup-${dup}">${seg}</mark>`;
    else if (spell) html += `<u class="ps-lint-spell">${seg}</u>`;
    else html += seg;
  }
  return html;
}

const MIRROR_PROPS = [
  'fontFamily','fontSize','fontWeight','fontStyle','fontVariant','lineHeight',
  'paddingTop','paddingRight','paddingBottom','paddingLeft',
  'borderTopWidth','borderRightWidth','borderBottomWidth','borderLeftWidth',
  'boxSizing','wordBreak','whiteSpace','overflowWrap','textIndent',
  'textAlign','textTransform','tabSize','direction','width','height',
] as const;

export function syncLayout(lintDiv: HTMLElement, textarea: HTMLTextAreaElement): void {
  const cs = getComputedStyle(textarea);
  for (const p of MIRROR_PROPS)
    (lintDiv.style as unknown as Record<string,string>)[p] = cs[p as keyof CSSStyleDeclaration] as string;
  lintDiv.style.borderStyle = 'solid';
  lintDiv.style.borderColor = 'transparent';
  lintDiv.style.letterSpacing = '0';
  lintDiv.style.wordSpacing = '0';
  lintDiv.style.fontKerning = 'none';
  (lintDiv.style as unknown as Record<string,string>).webkitTextSizeAdjust = 'none';
  lintDiv.style.fontVariantLigatures = 'none';
  const sw = (cs as unknown as Record<string,string>).scrollbarWidth ?? '';
  if (sw === 'none' || (cs.overflow !== 'scroll' && cs.overflow !== 'auto'))
    (lintDiv.style as unknown as Record<string,string>).scrollbarWidth = 'none';
}

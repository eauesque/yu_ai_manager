export type SyntaxMode = 'sd' | 'nai' | 'mixed' | 'unknown';

export interface RawToken { raw: string; start: number; }
export interface DupMark { raw: string; start: number; end: number; groupIdx: number; }

export function splitIntoRawTokens(text: string): RawToken[] {
  const result: RawToken[] = [];
  let depth = 0, tokenStart = 0;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '<') depth++;
    else if (ch === '>' && depth > 0) depth--;
    else if ((ch === ',' || ch === '\n') && depth === 0) {
      // Advance start past leading whitespace for accurate position reporting
      let start = tokenStart;
      while (start < i && (text[start] === ' ' || text[start] === '\t')) start++;
      const rawStr = text.slice(start, i).trimEnd();
      if (rawStr.length > 0) result.push({ raw: rawStr, start });
      tokenStart = i + 1;
    }
  }
  // Final token: skip leading whitespace
  let start = tokenStart;
  while (start < text.length && (text[start] === ' ' || text[start] === '\t')) start++;
  const rawStr = text.slice(start).trimEnd();
  if (rawStr.length > 0) result.push({ raw: rawStr, start });
  return result;
}

const SD_WEIGHT_RE = /\(\s*([^()]+?)\s*(?::\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+))?\s*\)/;
const NAI_CURLY_RE = /\{([^{}]+)\}/;
const NAI_SQUARE_RE = /\[([^\[\]]+)\]/;

export function normalizeKey(raw: string, mode: SyntaxMode): string {
  let s = raw;
  if (mode === 'nai') {
    let prev = '';
    while (prev !== s) { prev = s; s = s.replace(NAI_CURLY_RE, '$1').replace(NAI_SQUARE_RE, '$1'); }
  } else {
    let prev = '';
    while (prev !== s) { prev = s; s = s.replace(SD_WEIGHT_RE, '$1'); }
  }
  return s.replace(/_/g, ' ').toLowerCase().trim();
}

const LORA_RE = /^<(?:lora|embedding|hypernet):/i;
const WILDCARD_RE = /^__[a-zA-Z0-9_/\-]*__$/;
const SYMBOL_ONLY_RE = /^[^a-zA-Z0-9]*$/;

function shouldExclude(raw: string, normalized: string): boolean {
  const t = raw.trim();
  if (LORA_RE.test(t)) return true;
  if (WILDCARD_RE.test(t)) return true;
  if (!normalized) return true;
  if (/^\d+$/.test(normalized)) return true;
  if (normalized.length === 1) return true;
  if (SYMBOL_ONLY_RE.test(normalized)) return true;
  if (/[/\\:]/.test(normalized)) return true;
  return false;
}

export function detectDuplicates(text: string, mode: SyntaxMode): DupMark[] {
  const tokens = splitIntoRawTokens(text);
  const keyToGroup = new Map<string, number>();
  const keyToTokens = new Map<string, RawToken[]>();
  let nextGroup = 0;
  for (const tok of tokens) {
    const norm = normalizeKey(tok.raw, mode);
    if (shouldExclude(tok.raw, norm)) continue;
    if (!keyToTokens.has(norm)) keyToTokens.set(norm, []);
    keyToTokens.get(norm)!.push(tok);
  }
  const marks: DupMark[] = [];
  for (const [key, toks] of keyToTokens) {
    if (toks.length < 2) continue;
    if (!keyToGroup.has(key)) { keyToGroup.set(key, nextGroup % 10); nextGroup++; }
    const groupIdx = keyToGroup.get(key)!;
    for (const tok of toks)
      marks.push({ raw: tok.raw, start: tok.start, end: tok.start + tok.raw.length, groupIdx });
  }
  return marks;
}

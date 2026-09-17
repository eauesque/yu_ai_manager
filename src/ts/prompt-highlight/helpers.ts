/* prompt-highlight/helpers.ts — Prompt normalization and index helpers */

export function normalizePromptOperators(input: string): string {
  let s = String(input || '');
  s = s.replace(/\s+/g, ' ');
  // Protect <...> tokens (LoRA/Lyco/embedding) from comma normalization
  const angleBracketTokens: string[] = [];
  s = s.replace(/<[^>]+>/g, (m) => {
    angleBracketTokens.push(m);
    return `\x00AB${angleBracketTokens.length - 1}\x00`;
  });
  s = s.replace(/\s*,\s*/g, ', ');
  s = s.replace(/(,\s*){2,}/g, ', ');
  s = s.replace(/\s*,\s*AND\s*,\s*/gi, ' AND ');
  s = s.replace(/\s*,\s*AND\s+/gi, ' AND ');
  s = s.replace(/\s+AND\s*,\s*/gi, ' AND ');
  s = s.replace(/\s+AND\s+/gi, ' AND ');
  s = s.replace(/\s*,\s*BREAK\s*,\s*/gi, ' BREAK ');
  s = s.replace(/\s*,\s*BREAK\s+/gi, ' BREAK ');
  s = s.replace(/\s+BREAK\s*,\s*/gi, ' BREAK ');
  s = s.replace(/\s+BREAK\s+/gi, ' BREAK ');
  s = s.replace(/(?:\bBREAK\b\s*){2,}/gi, 'BREAK ');
  s = s.replace(/^\s*(?:,|AND|BREAK)\s*/i, '').replace(/\s*(?:,|AND|BREAK)\s*$/i, '');
  // Restore <...> tokens
  s = s.replace(/\x00AB(\d+)\x00/g, (_, idx) => angleBracketTokens[parseInt(idx, 10)]);
  return s.trim();
}

export function isStandaloneKeyword(text: string, index: number, word: string): boolean {
  const len = word.length;
  const beforeOk = index === 0 || !/[A-Za-z0-9_]/.test(text[index - 1]);
  const afterOk = index + len >= text.length || !/[A-Za-z0-9_]/.test(text[index + len]);
  return beforeOk && afterOk && text.slice(index, index + len).toUpperCase() === word;
}

export function findNextSpecialIndex(text: string, index: number): number {
  const rest = text.slice(index);
  for (let p = 0; p < rest.length; p++) {
    // Skip escaped characters — \( \) etc. are literal, not syntax
    if (rest[p] === '\\' && p + 1 < rest.length) { p++; continue; }
    if (rest[p] === '<') {
      // Return offset so caller handles <...> as a special token
      return p;
    }
    if (rest[p] === '(' || rest[p] === ',' || rest[p] === '|') return p;
    if (rest[p] >= '0' && rest[p] <= '9') {
      const naiMatch = rest.slice(p).match(/^(\d+(?:\.\d+)?::)/);
      if (naiMatch) return p;
    }
  }
  return rest.length;
}

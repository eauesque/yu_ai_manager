import type { SyntaxMode, RawToken } from './linter-duplicate';
import nspell from 'nspell';

export interface TagDictResult { tag_name: string; match_type: string; }
export interface ClassifyResult { isSpellError: boolean; candidates: string[]; passToEnglish: boolean; }
export interface SpellError { start: number; end: number; candidates: string[]; }

export function classifyTagDictResults(results: TagDictResult[]): ClassifyResult {
  if (results.length === 0) return { isSpellError: false, candidates: [], passToEnglish: true };
  if (results.some(r => r.match_type !== 'fuzzy')) return { isSpellError: false, candidates: [], passToEnglish: false };
  return { isSpellError: true, candidates: results.map(r => r.tag_name), passToEnglish: false };
}

const LORA_RE = /^<(?:lora|embedding|hypernet):/i;
const WILDCARD_RE = /^__[a-zA-Z0-9_/\-]*__$/;
const ASCII_LETTER_RE = /[a-zA-Z]/;
const WEIGHT_RE = /\(([^()]+):\s*[-+]?\d*\.?\d+\s*\)/g;
const OUTER_PAREN_RE = /^\(+|\)+$/g;

export function isExcludedFromSpell(raw: string): boolean {
  const t = raw.trim();
  if (LORA_RE.test(t)) return true;
  if (WILDCARD_RE.test(t)) return true;
  const stripped = t.replace(WEIGHT_RE, '$1').replace(OUTER_PAREN_RE, '').trim();
  if (!stripped) return true;
  if (/^\d+$/.test(stripped)) return true;
  if (stripped.length === 1) return true;
  if (!ASCII_LETTER_RE.test(stripped)) return true;
  if (/[/\\:]/.test(stripped)) return true;
  return false;
}

export function toQueryForm(raw: string): string {
  // Strip weight syntax and outer grouping parens, normalize spaces to underscores
  // (tag dict uses blue_eyes not blue eyes; NAI tokens like (masterpiece) have no numeric weight)
  return raw.replace(WEIGHT_RE, '$1').replace(OUTER_PAREN_RE, '')
            .toLowerCase().trim().replace(/\s+/g, '_');
}

// Kept as exported utilities (used in tests and external callers).
export function editDistance(a: string, b: string): number {
  const m = a.length, n = b.length;
  const dp = Array.from({ length: n + 1 }, (_, i) => i);
  for (let i = 1; i <= m; i++) {
    let prev = dp[0]; dp[0] = i;
    for (let j = 1; j <= n; j++) {
      const tmp = dp[j];
      dp[j] = a[i-1] === b[j-1] ? prev : 1 + Math.min(prev, dp[j], dp[j-1]);
      prev = tmp;
    }
  }
  return dp[n];
}

export function getCandidates(token: string, wordlist: Set<string>, maxDist: number): string[] {
  const results: Array<{word: string; dist: number}> = [];
  for (const word of wordlist) {
    if (Math.abs(word.length - token.length) > maxDist) continue;
    const d = editDistance(token, word);
    if (d === 0) return [];
    if (d <= maxDist) results.push({ word, dist: d });
  }
  results.sort((a, b) => a.dist - b.dist);
  return results.slice(0, 3).map(r => r.word);
}

/**
 * AI/prompt-specific vocabulary that is valid in image-generation prompts but
 * absent from the English Hunspell corpus (dictionary-en / SCOWL).
 *
 * Checked BEFORE nspell so these words are never flagged as misspellings.
 * Keep entries lowercase, one per line, in alphabetical order within groups.
 */
const AI_TERMS: ReadonlySet<string> = new Set([
  // Anime personality archetypes (Japanese loanwords)
  'dandere', 'deredere', 'kuudere', 'tsundere', 'yandere',
  // Content-rating abbreviations
  'nsfw', 'sfw',
  // Danbooru-style numeric-prefix tags (not caught by isExcludedFromSpell)
  '1boy', '1girl', '2boys', '2girls', '3girls',
  // Stable Diffusion / NAI model terms
  'controlnet', 'hypernetwork',
  // Swimwear / fashion
  'highleg', 'thighhigh', 'thighhighs',
  // Photography/rendering
  'bokeh', 'highres', 'hyperdetailed', 'photorealistic', 'hyperrealistic',
  // Style genres
  'lofi', 'synthwave', 'vaporwave',
  // Japanese-origin garments / accessories (uncommon in SCOWL)
  'obi', 'yukata',
  // Explicit/doujin genre terms (appear in prompts)
  'ahegao', 'futanari',
]);

const tagDictCache = new Map<string, TagDictResult[]>();
let nspellCache: ReturnType<typeof nspell> | null = null;
let nspellLoading: Promise<ReturnType<typeof nspell>> | null = null;

async function loadNspell(): Promise<ReturnType<typeof nspell>> {
  if (nspellCache) return nspellCache;
  if (!nspellLoading) {
    nspellLoading = Promise.all([
      fetch('/static/hunspell-en/index.aff').then(r => r.text()),
      fetch('/static/hunspell-en/index.dic').then(r => r.text()),
    ]).then(([aff, dic]) => {
      nspellCache = nspell({ aff, dic });
      return nspellCache!;
    }).catch(() => {
      // Graceful degradation: return a stub that never flags errors
      nspellCache = { correct: () => true, suggest: () => [] } as unknown as ReturnType<typeof nspell>;
      return nspellCache!;
    });
  }
  return nspellLoading;
}

export async function checkSpelling(
  tokens: RawToken[],
  mode: SyntaxMode,
  runId: number,
  getRunId: () => number,
  ignoreSet: Set<string>,
): Promise<SpellError[]> {
  const toCheck = tokens
    .filter(t => !isExcludedFromSpell(t.raw))
    .map(t => ({ ...t, queryForm: toQueryForm(t.raw) }))
    .filter(t => !ignoreSet.has(t.queryForm));

  const seenQueryForms = new Set<string>();
  const uncached = toCheck.filter(t => {
    if (tagDictCache.has(t.queryForm) || seenQueryForms.has(t.queryForm)) return false;
    seenQueryForms.add(t.queryForm);
    return true;
  });
  const CONCURRENCY = 6;
  const queue = [...uncached];

  async function runWorker() {
    while (queue.length > 0) {
      const item = queue.shift()!;
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 5000);
      try {
        const res = await fetch(
          `/api/tag-dict/search?q=${encodeURIComponent(item.queryForm)}&fuzzy=1&limit=5`,
          { signal: ctrl.signal }
        );
        const data = await res.json();
        tagDictCache.set(item.queryForm, data.results ?? []);
      } catch {
        tagDictCache.set(item.queryForm, []);
      } finally {
        clearTimeout(timer);
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, uncached.length) }, runWorker));
  if (getRunId() !== runId) return [];

  // Load nspell whenever any token might need English validation:
  // - passToEnglish: tag-dict returned nothing → check if it's a valid English word
  // - isSpellError: tag-dict returned only fuzzy matches → skip if it IS a valid English word
  const needsEnglish = toCheck.some(t => {
    const cls = classifyTagDictResults(tagDictCache.get(t.queryForm) ?? []);
    return cls.passToEnglish || cls.isSpellError;
  });
  const spell: ReturnType<typeof nspell> | null = needsEnglish ? await loadNspell() : null;
  if (getRunId() !== runId) return [];

  const errors: SpellError[] = [];
  for (const tok of toCheck) {
    const results = tagDictCache.get(tok.queryForm) ?? [];
    const { isSpellError, candidates, passToEnglish } = classifyTagDictResults(results);
    // Restore spaces so nspell sees "blue eyes" instead of "blue_eyes"
    const word = tok.queryForm.replace(/_/g, ' ');

    if (isSpellError) {
      // Skip if this is an AI prompt term not in the Hunspell corpus
      if (AI_TERMS.has(word)) continue;
      // Skip if nspell recognises it as valid English (handles plurals, conjugations, etc.)
      if (spell && spell.correct(word)) continue;
      errors.push({ start: tok.start, end: tok.start + tok.raw.length, candidates: candidates.slice(0, 3) });

    } else if (passToEnglish && spell) {
      // Skip AI-specific vocabulary before querying nspell
      if (AI_TERMS.has(word)) continue;
      // If nspell recognises it (including morphological forms), it's fine
      if (spell.correct(word)) continue;
      // Multi-word phrases cannot be looked up in nspell; skip suggestion
      if (word.includes(' ')) continue;
      const cands = spell.suggest(word).slice(0, 3);
      if (cands.length > 0)
        errors.push({ start: tok.start, end: tok.start + tok.raw.length, candidates: cands });
    }
  }
  return errors;
}

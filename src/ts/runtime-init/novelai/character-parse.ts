/**
 * NovelAI V4 character prompt parser.
 * Extracts structured character prompt data from raw NovelAI metadata JSON.
 */

export interface CharacterEntry {
  index: number;
  prompt: string;
  positions: Array<{ x: number; y: number }>;
}

export interface VibeTransfer {
  strengths: number[];
  descriptions: string[];
}

export interface CharacterPromptData {
  baseCaption: string;
  characters: CharacterEntry[];
  negativeBase: string;
  negativeCharacters: CharacterEntry[];
  vibeTransfer: VibeTransfer | null;
}

interface NovelAICommentCaption {
  base_caption?: string;
  char_captions?: Array<{
    char_caption?: string;
    centers?: Array<{ x: number; y: number }>;
  }>;
}

interface NovelAICommentData {
  v4_prompt?: { caption?: NovelAICommentCaption };
  v4_negative_prompt?: { caption?: NovelAICommentCaption };
  director_reference_strengths?: number[];
  director_reference_descriptions?: string[];
}

export type { NovelAICommentData };

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * DB sources belonging to the NovelAI family.
 *
 * Mirrors `is_nai_source` in crates/meta-extract/src/lib.rs and `_NAI_SOURCES`
 * in core/prompt/detail_parsing.py. Kept as a predicate rather than an inline
 * list because writing the same set in several places is exactly how the three
 * implementations drifted apart: this side was still checking two sources while
 * the other two checked eight.
 *
 * `novelai_png`/`novelai_webp` are the v3 sources; they reach the same parser
 * because NovelAI stores the generation parameters identically for v3. The
 * remaining values are internal parser identifiers that only appear on rows
 * polluted before E1.
 */
const NAI_SOURCES: ReadonlySet<string> = new Set([
  'novelai_v4_png',
  'novelai_v4_webp',
  'novelai_v4',
  'novelai_png',
  'novelai_webp',
  'nai_webp',
  'nai_v4',
  'nai_v3',
]);

export function isNaiSource(metaSource: unknown): boolean {
  return typeof metaSource === 'string' && NAI_SOURCES.has(metaSource);
}

/**
 * Unwrap NovelAI metadata into its Comment payload, whatever shape it arrives in.
 *
 * Two shapes reach the UI and both must be accepted. The Python extractors wrap
 * the PNG chunks in an object keyed by `Comment`, while the Rust scanner stores
 * the bare `Comment` chunk itself, whose `v4_prompt` sits at the top level.
 * Requiring the wrapper made every Rust-scanned image render as having no
 * characters.
 *
 * Mirrors `parse_novelai_v4_metadata` in crates/meta-extract/src/detail.rs and
 * core/prompt/parse.py. Returns null -- not an empty object -- when there is no
 * v4 caption, so a caller can tell "v3, no character concept" apart from
 * "v4 with zero characters".
 *
 * Accepts a JSON string or an already-parsed value.
 */
export function parseNovelAIComment(raw: unknown): NovelAICommentData | null {
  let outer: unknown = raw;
  if (typeof raw === 'string') {
    try {
      outer = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (!isPlainObject(outer)) return null;

  let data: unknown = outer;
  const inner = outer.Comment;
  if (typeof inner === 'string') {
    try {
      data = JSON.parse(inner);
    } catch {
      return null;
    }
  }
  if (!isPlainObject(data)) return null;

  if (data.v4_prompt === undefined && data.v4_negative_prompt === undefined) return null;
  return data;
}

function toEntries(caption: NovelAICommentCaption | undefined): CharacterEntry[] {
  const chars = caption?.char_captions;
  if (!chars || chars.length === 0) return [];
  return chars.map((char, index) => ({
    index: index + 1,
    prompt: char.char_caption || '',
    positions: char.centers || [],
  }));
}

export function parseNovelAICharacterPrompts(rawMetaJson: string): CharacterPromptData | null {
  const commentData = parseNovelAIComment(rawMetaJson);
  if (!commentData) return null;

  return {
    baseCaption: commentData.v4_prompt?.caption?.base_caption || '',
    characters: toEntries(commentData.v4_prompt?.caption),
    negativeBase: commentData.v4_negative_prompt?.caption?.base_caption || '',
    negativeCharacters: toEntries(commentData.v4_negative_prompt?.caption),
    vibeTransfer: commentData.director_reference_strengths
      ? {
          strengths: commentData.director_reference_strengths || [],
          descriptions: commentData.director_reference_descriptions || [],
        }
      : null,
  };
}

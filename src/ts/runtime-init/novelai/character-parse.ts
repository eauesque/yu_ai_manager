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

export function parseNovelAICharacterPrompts(rawMetaJson: string): CharacterPromptData | null {
  try {
    const rawMeta: Record<string, string> = JSON.parse(rawMetaJson);
    const commentData: NovelAICommentData = JSON.parse(rawMeta.Comment || '{}');
    const result: CharacterPromptData = {
      baseCaption: '',
      characters: [],
      negativeBase: '',
      negativeCharacters: [],
      vibeTransfer: null,
    };

    if (commentData.v4_prompt && commentData.v4_prompt.caption) {
      const caption = commentData.v4_prompt.caption;
      result.baseCaption = caption.base_caption || '';
      if (caption.char_captions && caption.char_captions.length > 0) {
        result.characters = caption.char_captions.map((char, index) => ({
          index: index + 1,
          prompt: char.char_caption || '',
          positions: char.centers || [],
        }));
      }
    }

    if (commentData.v4_negative_prompt && commentData.v4_negative_prompt.caption) {
      const negCaption = commentData.v4_negative_prompt.caption;
      result.negativeBase = negCaption.base_caption || '';
      if (negCaption.char_captions && negCaption.char_captions.length > 0) {
        result.negativeCharacters = negCaption.char_captions.map((char, index) => ({
          index: index + 1,
          prompt: char.char_caption || '',
          positions: char.centers || [],
        }));
      }
    }

    if (commentData.director_reference_strengths) {
      result.vibeTransfer = {
        strengths: commentData.director_reference_strengths || [],
        descriptions: commentData.director_reference_descriptions || [],
      };
    }
    return result;
  } catch (e) {
    console.error('Failed to parse NovelAI character prompts:', e);
    return null;
  }
}

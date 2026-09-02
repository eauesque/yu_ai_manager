import { getRuntimeInitApi } from '../../shared/browser-apis';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function renderCharacterPromptsForData(data: any): void {
  const runtimeInitApi = getRuntimeInitApi();
  if (data.novelai_v4) {
    const container = document.getElementById('characterPromptsContainer');
    if (!container) return;
    const charData = {
      baseCaption: data.novelai_v4.base_caption || '',
      characters: (data.novelai_v4.character_prompts || []).map((cp: Record<string, unknown>, i: number) => ({
        index: i + 1,
        prompt: cp.prompt || cp.char_caption || '',
        positions: cp.centers || cp.positions || [],
      })),
      negativeBase: data.novelai_v4.negative_base || '',
      negativeCharacters: (data.novelai_v4.negative_characters || []).map((nc: Record<string, unknown>, i: number) => ({
        index: i + 1,
        prompt: nc.prompt || nc.char_caption || '',
        positions: nc.centers || nc.positions || [],
      })),
      vibeTransfer: data.novelai_v4.vibe_transfer || null,
    };
    runtimeInitApi.renderCharacterPrompts(container, charData);
    return;
  }

  if ((data.meta_source === 'novelai_v4_png' || data.meta_source === 'novelai_v4_webp') && data.raw_meta_json) {
    try {
      const charPromptsData = runtimeInitApi.parseNovelAICharacterPrompts(data.raw_meta_json);
      if (!charPromptsData) return;
      const container = document.getElementById('characterPromptsContainer');
      if (container) runtimeInitApi.renderCharacterPrompts(container, charPromptsData);
    } catch (e) {
      console.warn('Character prompt fallback parse failed:', e);
    }
  }
}

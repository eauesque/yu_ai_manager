/**
 * NovelAI V4 character prompt renderer.
 * Builds HTML for character prompt display in the detail modal.
 */

import type { CharacterPromptData, VibeTransfer } from './character-parse';
import { MARKER_COLORS } from './character-grid';
import { getAppApi } from '../../shared/browser-apis';

interface NormalizedVibeTransfer {
  strengths: number[];
  descriptions: string[];
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
interface RawVibeTransferInput {
  strengths?: number[];
  director_reference_strengths?: number[];
  strength?: number | string | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  descriptions?: Array<string | { caption?: { base_caption?: string } }>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  director_reference_descriptions?: Array<string | { caption?: { base_caption?: string } }>;
  description?: string;
}

export function normalizeVibeTransfer(vt: VibeTransfer | RawVibeTransferInput | null | undefined): NormalizedVibeTransfer {
  if (!vt || typeof vt !== 'object') return { strengths: [], descriptions: [] };
  let strengths: number[] = [];
  let descriptions: string[] = [];

  if (Array.isArray((vt as RawVibeTransferInput).strengths)) {
    strengths = (vt as RawVibeTransferInput).strengths!;
  } else if (Array.isArray((vt as RawVibeTransferInput).director_reference_strengths)) {
    strengths = (vt as RawVibeTransferInput).director_reference_strengths!;
  } else if ((vt as RawVibeTransferInput).strength !== undefined && (vt as RawVibeTransferInput).strength !== null && (vt as RawVibeTransferInput).strength !== '') {
    strengths = [(vt as RawVibeTransferInput).strength as number];
  }

  if (Array.isArray((vt as RawVibeTransferInput).descriptions)) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    descriptions = ((vt as RawVibeTransferInput).descriptions as any[]).map(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (d: any) => (typeof d === 'string' ? d : d?.caption?.base_caption || ''),
    );
  } else if (Array.isArray((vt as RawVibeTransferInput).director_reference_descriptions)) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    descriptions = ((vt as RawVibeTransferInput).director_reference_descriptions as any[]).map(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (d: any) => (typeof d === 'string' ? d : d?.caption?.base_caption || ''),
    );
  } else if (typeof (vt as RawVibeTransferInput).description === 'string' && (vt as RawVibeTransferInput).description) {
    descriptions = [(vt as RawVibeTransferInput).description!];
  }
  return { strengths, descriptions };
}

const MINI_GRID_SIZE = 5;

function buildMiniGrid(positions: Array<{ x: number; y: number }>, charIndex: number): string {
  const color = MARKER_COLORS[(charIndex - 1) % MARKER_COLORS.length];
  const activeSet = new Set<string>();
  for (const pos of positions) {
    const col = Math.min(MINI_GRID_SIZE - 1, Math.floor(pos.x * MINI_GRID_SIZE));
    const row = Math.min(MINI_GRID_SIZE - 1, Math.floor(pos.y * MINI_GRID_SIZE));
    activeSet.add(`${row}-${col}`);
  }

  let html = '<span class="char-mini-grid">';
  for (let r = 0; r < MINI_GRID_SIZE; r++) {
    for (let c = 0; c < MINI_GRID_SIZE; c++) {
      const isActive = activeSet.has(`${r}-${c}`);
      html += `<span class="char-mini-cell${isActive ? ' active' : ''}"${isActive ? ` style="background:${color}"` : ''}></span>`;
    }
  }
  html += '</span>';
  return html;
}

export function renderCharacterPrompts(container: HTMLElement, data: CharacterPromptData | null): void {
  const chars = Array.isArray(data?.characters) ? data!.characters : [];
  if (!data || (!chars.length && !data.baseCaption)) {
    container.innerHTML = '';
    return;
  }

  const { escapeHtml } = getAppApi();
  const vibe = normalizeVibeTransfer(data.vibeTransfer);
  let html = '<div class="novelai-character-section">';
  html += `<h4>${escapeHtml(window.tr('character.section_title'))}</h4>`;

  if (data.baseCaption) {
    html += '<div class="base-caption-box">';
    html += escapeHtml(data.baseCaption);
    html += '</div>';
  }

  if (chars.length > 0) {
    html += '<div class="character-prompts-list">';
    chars.forEach((char, idx) => {
      const positions = Array.isArray(char.positions) ? char.positions : [];
      const posStr = positions.map((p) => `(${(p.x * 100).toFixed(0)}%, ${(p.y * 100).toFixed(0)}%)`).join(', ');

      html += '<div class="character-prompt-card">';
      html += '<div class="char-header">';
      html += `<span class="char-number">#${char.index}</span>`;
      if (posStr) {
        html += '<span class="char-position-group">';
        html += `<span class="char-position">@ ${escapeHtml(posStr)}</span>`;
        html += buildMiniGrid(positions, char.index);
        html += '</span>';
      }
      html += '</div>';
      html += `<div class="char-prompt-text">${escapeHtml(char.prompt)}</div>`;

      if (data.negativeCharacters && data.negativeCharacters[idx]) {
        const negChar = data.negativeCharacters[idx];
        if (negChar.prompt) {
          html += '<div class="char-negative-prompt">';
          html += `<span class="char-negative-label">${escapeHtml(window.tr('character.negative_label'))}</span> `;
          html += `<span class="char-negative-text">${escapeHtml(negChar.prompt)}</span>`;
          html += '</div>';
        }
      }
      html += '</div>';
    });
    html += '</div>';
  }

  if (data.negativeBase) html += `<div class="negative-caption-box"><strong>${escapeHtml(window.tr('character.negative_label'))}</strong> ${escapeHtml(data.negativeBase)}</div>`;
  if (vibe.strengths.length > 0) {
    html += '<div class="vibe-transfer-box"><h5>Vibe Transfer (Director)</h5>';
    vibe.strengths.forEach((strength, i) => {
      const desc = vibe.descriptions[i] || '';
      html += `<div class="vibe-item">Strength: ${strength}`;
      if (desc) html += ` - ${escapeHtml(desc)}`;
      html += '</div>';
    });
    html += '</div>';
  }
  html += '</div>';
  container.innerHTML = html;

  const section = container.querySelector('.novelai-character-section');
  if (section) {
    const header = section.querySelector('h4');
    if (header) header.addEventListener('click', () => section.classList.toggle('collapsed'));
  }
}

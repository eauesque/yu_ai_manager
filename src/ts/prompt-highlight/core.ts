/* prompt-highlight/core.ts — Main highlightPrompt function */

import { normalizePromptOperators, isStandaloneKeyword, findNextSpecialIndex } from './helpers';
import {
  highlightLora, highlightWeight, highlightNovelAIWeight, highlightParen,
} from './renderers-weights';
import {
  highlightOperator, highlightEmbedding, highlightRandomChoice, highlightNormal,
} from './renderers-tokens';

export function highlightPrompt(prompt: string): string {
  if (!prompt) return '';

  const normalized = normalizePromptOperators(String(prompt));
  let result = '';
  let i = 0;

  while (i < normalized.length) {
    if (i === 0 || /[\s,]/.test(normalized[i - 1])) {
      const naiMatch = normalized.slice(i).match(/^(-?\d+(?:\.\d+)?)::((?:[^:]|:[^:])+?)::/);
      if (naiMatch) {
        result += highlightNovelAIWeight(naiMatch[1], naiMatch[2].trim());
        i += naiMatch[0].length;
        continue;
      }
    }

    if (normalized[i] === '|' && normalized[i + 1] === '|') {
      const randomMatch = normalized.slice(i).match(/^\|\|([^|]+(?:\|[^|]+)*)\|\|/);
      if (randomMatch) {
        result += highlightRandomChoice(randomMatch[1]);
        i += randomMatch[0].length;
        continue;
      }
    }

    if (normalized[i] === '<') {
      // LoRA / LyCORIS — capture all params (supports lbw= extended syntax)
      const lora = normalized.slice(i).match(/^<(lora|lyco):([^:>]+):([^>]+)>/i);
      if (lora) {
        result += highlightLora(lora[2].trim(), lora[3], lora[1].toLowerCase());
        i += lora[0].length;
        continue;
      }
      const emb = normalized.slice(i).match(/^<(embedding|hypernet):([^:>]+)(?::([0-9]*\.?[0-9]+))?>/i);
      if (emb) {
        result += highlightEmbedding(`<${emb[1]}:${emb[2].trim()}>`);
        i += emb[0].length;
        continue;
      }
      // Generic <...> fallback — treat as single token (don't split on inner commas)
      const generic = normalized.slice(i).match(/^<[^>]+>/);
      if (generic) {
        result += highlightNormal(generic[0]);
        i += generic[0].length;
        continue;
      }
    }

    if (normalized[i] === '(' || (i === 0 || /[\s,]/.test(normalized[i - 1]))) {
      const ti = normalized.slice(i).match(/^(?:\()?embedding:([^\s,):]+)(?:\))?/i);
      if (ti && ti[0].includes('embedding:')) {
        result += highlightEmbedding(`embedding:${ti[1].trim()}`);
        i += ti[0].length;
        continue;
      }
    }

    if (normalized[i] === '(') {
      // SD weighted: (content:weight) — allow escaped parens \( \) in content
      const weighted = normalized.slice(i).match(/^\(((?:[^()\\]|\\.)+):(\d+\.?\d*)\)/);
      if (weighted) {
        result += highlightWeight(weighted[1].trim(), parseFloat(weighted[2]));
        i += weighted[0].length;
        continue;
      }

      let count = 0;
      let j = i;
      while (j < normalized.length && normalized[j] === '(') {
        count += 1;
        j += 1;
      }
      if (count > 0) {
        // Find matching ')' skipping escaped \) characters
        let endIdx = -1;
        for (let scan = j; scan < normalized.length; scan++) {
          if (normalized[scan] === '\\' && scan + 1 < normalized.length) { scan++; continue; }
          if (normalized[scan] === ')') { endIdx = scan; break; }
        }
        if (endIdx !== -1) {
          const inner = normalized.slice(j, endIdx).trim();
          result += highlightParen(inner, count, Math.pow(1.1, count));
          let k = endIdx;
          while (k < normalized.length && normalized[k] === ')') k += 1;
          i = k;
          continue;
        }
      }
    }

    if (isStandaloneKeyword(normalized, i, 'AND')) {
      result += highlightOperator('AND');
      i += 3;
      continue;
    }
    if (isStandaloneKeyword(normalized, i, 'BREAK')) {
      result += highlightOperator('BREAK');
      i += 5;
      continue;
    }

    if (normalized[i] === ',') {
      result += '<span style="opacity:.6;">,</span> ';
      i += 1;
      continue;
    }

    const nextSpecial = findNextSpecialIndex(normalized, i);
    const chunk = normalized.slice(i, i + nextSpecial).trim();
    if (chunk) result += highlightNormal(chunk);
    i += nextSpecial > 0 ? nextSpecial : 1;
  }

  return result;
}

/**
 * prompt-syntax-engine.js v2 — lexical core (entry/constants/tokenize)
 */

const PromptSyntax = (function() {
  'use strict';

  const T = {
    NAI_WEIGHT: 'nai_weight',
    NAI_CHOICE: 'nai_choice',
    NAI_EMPHASIS: 'nai_emphasis',
    NAI_SUPPRESS: 'nai_suppress',
    NAI_MIXING: 'nai_mixing',
    SD_WEIGHT: 'sd_weight',
    SD_EMPHASIS: 'sd_emphasis',
    SD_LORA: 'sd_lora',
    SD_EMBEDDING: 'sd_embedding',
    SD_HYPERNET: 'sd_hypernet',
    SD_ALTERNATE: 'sd_alternate',
    SD_SCHEDULED: 'sd_scheduled',
    SD_AND: 'sd_and',
    DP_CHOICE: 'dp_choice',
    DP_WEIGHTED: 'dp_weighted',
    DP_WILDCARD: 'dp_wildcard',
    NAMESPACE: 'namespace',
    COMMA: 'comma',
    TEXT: 'text',
    BREAK: 'break',
    NEWLINE: 'newline',
    ERROR: 'error',
  };

  const SYNTAX = { NAI: 'nai', SD: 'sd', DP: 'dynamic_prompts', MIXED: 'mixed', UNKNOWN: 'unknown' };

  const KNOWN_NS = new Set([
    'artist', 'character', 'copyright', 'general', 'meta', 'style',
    'quality', 'rating', 'source', 'year',
  ]);

  // ─── Tokenizer ───
  function tokenize(text) {
    const tokens = [];
    let i = 0;
    const len = text.length;

    while (i < len) {
      if (text[i] === '\n') { tokens.push({ type: T.NEWLINE, value: '\n', start: i, end: i + 1 }); i++; continue; }
      if (text[i] === ',') { tokens.push({ type: T.COMMA, value: ',', start: i, end: i + 1 }); i++; continue; }

      const nw = matchNaiWeight(text, i);
      if (nw) { tokens.push(nw); i = nw.end; continue; }

      const nc = matchNaiChoice(text, i);
      if (nc) { tokens.push(nc); i = nc.end; continue; }

      const angle = matchAngleBracket(text, i);
      if (angle) { tokens.push(angle); i = angle.end; continue; }

      const wc = matchWildcard(text, i);
      if (wc) { tokens.push(wc); i = wc.end; continue; }

      if (text.substring(i, i + 5) === 'BREAK' && (i === 0 || /[\s,]/.test(text[i - 1])) && (i + 5 >= len || /[\s,]/.test(text[i + 5]))) {
        tokens.push({ type: T.BREAK, value: 'BREAK', start: i, end: i + 5 });
        i += 5;
        continue;
      }

      if (text.substring(i, i + 3) === 'AND' && (i === 0 || /\s/.test(text[i - 1])) && (i + 3 >= len || /\s/.test(text[i + 3]))) {
        tokens.push({ type: T.SD_AND, value: 'AND', start: i, end: i + 3 });
        i += 3;
        continue;
      }

      if (text.substring(i, i + 5) === ' AND ' && i > 0) {
        tokens.push({ type: T.SD_AND, value: ' AND ', start: i, end: i + 5 });
        i += 5;
        continue;
      }

      if (text[i] === '[') {
        const sq = matchSquareBracket(text, i);
        if (sq) { tokens.push(sq); i = sq.end; continue; }
      }

      if (text[i] === '{') {
        const br = matchBrace(text, i);
        if (br) { tokens.push(br); i = br.end; continue; }
      }

      if (text[i] === '(') {
        const paren = matchParen(text, i);
        if (paren) { tokens.push(paren); i = paren.end; continue; }
      }

      const ns = matchNamespace(text, i);
      if (ns) { tokens.push(ns); i = ns.end; continue; }

      const embed = matchBareEmbedding(text, i);
      if (embed) { tokens.push(embed); i = embed.end; continue; }

      const te = findTextEnd(text, i);
      if (te > i) {
        tokens.push({ type: T.TEXT, value: text.substring(i, te), start: i, end: te });
        i = te;
      } else {
        tokens.push({ type: T.TEXT, value: text[i], start: i, end: i + 1 });
        i++;
      }
    }

    return postDetectMixing(tokens);
  }

  // ─── Syntax detection ───

  function detectSyntax(tokens) {
    const ind = { nai:[], sd:[], dp:[] };
    for (const tok of tokens) {
      switch (tok.type) {
        case T.NAI_WEIGHT: case T.NAI_CHOICE: case T.NAI_EMPHASIS:
        case T.NAI_SUPPRESS: case T.NAI_MIXING:
          ind.nai.push(tok); break;
        case T.SD_WEIGHT: case T.SD_EMPHASIS: case T.SD_LORA:
        case T.SD_EMBEDDING: case T.SD_HYPERNET: case T.SD_ALTERNATE:
        case T.SD_SCHEDULED: case T.SD_AND: case T.SD_AND:
          ind.sd.push(tok); break;
        case T.DP_CHOICE: case T.DP_WEIGHTED: case T.DP_WILDCARD:
          ind.dp.push(tok); break;
      }
    }
    const hasNai = ind.nai.length > 0, hasSd = ind.sd.length > 0, hasDp = ind.dp.length > 0;
    const warnings = [];
    if (hasNai && hasSd) {
      warnings.push({
        level:'warning',
        message:window.tr?.('prompt_syntax.error_mixed_syntax', 'NAI and SD syntax are mixed'),
        detail:(window.tr?.('prompt_syntax.error_mixed_detail', 'NAI: {nai} occurrences, SD: {sd} occurrences') || 'NAI: {nai} occurrences, SD: {sd} occurrences').replace('{nai}', ind.nai.length).replace('{sd}', ind.sd.length),
        naiExamples: ind.nai.slice(0,3).map(t=>t.value),
        sdExamples: ind.sd.slice(0,3).map(t=>t.value),
      });
    }
    let syntax = SYNTAX.UNKNOWN, confidence = 0;
    if (hasNai && !hasSd) { syntax = SYNTAX.NAI; confidence = 0.9; }
    else if (hasSd && !hasNai) { syntax = SYNTAX.SD; confidence = 0.9; }
    else if (hasNai && hasSd) { syntax = SYNTAX.MIXED; confidence = 1.0; }
    else if (hasDp) { syntax = SYNTAX.DP; confidence = 0.7; }
    if (hasDp && syntax !== SYNTAX.DP) syntax = syntax === SYNTAX.UNKNOWN ? SYNTAX.DP : syntax;
    return { syntax, confidence, indicators: ind, warnings };
  }

  // ─── Error detection ───

  function detectErrors(tokens) {
    const errors = [];
    for (const tok of tokens) {
      if (tok.type === T.ERROR) {
        const m = {
          unmatched_paren:window.tr?.('prompt_syntax.error_missing_close_paren', 'No matching )'),
          unmatched_brace:window.tr?.('prompt_syntax.error_missing_close_brace', 'No matching }'),
          unmatched_bracket:window.tr?.('prompt_syntax.error_missing_close_bracket', 'No matching ]')
        };
        errors.push({ level:'error', message:m[tok.meta?.error]||window.tr?.('prompt_syntax.error_syntax', 'Syntax error'), start:tok.start, end:tok.end, token:tok });
      }
      if (tok.type === T.NAI_WEIGHT || tok.type === T.SD_WEIGHT) {
        const w = tok.meta?.weight;
        if (w !== undefined && w > 5) {
          const msg = (window.tr?.('prompt_syntax.error_weight_too_high', 'Abnormally high weight: {w}') || 'Abnormally high weight: {w}').replace('{w}', w);
          errors.push({level:'warning',message:msg,start:tok.start,end:tok.end,token:tok});
        }
        if (w !== undefined && w < -10) {
          const msg = (window.tr?.('prompt_syntax.error_weight_too_low', 'Abnormally low weight: {w}') || 'Abnormally low weight: {w}').replace('{w}', w);
          errors.push({level:'warning',message:msg,start:tok.start,end:tok.end,token:tok});
        }
      }
      if (tok.type === T.SD_EMPHASIS && tok.depth > 5) {
        const msg = (window.tr?.('prompt_syntax.error_paren_depth', 'Parenthesis depth {d} (effective ×{w})') || 'Parenthesis depth {d} (effective ×{w})').replace('{d}', tok.depth).replace('{w}', tok.meta?.weight?.toFixed(2));
        errors.push({level:'warning',message:msg,start:tok.start,end:tok.end,token:tok});
      }
      if (tok.type === T.NAI_EMPHASIS && tok.depth > 8) {
        const msg = (window.tr?.('prompt_syntax.error_brace_depth', 'Brace depth {d} (effective ×{w})') || 'Brace depth {d} (effective ×{w})').replace('{d}', tok.depth).replace('{w}', tok.meta?.weight?.toFixed(2));
        errors.push({level:'warning',message:msg,start:tok.start,end:tok.end,token:tok});
      }
    }
    return errors;
  }


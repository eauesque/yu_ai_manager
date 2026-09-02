  // ── () — SD weight, SD emphasis ──
  function matchParen(text, i) {
    const result = findMatchingClose(text, i, '(', ')');
    if (!result) {
      return { type: T.ERROR, value: '(', start: i, end: i + 1, meta: { error: 'unmatched_paren' } };
    }

    const inner = text.substring(i + result.depth, result.end - result.depth);
    const fullVal = text.substring(i, result.end);

    if (result.depth === 1) {
      const wm = inner.match(/^(.+?):\s*(-?\d*\.?\d+)\s*$/);
      if (wm) {
        return {
          type: T.SD_WEIGHT,
          value: fullVal,
          start: i,
          end: result.end,
          depth: 1,
          meta: { content: wm[1].trimEnd(), weight: parseFloat(wm[2]) },
        };
      }
    }

    return {
      type: T.SD_EMPHASIS,
      value: fullVal,
      start: i,
      end: result.end,
      depth: result.depth,
      meta: { content: inner, weight: Math.pow(1.1, result.depth) },
    };
  }

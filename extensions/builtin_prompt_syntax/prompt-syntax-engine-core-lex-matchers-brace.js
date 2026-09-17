  // ── {} — NAI emphasis, DP choice, DP weighted ──
  function matchBrace(text, i) {
    const result = findMatchingBrace(text, i);
    if (!result) {
      return { type: T.ERROR, value: '{', start: i, end: i + 1, meta: { error: 'unmatched_brace' } };
    }

    // :: terminated: braces are closed by :: terminator, content ends at ::
    if (result.terminatedBy === '::') {
      const inner = text.substring(i + result.depth, result.end);
      const fullVal = text.substring(i, result.end);
      return {
        type: T.NAI_EMPHASIS,
        value: fullVal,
        start: i,
        end: result.end,
        depth: result.depth,
        meta: { content: inner, weight: Math.pow(1.05, result.depth), terminatedBy: '::' },
      };
    }

    const inner = text.substring(i + result.depth, result.end - result.depth);
    const fullVal = text.substring(i, result.end);

    if (inner.includes('|') && (/\d+\$\$/.test(inner) || /\d+##/.test(inner))) {
      const choices = inner.split('|').map((part) => {
        const wm = part.match(/^(\d+)(?:\$\$|##)(.*)$/);
        if (wm) return { weight: parseInt(wm[1], 10), text: wm[2] };
        return { weight: 1, text: part };
      });
      return {
        type: T.DP_WEIGHTED,
        value: fullVal,
        start: i,
        end: result.end,
        depth: result.depth,
        meta: { choices },
      };
    }

    if (inner.includes('|')) {
      const choices = splitTopLevel(inner, '|');
      return {
        type: T.DP_CHOICE,
        value: fullVal,
        start: i,
        end: result.end,
        depth: result.depth,
        meta: { choices },
      };
    }

    return {
      type: T.NAI_EMPHASIS,
      value: fullVal,
      start: i,
      end: result.end,
      depth: result.depth,
      meta: { content: inner, weight: Math.pow(1.05, result.depth) },
    };
  }

  // ── [] — SD Alternating / SD Scheduled / NAI suppress ──
  function matchSquareBracket(text, i) {
    const closeResult = findSimpleClose(text, i, '[', ']');

    // findSimpleClose returns int (position) or {pos, terminatedBy} or -1
    let close, terminated = false;
    if (closeResult === -1) {
      return { type: T.ERROR, value: '[', start: i, end: i + 1, meta: { error: 'unmatched_bracket' } };
    } else if (typeof closeResult === 'object') {
      close = closeResult.pos;
      terminated = true;
    } else {
      close = closeResult;
    }

    let depth = 0;
    let j = i;
    while (j < text.length && text[j] === '[') { depth++; j++; }

    // :: terminated: content ends at :: position, no closing ]
    if (terminated) {
      const inner = text.substring(i + depth, close);
      const fullVal = text.substring(i, close);
      return {
        type: T.NAI_SUPPRESS,
        value: fullVal,
        start: i,
        end: close,
        depth: depth,
        meta: { content: inner, terminatedBy: '::' },
      };
    }

    let closeDepth = 0;
    let k = close;
    while (k >= 0 && text[k] === ']') { closeDepth++; k--; }

    const innerStart = i + depth;
    const innerEnd = close + 1 - depth;
    const inner = text.substring(innerStart, innerEnd > innerStart ? innerEnd : close);
    const fullVal = text.substring(i, close + 1);

    if (depth === 1 && inner.includes('|') && !inner.includes(':')) {
      const choices = inner.split('|');
      return { type: T.SD_ALTERNATE, value: fullVal, start: i, end: close + 1, meta: { choices } };
    }

    if (depth === 1) {
      const schedM = inner.match(/^(.+):(.+):(\d*\.?\d+)$/);
      if (schedM) {
        return {
          type: T.SD_SCHEDULED,
          value: fullVal,
          start: i,
          end: close + 1,
          meta: { from: schedM[1], to: schedM[2], step: parseFloat(schedM[3]) },
        };
      }
      const schedM2 = inner.match(/^(.+)::(\d*\.?\d+)$/);
      if (schedM2) {
        return {
          type: T.SD_SCHEDULED,
          value: fullVal,
          start: i,
          end: close + 1,
          meta: { from: schedM2[1], to: '', step: parseFloat(schedM2[2]) },
        };
      }
      const schedM3 = inner.match(/^:(.+):(\d*\.?\d+)$/);
      if (schedM3) {
        return {
          type: T.SD_SCHEDULED,
          value: fullVal,
          start: i,
          end: close + 1,
          meta: { from: '', to: schedM3[1], step: parseFloat(schedM3[2]) },
        };
      }
    }

    return {
      type: T.NAI_SUPPRESS,
      value: fullVal,
      start: i,
      end: close + 1,
      depth: Math.min(depth, closeDepth),
      meta: { content: inner },
    };
  }

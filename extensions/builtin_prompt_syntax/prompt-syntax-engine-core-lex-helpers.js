  // ── Post-pass: NAI Prompt Mixing detection ──
  // Single | between text/tag segments (not inside || or [|])
  function postDetectMixing(tokens) {
    const result = [];
    for (let i = 0; i < tokens.length; i++) {
      const tok = tokens[i];

      // Look for TEXT tokens containing single | (prompt mixing: cat|dog:1.1)
      if (tok.type === T.TEXT && tok.value.includes('|')) {
        const parts = tok.value.split('|');
        for (let pi = 0; pi < parts.length; pi++) {
          if (pi > 0) {
            // This is a mixing separator
            // Check if full expression is mixing: A|B or A:w|B:w
            result.push({
              type: T.NAI_MIXING, value: '|', start: tok.start, end: tok.start + 1,
              meta: { isSeparator: true },
            });
          }
          if (parts[pi]) {
            // Parse weight suffix :1.1
            const wm = parts[pi].match(/^(.+):(-?\d*\.?\d+)$/);
            if (wm) {
              result.push({ type: T.TEXT, value: wm[1], start: tok.start, end: tok.start + wm[1].length });
              result.push({
                type: T.NAI_MIXING, value: ':' + wm[2], start: tok.start, end: tok.start,
                meta: { weight: parseFloat(wm[2]) },
              });
            } else {
              result.push({ type: T.TEXT, value: parts[pi], start: tok.start, end: tok.start + parts[pi].length });
            }
          }
        }
      } else {
        result.push(tok);
      }
    }
    return result;
  }

  // ─── Bracket helpers ───

  function findMatchingClose(text, i, open, close) {
    let depth = 0, j = i;
    while (j < text.length && text[j] === open) { depth++; j++; }
    if (depth === 0) return null;
    let inner = 0;
    while (j < text.length) {
      // Skip escaped characters (e.g. \( \) in NAI prompts)
      if (text[j] === '\\' && j + 1 < text.length) { j += 2; continue; }
      if (text[j] === open) inner++;
      else if (text[j] === close) {
        if (inner > 0) { inner--; }
        else {
          let cc = 0, k = j;
          while (k < text.length && text[k] === close) { cc++; k++; }
          if (cc >= depth) return { depth, end: j + depth };
          return { depth: cc, end: j + cc };
        }
      }
      j++;
    }
    return null;
  }

  function findMatchingBrace(text, i) {
    let depth = 0, j = i;
    while (j < text.length && text[j] === '{') { depth++; j++; }
    if (depth === 0) return null;

    // Lookahead: a top-level `|` before the matching `}` means this brace is a
    // Dynamic Prompts choice group ({a|b|c}), not a NAI ::-terminated emphasis.
    // In that case, never let an inner NAI weight (e.g. 2::e::) terminate the
    // brace — the matching `}` is authoritative.
    let hasTopLevelPipe = false;
    {
      let k = j, nested = 0;
      while (k < text.length) {
        if (text[k] === '\\' && k + 1 < text.length) { k += 2; continue; }
        if (text[k] === '{') { nested++; k++; continue; }
        if (text[k] === '}') {
          if (nested > 0) { nested--; k++; continue; }
          break;
        }
        if (text[k] === '|' && nested === 0) { hasTopLevelPipe = true; break; }
        k++;
      }
    }

    let inner = 0;
    while (j < text.length) {
      // NAI :: terminator — closes all open braces
      // But skip over NAI weight syntax (number::content::)
      if (!hasTopLevelPipe && text[j] === ':' && text[j + 1] === ':') {
        // Check if this :: is part of a NAI weight (preceded by a number)
        var numStart = j - 1;
        while (numStart >= i + depth && /[\d.\-]/.test(text[numStart])) numStart--;
        numStart++;
        var prefix = text.substring(numStart, j);
        if (/^-?\d+(?:\.\d+)?$/.test(prefix) && numStart > i + depth - 1) {
          // This is a NAI weight opening ::, skip to the closing ::
          var closeDoubleColon = text.indexOf('::', j + 2);
          if (closeDoubleColon !== -1) {
            // The closing :: is the terminator for both weight AND braces
            return { depth, end: closeDoubleColon + 2, terminatedBy: '::' };
          }
        }
        // Standalone :: terminator
        return { depth, end: j, terminatedBy: '::' };
      }
      if (text[j] === '{') inner++;
      else if (text[j] === '}') {
        if (inner > 0) { inner--; }
        else {
          let cc = 0, k = j;
          while (k < text.length && text[k] === '}') { cc++; k++; }
          if (cc >= depth) return { depth, end: j + depth };
          return { depth: cc, end: j + cc };
        }
      }
      j++;
    }
    return null;
  }

  function findSimpleClose(text, i, open, close) {
    let depth = 1;
    for (let j = i + 1; j < text.length; j++) {
      // NAI :: terminator — closes all open brackets
      // But NOT inside SD scheduled syntax [from::step] or [from:to:step]
      if (text[j] === ':' && text[j + 1] === ':') {
        // Check if this looks like SD scheduled: ::number]
        var afterDC = text.substring(j + 2);
        var sdSched = afterDC.match(/^(\d+(?:\.\d+)?)\]/);
        if (sdSched) {
          // This is SD scheduled syntax, don't treat as terminator
          // Continue to find the real close bracket
        } else {
          // Check if this :: is part of a NAI weight (preceded by a number)
          var numStart = j - 1;
          while (numStart > i && /[\d.\-]/.test(text[numStart])) numStart--;
          numStart++;
          var prefix = text.substring(numStart, j);
          if (/^-?\d+(?:\.\d+)?$/.test(prefix) && numStart > i) {
            var closeDoubleColon = text.indexOf('::', j + 2);
            if (closeDoubleColon !== -1) {
              return { pos: closeDoubleColon + 2, terminatedBy: '::' };
            }
          }
          return { pos: j, terminatedBy: '::' };
        }
      }
      if (text[j] === open) depth++;
      if (text[j] === close) { depth--; if (depth === 0) return j; }
    }
    return -1;
  }

  function splitTopLevel(str, sep) {
    // Split on sep but not inside nested brackets
    const parts = []; let cur = ''; let depth = 0;
    for (let i = 0; i < str.length; i++) {
      if ('{[('.includes(str[i])) depth++;
      if ('}])'.includes(str[i])) depth--;
      if (str[i] === sep && depth === 0) { parts.push(cur); cur = ''; }
      else cur += str[i];
    }
    parts.push(cur);
    return parts;
  }


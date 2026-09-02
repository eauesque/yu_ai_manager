  // ── NAI numeric emphasis: [-]w::content[, more]:: ──
  function matchNaiWeight(text, i) {
    const m = text.substring(i).match(/^(-?\d*\.?\d+)::([\s\S]*?)::/);
    if (!m) return null;
    if (m[2].length > 500) return null;
    const weight = parseFloat(m[1]);
    return {
      type: T.NAI_WEIGHT,
      value: m[0],
      start: i,
      end: i + m[0].length,
      meta: { weight, content: m[2] },
    };
  }

  // ── NAI Prompt Randomizer: ||A|B|| ──
  function matchNaiChoice(text, i) {
    if (text[i] !== '|' || text[i + 1] !== '|') return null;
    let j = i + 2;
    let depth = 0;
    while (j < text.length - 1) {
      if (text[j] === '{') depth++;
      else if (text[j] === '}') depth--;
      else if (text[j] === '|' && text[j + 1] === '|' && depth === 0) {
        const inner = text.substring(i + 2, j);
        const choices = splitTopLevel(inner, '|');
        return {
          type: T.NAI_CHOICE,
          value: text.substring(i, j + 2),
          start: i,
          end: j + 2,
          meta: { choices },
        };
      }
      j++;
    }
    return null;
  }

  // ── Angle brackets ──
  function matchAngleBracket(text, i) {
    if (text[i] !== '<') return null;
    const close = text.indexOf('>', i);
    if (close === -1 || close - i > 200) return null;
    const inner = text.substring(i + 1, close);
    const val = text.substring(i, close + 1);
    if (/^lora:/i.test(inner) || /^lyco:/i.test(inner)) {
      const p = inner.split(':');
      return { type: T.SD_LORA, value: val, start: i, end: close + 1, meta: { name: p[1] || '', weight: parseFloat(p[2]) || 1 } };
    }
    if (/^(embedding|ti):/i.test(inner)) {
      return { type: T.SD_EMBEDDING, value: val, start: i, end: close + 1, meta: { name: inner.split(':')[1] || '' } };
    }
    if (/^hypernet:/i.test(inner)) {
      return { type: T.SD_HYPERNET, value: val, start: i, end: close + 1, meta: { name: inner.split(':')[1] || '' } };
    }
    return null;
  }

  // ── Wildcard __name__ ──
  function matchWildcard(text, i) {
    if (text[i] !== '_' || text[i + 1] !== '_') return null;
    const m = text.substring(i).match(/^__([a-zA-Z0-9_\-/]+)__/);
    if (!m) return null;
    return { type: T.DP_WILDCARD, value: m[0], start: i, end: i + m[0].length, meta: { name: m[1] } };
  }

  function matchNamespace(text, i) {
    const m = text.substring(i).match(/^([a-z_]+):/);
    if (!m || !KNOWN_NS.has(m[1])) return null;
    if (['lora', 'embedding', 'ti', 'hypernet', 'lyco'].includes(m[1])) return null;
    return { type: T.NAMESPACE, value: m[0], start: i, end: i + m[0].length, meta: { namespace: m[1] } };
  }

  function matchBareEmbedding(text, i) {
    const m = text.substring(i).match(/^embedding:([^\s,<>(){}[\]]+)/i);
    if (!m) return null;
    return { type: T.SD_EMBEDDING, value: m[0], start: i, end: i + m[0].length, meta: { name: m[1] } };
  }

  function findTextEnd(text, i) {
    const specials = ',\n|{}[]()<>_';
    let j = i;
    while (j < text.length) {
      // Escaped brackets: \( \) \[ \] \{ \} → consume as literal text
      if (text[j] === '\\' && j + 1 < text.length && '()[]{}' .includes(text[j + 1])) {
        j += 2;
        continue;
      }
      if (specials.includes(text[j])) break;
      if (/[\d.]/.test(text[j]) && /^-?\d*\.?\d+::/.test(text.substring(j))) break;
      if (/^embedding:/i.test(text.substring(j))) break;
      if (text.substring(j, j + 5) === 'BREAK' && (j === i || /\s/.test(text[j - 1]))) break;
      if (text.substring(j, j + 3) === 'AND' && (j === i || /\s/.test(text[j - 1])) && (j + 3 >= text.length || /\s/.test(text[j + 3]))) break;
      j++;
    }
    return j;
  }

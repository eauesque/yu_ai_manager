  function renderNaiWeight(tok) {
    const w = tok.meta.weight;
    const cls = w > 1 ? 'ps-w-high' : (w < 0 ? 'ps-w-neg' : (w < 1 ? 'ps-w-low' : 'ps-w-normal'));
    // Use original text from tok.value to preserve exact character count (e.g. ".8" not "0.8")
    // tok.value is "weight::content::" — extract the weight portion before first "::"
    const rawWeight = tok.value.substring(0, tok.value.indexOf('::'));
    const rawContent = tok.value.substring(tok.value.indexOf('::') + 2, tok.value.lastIndexOf('::'));
    const tip = (window.tr?.('prompt_syntax.nai_numeric_emphasis', 'NAI numeric emphasis: ×{w}') || 'NAI numeric emphasis: ×{w}').replace('{w}', w);
    return `<span class="ps-nai-w ${cls}" title="${esc(tip)}"><span class="ps-weight">${esc(rawWeight)}</span><span class="ps-delim">::</span>${esc(rawContent)}<span class="ps-delim">::</span></span>`;
  }

  function renderNaiChoice(tok) {
    const choices = tok.meta.choices;
    const tip = (window.tr?.('prompt_syntax.nai_randomizer', 'NAI Randomizer: {n} choices') || 'NAI Randomizer: {n} choices').replace('{n}', choices.length);
    const inner = choices.map((c) => esc(c)).join('<span class="ps-pipe">|</span>');
    return `<span class="ps-nai-choice" title="${esc(tip)}"><span class="ps-delim">||</span>${inner}<span class="ps-delim">||</span></span>`;
  }

  function renderNaiMixing(tok) {
    if (tok.meta?.isSeparator) {
      return '<span class="ps-mixing-sep">|</span>';
    }
    if (tok.meta?.weight !== undefined) {
      return `<span class="ps-mixing-w"><span class="ps-delim">:</span><span class="ps-weight">${esc(String(tok.meta.weight))}</span></span>`;
    }
    return esc(tok.value);
  }

  function renderSdWeight(tok) {
    const w = tok.meta.weight;
    const cls = w > 1 ? 'ps-w-high' : (w < 0 ? 'ps-w-neg' : (w < 1 ? 'ps-w-low' : 'ps-w-normal'));
    const tip = (window.tr?.('prompt_syntax.sd_weight', 'SD weight: ×{w}') || 'SD weight: ×{w}').replace('{w}', w);
    // Use original text to preserve exact characters (e.g. ".8" not "0.8")
    // tok.value is "(content:weight)" — extract parts preserving original format
    const inner = tok.value.substring(tok.depth, tok.value.length - tok.depth);
    const colonIdx = inner.lastIndexOf(':');
    const rawContent = inner.substring(0, colonIdx);
    const rawWeight = inner.substring(colonIdx + 1).trimEnd();
    return `<span class="ps-sd-w ${cls}" title="${esc(tip)}"><span class="ps-delim">(</span>${esc(rawContent)}<span class="ps-delim">:</span><span class="ps-weight">${esc(rawWeight)}</span><span class="ps-delim">)</span></span>`;
  }

  function renderSdAlternate(tok) {
    const choices = tok.meta.choices;
    const tip = (window.tr?.('prompt_syntax.sd_alternating', 'SD Alternating: {n} choices, alternating each step') || 'SD Alternating: {n} choices, alternating each step').replace('{n}', choices.length);
    const inner = choices.map((c) => esc(c)).join('<span class="ps-pipe">|</span>');
    return `<span class="ps-sd-alt" title="${esc(tip)}"><span class="ps-delim">[</span>${inner}<span class="ps-delim">]</span></span>`;
  }

  function renderSdScheduled(tok) {
    const m = tok.meta;
    const tip = `SD Scheduled: ${m.from || '(なし)'} → ${m.to || '(なし)'} at step ${m.step}`;
    return `<span class="ps-sd-sched" title="${esc(tip)}"><span class="ps-delim">[</span>${esc(m.from)}<span class="ps-delim">:</span>${esc(m.to)}<span class="ps-delim">:</span><span class="ps-weight">${esc(String(m.step))}</span><span class="ps-delim">]</span></span>`;
  }

  function renderDpChoice(tok) {
    const d = tok.depth || 1;
    const choices = tok.meta.choices;
    const inner = choices.map((c) => esc(c)).join('<span class="ps-pipe">|</span>');
    return `<span class="ps-dp-choice"><span class="ps-delim">${esc('{'.repeat(d))}</span>${inner}<span class="ps-delim">${esc('}'.repeat(d))}</span></span>`;
  }

  function renderDpWeighted(tok) {
    const d = tok.depth || 1;
    const parts = tok.meta.choices.map((c) => `<span class="ps-dp-wt">${esc(String(c.weight))}</span><span class="ps-delim">$$</span>${esc(c.text)}`);
    return `<span class="ps-dp-weighted"><span class="ps-delim">${esc('{'.repeat(d))}</span>${parts.join('<span class="ps-pipe">|</span>')}<span class="ps-delim">${esc('}'.repeat(d))}</span></span>`;
  }

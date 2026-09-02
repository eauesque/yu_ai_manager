  const DEPTH_COLORS = ['#ffcc66','#ffaa44','#ff7766','#ee66bb','#bb88ee','#66bbff'];

  function depthColor(d) {
    return DEPTH_COLORS[Math.min(d - 1, DEPTH_COLORS.length - 1)] || DEPTH_COLORS[0];
  }

  function renderDepthBracket(tok, open, close, cls) {
    const d = tok.depth || 1;
    const content = esc(tok.meta?.content || '');
    const color = depthColor(d);
    const terminated = tok.meta?.terminatedBy === '::';
    let tip;
    if (cls === 'ps-nai-em') {
      const w = Math.pow(1.05, d);
      tip = terminated
        ? (window.tr?.('prompt_syntax.nai_emphasis_term', 'NAI emphasis {o}…::: ×{w} ({d} levels, :: terminated)') || 'NAI emphasis {o}…::: ×{w} ({d} levels, :: terminated)').replace('{o}', open.repeat(d)).replace('{w}', w.toFixed(4)).replace('{d}', d)
        : (window.tr?.('prompt_syntax.nai_emphasis', 'NAI emphasis {o}…{c}: ×{w} ({d} levels)') || 'NAI emphasis {o}…{c}: ×{w} ({d} levels)').replace('{o}', open.repeat(d)).replace('{c}', close.repeat(d)).replace('{w}', w.toFixed(4)).replace('{d}', d);
    } else if (cls === 'ps-nai-sup') {
      const w = Math.pow(1.05, -d);
      tip = (window.tr?.('prompt_syntax.nai_suppression', 'NAI suppression {o}…{c}: ×{w} ({d} levels)') || 'NAI suppression {o}…{c}: ×{w} ({d} levels)').replace('{o}', open.repeat(d)).replace('{c}', close.repeat(d)).replace('{w}', w.toFixed(4)).replace('{d}', d);
    } else if (cls === 'ps-sd-em') {
      const w = Math.pow(1.1, d);
      tip = (window.tr?.('prompt_syntax.sd_emphasis', 'SD emphasis {o}…{c}: ×{w} ({d} levels)') || 'SD emphasis {o}…{c}: ×{w} ({d} levels)').replace('{o}', open.repeat(d)).replace('{c}', close.repeat(d)).replace('{w}', w.toFixed(4)).replace('{d}', d);
    } else {
      tip = (window.tr?.('prompt_syntax.label_depth', 'Depth {d}') || 'Depth {d}').replace('{d}', d);
    }
    // Do not generate closing brackets when :: terminator is used.
    // The token value does not contain closing brackets, so generating them
    // would cause character count mismatch between highlight and textarea.
    const closeBracket = terminated ? '' : `<span class="ps-bracket" style="color:${color}">${esc(close.repeat(d))}</span>`;
    return `<span class="${cls}" style="--depth-color:${color}" title="${esc(tip)}"><span class="ps-bracket" style="color:${color}">${esc(open.repeat(d))}</span>${content}${closeBracket}</span>`;
  }

  function esc(s) {
    if (!s) return '';
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

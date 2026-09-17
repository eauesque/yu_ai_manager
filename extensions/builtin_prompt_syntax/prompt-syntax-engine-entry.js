  // ─── Unified API ───
  function analyze(text) {
    const tokens = tokenize(text || '');
    const syntax = detectSyntax(tokens);
    const errors = detectErrors(tokens);
    for (const w of syntax.warnings) errors.push({level:w.level,message:w.message,start:0,end:(text||'').length});
    return { tokens, syntax, errors, html: toHighlightHTML(tokens) };
  }

  return { T, SYNTAX, tokenize, detectSyntax, detectErrors, toHighlightHTML, analyze, depthColor };
})();

if (typeof module !== 'undefined' && module.exports) module.exports = PromptSyntax;

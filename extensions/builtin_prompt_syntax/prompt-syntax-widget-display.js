  function renderDisplay(container, text, opts = {}) {
    const { showSyntaxBadge = true } = opts;
    const analysis = PromptSyntax.analyze(text);

    let html = `<div class="ps-display">${analysis.html}</div>`;
    if (showSyntaxBadge) {
      const syn = analysis.syntax.syntax;
      html += `<div style="margin-top:4px;"><span class="ps-syntax-badge ${syn}" style="font-size:10px;">${SYNTAX_LABELS[syn] || syn}</span></div>`;
    }

    container.innerHTML = html;
    return analysis;
  }

  function highlight(text) {
    return PromptSyntax.toHighlightHTML(PromptSyntax.tokenize(text || ''));
  }

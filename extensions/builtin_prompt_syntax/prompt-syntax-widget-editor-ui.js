  function createEditorElements(container, opts = {}) {
    const {
      value = '',
      placeholder = '',
      rows = 6,
      showSyntaxBar = true,
      showErrors = true,
      ariaLabel = '',
    } = opts;

    container.innerHTML = '';
    container.classList.add('ps-editor-container');
    // Prevent password managers (1Password, LastPass) from treating
    // prompt textareas as login fields
    container.setAttribute('data-1p-ignore', '');
    container.setAttribute('data-lpignore', 'true');

    const wrap = document.createElement('div');
    wrap.className = 'ps-editor-wrap';

    const highlight = document.createElement('div');
    highlight.className = 'ps-highlight';
    highlight.setAttribute('aria-hidden', 'true');

    const textarea = document.createElement('textarea');
    textarea.className = 'ps-textarea';
    textarea.placeholder = placeholder;
    textarea.rows = rows;
    textarea.spellcheck = false;
    textarea.autocomplete = 'off';
    textarea.setAttribute('data-1p-ignore', '');
    textarea.setAttribute('data-lpignore', 'true');
    textarea.setAttribute('data-form-type', 'other');
    textarea.value = value;
    textarea.setAttribute('aria-label', ariaLabel || placeholder || 'Prompt input');

    wrap.appendChild(highlight);
    wrap.appendChild(textarea);
    container.appendChild(wrap);

    let syntaxBar = null;
    if (showSyntaxBar) {
      syntaxBar = document.createElement('div');
      syntaxBar.className = 'ps-syntax-bar';
      const badgeSpan = document.createElement('span');
      badgeSpan.className = 'ps-syntax-badge unknown';
      badgeSpan.textContent = window.tr?.('prompt_syntax.label_text', 'Text') || 'Text';
      syntaxBar.appendChild(badgeSpan);
      container.appendChild(syntaxBar);
    }

    let errorList = null;
    if (showErrors) {
      errorList = document.createElement('div');
      errorList.className = 'ps-error-list';
      errorList.style.display = 'none';
      container.appendChild(errorList);
    }

    const tooltip = document.createElement('div');
    tooltip.className = 'ps-tooltip';
    tooltip.style.display = 'none';
    container.appendChild(tooltip);

    return { wrap, highlight, textarea, syntaxBar, errorList, tooltip };
  }

  function updateEditorLayout(wrap, textarea, rows) {
    const minH = rows * 20 + 20;
    const h = Math.max(minH, textarea.scrollHeight);
    // Account for wrap border under border-box to prevent 2px-per-update shrink loop
    const cs = getComputedStyle(wrap);
    const borderY = parseFloat(cs.borderTopWidth || '0') + parseFloat(cs.borderBottomWidth || '0');
    wrap.style.height = `${h + borderY}px`;
  }

  function buildSyntaxBarHtml(analysis, text) {
    const syn = analysis.syntax;
    let barHtml = `<span class="ps-syntax-badge ${syn.syntax}">${SYNTAX_LABELS[syn.syntax] || syn.syntax}</span>`;

    const counts = {};
    for (const tok of analysis.tokens) {
      if (tok.type !== 'text' && tok.type !== 'comma' && tok.type !== 'newline') {
        counts[tok.type] = (counts[tok.type] || 0) + 1;
      }
    }
    const tagCount = text.split(',').filter((t) => t.trim()).length;
    const tagLabel = (window.tr?.('prompt_syntax.label_tag_count', 'Tags: {n}') || 'Tags: {n}').replace('{n}', tagCount);
    barHtml += `<span style="color:#888;">${escHtml(tagLabel)}</span>`;

    if (counts.sd_lora) barHtml += `<span style="color:#e67e22;">LoRA: ${counts.sd_lora}</span>`;
    if (counts.dp_choice || counts.nai_choice) {
      const selCount = (counts.dp_choice || 0) + (counts.nai_choice || 0);
      const selLabel = (window.tr?.('prompt_syntax.label_selection_count', 'Selected: {n}') || 'Selected: {n}').replace('{n}', selCount);
      barHtml += `<span style="color:#f1c40f;">${escHtml(selLabel)}</span>`;
    }
    if (counts.dp_wildcard) barHtml += `<span style="color:#e056a0;">WC: ${counts.dp_wildcard}</span>`;

    if (analysis.errors.length > 0) {
      const errCount = analysis.errors.filter((e) => e.level === 'error').length;
      const warnCount = analysis.errors.filter((e) => e.level === 'warning').length;
      if (errCount) barHtml += `<span style="color:#e74c3c;">❌ ${errCount}</span>`;
      if (warnCount) barHtml += `<span style="color:#f39c12;">⚠ ${warnCount}</span>`;
    }

    return barHtml;
  }

  function renderErrorList(errorList, errors) {
    if (!errorList) return;
    if (errors.length === 0) {
      errorList.style.display = 'none';
      return;
    }

    errorList.style.display = 'block';
    errorList.innerHTML = errors.slice(0, 5).map((e) => {
      const icon = e.level === 'error' ? '❌' : '⚠️';
      return `<div class="ps-error-item ${e.level}"><span class="ps-error-icon">${icon}</span>${escHtml(e.message)}</div>`;
    }).join('');

    if (errors.length > 5) {
      const moreLabel = (window.tr?.('prompt_syntax.label_more_items', '...and {n} more') || '...and {n} more').replace('{n}', errors.length - 5);
      errorList.innerHTML += `<div class="ps-error-item warning" style="color:#888;">${escHtml(moreLabel)}</div>`;
    }
  }

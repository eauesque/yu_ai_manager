  function createEditor(container, opts = {}) {
    const {
      value = '',
      placeholder = '',
      onChange = null,
      rows = 6,
      showSyntaxBar = true,
      showErrors = true,
      ariaLabel = '',
    } = opts;

    const {
      wrap,
      highlight,
      textarea,
      syntaxBar,
      errorList,
      tooltip,
    } = createEditorElements(container, {
      value,
      placeholder,
      rows,
      showSyntaxBar,
      showErrors,
      ariaLabel,
    });

    let debounceTimer = null;
    let lastAnalysis = null;
    let tipDebounce = null;

    function update() {
      const text = textarea.value;
      const analysis = PromptSyntax.analyze(text);
      lastAnalysis = analysis;

      highlight.innerHTML = analysis.html || '';

      updateEditorLayout(wrap, textarea, rows);

      // Sync scroll in next frame — ensures layout (including scrollHeight)
      // is fully resolved before setting scrollTop/scrollLeft
      requestAnimationFrame(() => {
        highlight.scrollTop = textarea.scrollTop;
        highlight.scrollLeft = textarea.scrollLeft;
      });

      if (syntaxBar) {
        syntaxBar.innerHTML = buildSyntaxBarHtml(analysis, text);
      }

      renderErrorList(errorList, analysis.errors);

      if (onChange) onChange(text, analysis);
    }

    textarea.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(update, 50);
    });

    textarea.addEventListener('scroll', () => {
      highlight.scrollTop = textarea.scrollTop;
      highlight.scrollLeft = textarea.scrollLeft;
    });

    function showTokenTip() {
      if (!lastAnalysis) return;
      const pos = textarea.selectionStart;
      const tok = findTokenAt(lastAnalysis.tokens, pos);
      if (!tok || tok.type === 'text' || tok.type === 'comma' || tok.type === 'newline') {
        tooltip.style.display = 'none';
        return;
      }
      const info = describeToken(tok);
      if (!info) {
        tooltip.style.display = 'none';
        return;
      }
      tooltip.innerHTML = info;
      tooltip.style.display = 'block';
    }

    textarea.addEventListener('keyup', (e) => {
      if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) {
        clearTimeout(tipDebounce);
        tipDebounce = setTimeout(showTokenTip, 80);
      }
    });
    textarea.addEventListener('click', () => {
      clearTimeout(tipDebounce);
      tipDebounce = setTimeout(showTokenTip, 80);
    });
    textarea.addEventListener('blur', () => { tooltip.style.display = 'none'; });

    // Re-sync layout when the wrap element is resized by external reflows
    // (e.g. result area growing with generated images). Without this, the
    // highlight layer drifts from the textarea after page layout changes.
    let resizeObs = null;
    if (typeof ResizeObserver !== 'undefined') {
      resizeObs = new ResizeObserver(() => {
        // Defer to next frame to break synchronous resize loop
        requestAnimationFrame(() => {
          updateEditorLayout(wrap, textarea, rows);
          highlight.scrollTop = textarea.scrollTop;
          highlight.scrollLeft = textarea.scrollLeft;
        });
      });
      resizeObs.observe(wrap);
    }

    if (value) update();

    return {
      getValue: () => textarea.value,
      setValue: (v) => {
        // execCommand('insertText') silently fails in newer Brave/Chrome,
        // causing the textarea to remain in select-all state without updating.
        // Use direct assignment + input event dispatch for reliable sync.
        // (Undo history is lost, but sync reliability takes priority)
        textarea.value = v;
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        update();
      },
      getAnalysis: () => lastAnalysis,
      getTextarea: () => textarea,
      update,
      destroy: () => {
        if (resizeObs) resizeObs.disconnect();
        container.innerHTML = '';
      },
    };
  }

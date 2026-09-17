  // ─── Highlight HTML ───

  function toHighlightHTML(tokens) {
    let html = '';
    for (const tok of tokens) {
      const v = esc(tok.value);
      switch (tok.type) {
        case T.NAI_WEIGHT:   html += renderNaiWeight(tok); break;
        case T.NAI_CHOICE:   html += renderNaiChoice(tok); break;
        case T.NAI_EMPHASIS: html += renderDepthBracket(tok, '{', '}', 'ps-nai-em'); break;
        case T.NAI_SUPPRESS: html += renderDepthBracket(tok, '[', ']', 'ps-nai-sup'); break;
        case T.NAI_MIXING:   html += renderNaiMixing(tok); break;
        case T.SD_WEIGHT:    html += renderSdWeight(tok); break;
        case T.SD_EMPHASIS:  html += renderDepthBracket(tok, '(', ')', 'ps-sd-em'); break;
        case T.SD_LORA:      html += `<span class="ps-lora" title="LoRA: ${esc(tok.meta?.name || '')} (×${tok.meta?.weight || 1})">${v}</span>`; break;
        case T.SD_EMBEDDING: html += `<span class="ps-embed" title="Embedding: ${esc(tok.meta?.name || '')}">${v}</span>`; break;
        case T.SD_HYPERNET:  html += `<span class="ps-hyper" title="HyperNetwork: ${esc(tok.meta?.name || '')}">${v}</span>`; break;
        case T.SD_ALTERNATE: html += renderSdAlternate(tok); break;
        case T.SD_SCHEDULED: html += renderSdScheduled(tok); break;
        case T.SD_AND:       html += `<span class="ps-sd-and" title="${esc(window.tr?.('prompt_syntax.sd_composable', 'SD Composable Diffusion (AND)') || 'SD Composable Diffusion (AND)')}">${v}</span>`; break;
        case T.SD_AND:       html += '<span class="ps-sd-and" title="' + esc(window.tr?.('prompt_syntax.sd_composable', 'SD Composable Diffusion (AND)') || 'SD Composable Diffusion (AND)') + '">AND</span>'; break;
        case T.DP_CHOICE:    html += renderDpChoice(tok); break;
        case T.DP_WEIGHTED:  html += renderDpWeighted(tok); break;
        case T.DP_WILDCARD:  html += `<span class="ps-wildcard" title="Wildcard: ${esc(tok.meta?.name || '')}">${v}</span>`; break;
        case T.NAMESPACE:    html += `<span class="ps-ns">${v}</span>`; break;
        case T.BREAK:        html += `<span class="ps-break">${v}</span>`; break;
        case T.COMMA:        html += '<span class="ps-comma">,</span>'; break;
        case T.NEWLINE:      html += '\n'; break;
        case T.ERROR:        html += `<span class="ps-error" title="${esc(tok.meta?.error || '')}">${v}</span>`; break;
        default:             html += v;
      }
    }
    return html;
  }

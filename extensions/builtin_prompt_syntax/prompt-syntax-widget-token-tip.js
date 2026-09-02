  function escHtml(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function findTokenAt(tokens, pos) {
    for (const tok of tokens) {
      if (pos >= tok.start && pos < tok.end) return tok;
    }
    return null;
  }

  function describeToken(tok) {
    const T = PromptSyntax.T;
    switch (tok.type) {
      case T.NAI_WEIGHT: {
        const w = tok.meta.weight;
        const pct = ((w - 1) * 100).toFixed(1);
        const sign = w >= 1 ? '+' : '';
        const weightLabel = window.tr?.('prompt_syntax.label_weight', 'Weight') || 'Weight';
        const contentLabel = window.tr?.('prompt_syntax.label_content', 'Content') || 'Content';
        return `<b>${window.tr?.('prompt_syntax.nai_numeric_emphasis', 'NAI numeric emphasis') || 'NAI numeric emphasis'}</b><br>${weightLabel}: <b>×${w}</b> (${sign}${pct}%)<br>${contentLabel}: ${escHtml(tok.meta.content)}`;
      }
      case T.NAI_EMPHASIS: {
        const d = tok.depth || 1;
        const w = Math.pow(1.05, d);
        const pct = ((w - 1) * 100).toFixed(1);
        const depthLabel = window.tr?.('prompt_syntax.label_depth', 'Depth') || 'Depth';
        return `<b>${window.tr?.('prompt_syntax.nai_emphasis', 'NAI Emphasis') || 'NAI Emphasis'}</b> ${'{ '.repeat(Math.min(d, 3))}… ${'} '.repeat(Math.min(d, 3))}<br>${depthLabel}: <b>${d}</b> → <b>×${w.toFixed(4)}</b> (+${pct}%)`;
      }
      case T.NAI_SUPPRESS: {
        const d = tok.depth || 1;
        const w = Math.pow(1.05, -d);
        const pct = ((1 - w) * 100).toFixed(1);
        const depthLabel = window.tr?.('prompt_syntax.label_depth', 'Depth') || 'Depth';
        return `<b>${window.tr?.('prompt_syntax.nai_suppression', 'NAI Suppression') || 'NAI Suppression'}</b> ${'[ '.repeat(Math.min(d, 3))}… ${'] '.repeat(Math.min(d, 3))}<br>${depthLabel}: <b>${d}</b> → <b>×${w.toFixed(4)}</b> (−${pct}%)`;
      }
      case T.NAI_CHOICE: {
        const n = tok.meta.choices.length;
        const choiceLabel = window.tr?.('prompt_syntax.label_choices', 'choices') || 'choices';
        const eachLabel = window.tr?.('prompt_syntax.label_each_percent', 'each') || 'each';
        return `<b>${window.tr?.('prompt_syntax.nai_randomizer_label', 'NAI Randomizer') || 'NAI Randomizer'}</b><br>${n}${choiceLabel} (${eachLabel} ${(100 / n).toFixed(1)}%)`;
      }
      case T.NAI_MIXING: {
        if (tok.meta?.weight !== undefined) return `<b>${window.tr?.('prompt_syntax.nai_blend_weight', 'NAI Blend Weight') || 'NAI Blend Weight'}</b>: ${tok.meta.weight}`;
        if (tok.meta?.isSeparator) {
          const avgLabel = window.tr?.('prompt_syntax.nai_vector_average', 'Vector averaging') || 'Vector averaging';
          return `<b>${window.tr?.('prompt_syntax.nai_prompt_mixing', 'NAI Prompt Mixing') || 'NAI Prompt Mixing'}</b><br>${avgLabel}`;
        }
        return null;
      }
      case T.SD_WEIGHT: {
        const w = tok.meta.weight;
        const pct = ((w - 1) * 100).toFixed(1);
        const sign = w >= 1 ? '+' : '';
        const weightLabel = window.tr?.('prompt_syntax.label_weight', 'Weight') || 'Weight';
        const contentLabel = window.tr?.('prompt_syntax.label_content', 'Content') || 'Content';
        return `<b>${window.tr?.('prompt_syntax.sd_weight_label', 'SD Weight') || 'SD Weight'}</b><br>${weightLabel}: <b>×${w}</b> (${sign}${pct}%)<br>${contentLabel}: ${escHtml(tok.meta.content)}`;
      }
      case T.SD_EMPHASIS: {
        const d = tok.depth || 1;
        const w = Math.pow(1.1, d);
        const pct = ((w - 1) * 100).toFixed(1);
        const depthLabel = window.tr?.('prompt_syntax.label_depth', 'Depth') || 'Depth';
        return `<b>${window.tr?.('prompt_syntax.sd_emphasis_label', 'SD Emphasis') || 'SD Emphasis'}</b> ${( '('.repeat(Math.min(d, 3)))}… ${( ')'.repeat(Math.min(d, 3)))}<br>${depthLabel}: <b>${d}</b> → <b>×${w.toFixed(4)}</b> (+${pct}%)`;
      }
      case T.SD_LORA: {
        const nameLabel = window.tr?.('prompt_syntax.label_name', 'Name') || 'Name';
        const weightLabel = window.tr?.('prompt_syntax.label_weight', 'Weight') || 'Weight';
        return `<b>LoRA</b><br>${nameLabel}: ${escHtml(tok.meta.name)}<br>${weightLabel}: ×${tok.meta.weight}`;
      }
      case T.SD_EMBEDDING: {
        const nameLabel = window.tr?.('prompt_syntax.label_name', 'Name') || 'Name';
        return `<b>Embedding</b><br>${nameLabel}: ${escHtml(tok.meta.name)}`;
      }
      case T.SD_HYPERNET: {
        const nameLabel = window.tr?.('prompt_syntax.label_name', 'Name') || 'Name';
        return `<b>HyperNetwork</b><br>${nameLabel}: ${escHtml(tok.meta.name)}`;
      }
      case T.SD_ALTERNATE: {
        const n = tok.meta.choices.length;
        const choiceLabel = window.tr?.('prompt_syntax.label_choices', 'choices') || 'choices';
        const eachLabel = window.tr?.('prompt_syntax.label_each_percent', 'each') || 'each';
        const alternateSwitchLabel = window.tr?.('prompt_syntax.sd_alternate_switch', 'alternating each step') || 'alternating each step';
        return `<b>${window.tr?.('prompt_syntax.sd_alternating_label', 'SD Alternating') || 'SD Alternating'}</b><br>${n}${choiceLabel}, ${alternateSwitchLabel}`;
      }
      case T.SD_AND: {
        const vectorLabel = window.tr?.('prompt_syntax.sd_vector_synthesis', 'Vector synthesis of multiple prompts') || 'Vector synthesis of multiple prompts';
        const equivalentLabel = window.tr?.('prompt_syntax.sd_equivalent_to_nai', 'equivalent to NAI Prompt Mixing (|)') || 'equivalent to NAI Prompt Mixing (|)';
        return `<b>${window.tr?.('prompt_syntax.sd_composable', 'SD Composable Diffusion (AND)') || 'SD Composable Diffusion (AND)'}</b><br>${vectorLabel}<br>${equivalentLabel}`;
      }
      case T.SD_SCHEDULED: {
        const m = tok.meta;
        const stepPct = m.step < 1 ? `${(m.step * 100).toFixed(0)}%` : `step ${m.step}`;
        const firstHalfLabel = window.tr?.('prompt_syntax.label_first_half', 'First half') || 'First half';
        const secondHalfLabel = window.tr?.('prompt_syntax.label_second_half', 'Second half') || 'Second half';
        const switchLabel = window.tr?.('prompt_syntax.label_switch', 'Switch') || 'Switch';
        const noneLabel = window.tr?.('prompt_syntax.label_none', '(none)') || '(none)';
        return `<b>${window.tr?.('prompt_syntax.sd_scheduled_label', 'SD Scheduled') || 'SD Scheduled'}</b><br>${firstHalfLabel}: ${escHtml(m.from) || noneLabel}<br>${secondHalfLabel}: ${escHtml(m.to) || noneLabel}<br>${switchLabel}: ${stepPct}`;
      }
      case T.DP_CHOICE: {
        const n = tok.meta.choices.length;
        const choiceLabel = window.tr?.('prompt_syntax.label_choices', 'choices') || 'choices';
        const eachLabel = window.tr?.('prompt_syntax.label_each_percent', 'each') || 'each';
        const randomSelLabel = window.tr?.('prompt_syntax.dp_random_selection', 'Random selection') || 'Random selection';
        return `<b>Dynamic Prompts</b> ${randomSelLabel}<br>${n}${choiceLabel} (${eachLabel} ${(100 / n).toFixed(1)}%)`;
      }
      case T.DP_WEIGHTED: {
        const total = tok.meta.choices.reduce((s, c) => s + c.weight, 0);
        const items = tok.meta.choices.map((c) => `${escHtml(c.text)}: ${c.weight}/${total} (${((c.weight / total) * 100).toFixed(0)}%)`).join('<br>');
        return `<b>${window.tr?.('prompt_syntax.dp_weighted_selection', 'DP Weighted Selection') || 'DP Weighted Selection'}</b><br>${items}`;
      }
      case T.DP_WILDCARD: {
        const nameLabel = window.tr?.('prompt_syntax.label_name', 'Name') || 'Name';
        const randomSelectLabel = window.tr?.('prompt_syntax.dp_random_from_file', 'Random selection from file') || 'Random selection from file';
        return `<b>Wildcard</b><br>${nameLabel}: ${escHtml(tok.meta.name)}<br>${randomSelectLabel}`;
      }
      case T.BREAK: {
        const segmentLabel = window.tr?.('prompt_syntax.label_segment_break', 'Prompt segment separator') || 'Prompt segment separator';
        return `<b>BREAK</b><br>${segmentLabel}`;
      }
      case T.ERROR:
        return `<b>${window.tr?.('prompt_syntax.error_syntax', 'Syntax error') || 'Syntax error'}</b><br>${escHtml(tok.meta?.error || '')}`;
      default:
        return null;
    }
  }

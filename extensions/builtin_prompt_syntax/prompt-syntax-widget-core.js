/**
 * prompt-syntax-widget.js — shell
 */

const PromptSyntaxWidget = (function() {
  'use strict';

  const SYNTAX_LABELS = {
    nai: 'NovelAI',
    sd: 'Stable Diffusion',
    dynamic_prompts: 'Dynamic Prompts',
    mixed: window.tr?.('prompt_syntax.label_mixed', '⚠ Mixed') || '⚠ Mixed',
    unknown: window.tr?.('prompt_syntax.label_text', 'Text') || 'Text',
  };

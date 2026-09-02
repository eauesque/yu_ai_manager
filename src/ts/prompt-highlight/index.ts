// prompt-highlight — entry point
import { installWindowApi } from '../shared/window-api';
import * as weights from './renderers-weights';
import * as tokens from './renderers-tokens';
import './helpers';
import { highlightPrompt } from './core';

installWindowApi('promptHighlightApi', {
  highlightOperator: tokens.highlightOperator,
  highlightLora: weights.highlightLora,
  highlightEmbedding: tokens.highlightEmbedding,
  highlightWeight: weights.highlightWeight,
  highlightNovelAIWeight: weights.highlightNovelAIWeight,
  highlightRandomChoice: tokens.highlightRandomChoice,
  highlightParen: weights.highlightParen,
  highlightNormal: tokens.highlightNormal,
  highlightPrompt,
});

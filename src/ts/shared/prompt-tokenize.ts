/**
 * Tokenize a Stable Diffusion / NovelAI-style prompt string into segments
 * for editorial typesetting. Plain natural-language portions are emitted
 * as `text` tokens (rendered in Fraunces roman); syntactic constructs are
 * emitted as `weight` / `lora` / `embed` tokens so the modal can flip
 * them to inline JetBrains Mono.
 *
 * Recognised constructs:
 *   - `(any text:1.2)`              -> { type: "weight" }
 *   - `<lora:foo:0.8>`              -> { type: "lora" }
 *   - `<embed:bar>` or `<bar>`      -> { type: "embed" }
 *
 * Anything not matching above falls through as `text`.
 */

export type PromptToken =
  | { type: "text"; value: string }
  | { type: "weight"; value: string }
  | { type: "lora"; value: string }
  | { type: "embed"; value: string };

const PATTERN = /(\([^()]*:\d+(?:\.\d+)?\))|(<lora:[^>]+>)|(<[^>]+>)/g;

export function tokenizePrompt(input: string): PromptToken[] {
  const tokens: PromptToken[] = [];
  if (!input) return tokens;

  let cursor = 0;
  for (const match of input.matchAll(PATTERN)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      tokens.push({ type: "text", value: input.slice(cursor, start) });
    }
    if (match[1] !== undefined) {
      tokens.push({ type: "weight", value: match[1] });
    } else if (match[2] !== undefined) {
      tokens.push({ type: "lora", value: match[2] });
    } else if (match[3] !== undefined) {
      tokens.push({ type: "embed", value: match[3] });
    }
    cursor = start + match[0].length;
  }

  if (cursor < input.length) {
    tokens.push({ type: "text", value: input.slice(cursor) });
  }

  return tokens;
}

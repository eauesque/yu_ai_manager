/**
 * Detect SD (A1111) vs NAI prompt syntax.
 * Pure functions — no DOM dependencies.
 *
 * Pre-processing note: stripDynamicPrompts removes {a|b|c} as a DP-noise
 * mitigation for NAI detection; it is not a full DP parser.
 */

// --- SD (A1111) detection patterns ---
const SD_PATTERNS = [
  /\(\([^()]+\)\)/,                    // ((double bracket emphasis))
  /\([^()]+:\s*-?\d*\.?\d+\)/,         // (tag:1.3) or (tag:-0.5) explicit weight
  /<lora:[^>]+>/,                       // <lora:name:weight>
  /<embedding:[^>]+>/,                  // <embedding:name>
];

// --- NAI detection patterns (applied after pre-processing) ---
const NAI_BRACKET_PATTERN = /\{[^}]+\}/;
const NAI_PIPE_PATTERN = /\|/;

/**
 * Remove A1111 Dynamic Prompts wildcards: {a|b|c}, {2$$a|b|c}, __name__.
 * Prevents NAI pattern false-positives on DP syntax.
 */
function stripDynamicPrompts(s: string): string {
  return s
    .replace(/\{[^{}]*\|[^{}]*\}/g, '')  // {a|b|...} DP choice groups
    .replace(/__[^\s]+__/g, '');           // __wildcard__ (underscore chars allowed in name)
}

/**
 * Remove A1111 bracket groups [...] so that the | inside [a|b|c]
 * alternation is not mistaken for NAI mixing syntax.
 */
function stripBracketGroups(s: string): string {
  return s.replace(/\[[^\[\]]*\]/g, '');
}

function hasSdPatterns(prompt: string): boolean {
  return SD_PATTERNS.some((re) => re.test(prompt));
}

function hasNaiPatterns(prompt: string): boolean {
  const cleaned = stripBracketGroups(stripDynamicPrompts(prompt));
  return NAI_BRACKET_PATTERN.test(cleaned) || NAI_PIPE_PATTERN.test(cleaned);
}

/**
 * Detect the prompt syntax convention used in the given string.
 *
 * Pre-processing for NAI detection:
 *   - stripDynamicPrompts(): removes {a|b|c} and __wildcard__ (A1111 Dynamic Prompts)
 *   - stripBracketGroups(): removes [...] to exclude A1111 alternation [a|b|c]
 *
 * Return values:
 *   'sd'      – SD-specific patterns found, no NAI-specific patterns
 *   'nai'     – NAI-specific patterns found, no SD-specific patterns
 *   'mixed'   – both SD-specific and NAI-specific patterns found
 *   'unknown' – no recognisable patterns (plain text or [tag] de-emphasis only)
 *
 * Banner display logic:
 *   NAI bridge: show banner when result is 'sd' or 'mixed'
 *   SD bridge:  show banner when result is 'nai' or 'mixed'
 */
export function detectSyntax(prompt: string): 'sd' | 'nai' | 'mixed' | 'unknown' {
  const sd = hasSdPatterns(prompt);
  const nai = hasNaiPatterns(prompt);
  if (sd && nai) return 'mixed';
  if (sd) return 'sd';
  if (nai) return 'nai';
  return 'unknown';
}

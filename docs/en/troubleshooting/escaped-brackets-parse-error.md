# Escaped Brackets `\(` `\[` `\{` Causing Syntax Color Loss

**Version**: Fixed in v2.21.26
**Severity**: P1 -- affects all wildcard files
**Discovered**: 2026-02-23

---

## Symptoms

The WC Manager loses syntax coloring after encountering `\(` in a wildcard file (e.g., `__characters_genshin_impact__`). The first few lines of the file render with correct colors, but every line following an entry that contains `\(` loses all highlighting.

Specifically:
1. The `(` in `\(` renders as a red ERROR token.
2. All subsequent entries lose syntax highlighting entirely.
3. LoRA tags `<lora:...>` and weights `(tag:1.2)` also lose their colors.

### Example Data Affected

```
lumine \(genshin impact\)
yuko \(girls und panzer\), girls und panzer,
(artist:example_artist \(art style\):1.2)
```

- Line 1: `\(` triggers an ERROR. Everything after `genshin impact\)` becomes an invalid token.
- Line 2 onward: the previous line's `matchParen` scans the remaining text and absorbs it into an oversized token, destroying all colors.
- Line 3 works correctly when `\(` appears inside `()`, because `findMatchingClose` handles the escape properly. This asymmetry was the source of confusion.

---

## Root Cause

### Top-Level Tokenizer Flow (Before Fix)

```
Input: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: 'y' → no matcher matches → findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK, '\' → OK (not in specials)
                '(' → in specials → break → returns j=6
3. TEXT token: "yuko \" [0, 6)     ← '\' is consumed as text
4. i=6: '(' → matchParen(text, 6)
5. matchParen → findMatchingClose(text, 6, '(', ')')
6. findMatchingClose: depth=1, scanning interior:
   - 'g','i','r','l','s'... → OK
   - '\)' → skipped as escape (j += 2)  ← '\)' is NOT recognized as close paren!
   - ',' ' ' 'g','i','r','l','s'... → scans into subsequent lines
   - reaches EOF without finding a matching ')'
   → return null
7. matchParen: result === null → ERROR token { type: 'error', value: '(' }
8. i=7: remaining text is parsed in fragments; tokens that should be contiguous
   are split apart, destroying all highlighting on subsequent lines
```

**The core issue**: `findTextEnd` consumes `\` as ordinary text and then stops at the following `(`. The bare `(` reaches the `text[i] === '('` check in the main loop and triggers `matchParen`. Inside `findMatchingClose`, `\)` is skipped as an escape, so it is never recognized as a close paren. The match search runs all the way to EOF.

### Asymmetry Between Bracket Interior and Top Level

`findMatchingClose` already has escape handling:
```javascript
if (text[j] === '\\' && j + 1 < text.length) { j += 2; continue; }
```

This works correctly for escapes **inside brackets**, such as `(artist:example_artist \(art style\):1.2)`. The outer `()` matches first, and the inner `\(` `\)` pairs are skipped.

At the **top level**, however, `\` and `(` are processed in separate steps and are never recognized as a single escape sequence. This is the root cause of the bug.

---

## Fix

### Escape Bracket Handling Added to `findTextEnd()`

**File**: `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js`

```javascript
function findTextEnd(text, i) {
    const specials = ',\n|{}[]()<>_';
    let j = i;
    while (j < text.length) {
      // Escaped brackets: \( \) \[ \] \{ \} → consume as literal text
      if (text[j] === '\\' && j + 1 < text.length && '()[]{}'.includes(text[j + 1])) {
        j += 2;
        continue;
      }
      if (specials.includes(text[j])) break;
      // ... existing checks ...
    }
    return j;
}
```

### Flow After the Fix

```
Input: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK
                '\' + '(' → escaped bracket detected → j += 2 (consumes both)
                'g','i','r','l','s',' ','u','n','d',' ','p','a','n','z','e','r' → OK
                '\' + ')' → escaped bracket detected → j += 2
                ')' already consumed → ',' → specials → break
3. TEXT token: "yuko \(girls und panzer\)" [0, 30)  ← entire span is one token
4. i=30: ',' → COMMA token
5. Parsing continues normally
```

### Scope of Change

- All 6 escape sequences (`\(`, `\)`, `\[`, `\]`, `\{`, `\}`) are now consumed as text at the top level.
- Escape handling inside bracket expressions (`findMatchingClose` / `findMatchingBrace`) is unchanged.
- Normal bracket matching for `()`, `[]`, `{}` is unaffected.
- The fix conforms to the escape notation defined in Section 9 of the prompt syntax specification.

---

## Verification

| Test | Expected Result | Status |
|------|-----------------|--------|
| `lumine \(genshin impact\)` | Single TEXT token, no ERROR | PASS |
| `(masterpiece:1.2)` after multiple `\(` lines | Recognized as SD_WEIGHT | PASS |
| `\[brackets\]` and `\{braces\}` | TEXT token, no ERROR | PASS |
| Normal `(masterpiece:1.2)` | Works as SD_WEIGHT | PASS |
| Normal `{emphasis}` | Works as NAI_EMPHASIS | PASS |
| Normal `[suppress]` | Works as NAI_SUPPRESS | PASS |
| `\(` inside brackets: `(artist:a \(b\):1.2)` | Works as SD_WEIGHT | PASS |
| Plain-text reconstruction | Matches input | PASS |

---

## Related Files

- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js` -- fix location
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-main.js` -- tokenizer main loop
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-helpers.js` -- `findMatchingClose`
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-paren.js` -- `matchParen`
- `docs/development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md` -- Section 9 escape specification

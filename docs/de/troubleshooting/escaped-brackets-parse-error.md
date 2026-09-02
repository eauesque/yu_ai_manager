# Bug: Verlust der Syntaxfärbung durch Escape-Klammern `\(` `\[` `\{`

**Version**: Behoben in v2.21.26
**Schweregrad**: P1 -- betrifft Wildcard-Dateien insgesamt
**Entdeckungstag**: 2026-02-23

---

## Symptom

Beim Öffnen einer Wildcard-Datei im WC Manager (z. B. `__characters_genshin_impact__`)
funktioniert die Syntaxfärbung nur für die ersten paar Zeilen am Dateianfang;
ab Einträgen mit `\(` verschwinden sämtliche Farben in allen folgenden Zeilen.

Konkret:
1. Das `(` in `\(` wird als roter ERROR-Token angezeigt
2. In allen Einträgen ab dieser Zeile geht die Syntaxhervorhebung verloren
3. Auch LoRA-Tags `<lora:...>` und Gewichtungen `(tag:1.2)` werden nicht mehr eingefärbt

### Beispiele betroffener Daten

```
lumine \(genshin impact\)
yuko \(girls und panzer\), girls und panzer,
(artist:example_artist \(art style\):1.2)
```

- Zeile 1: ERROR ab `\(`, ab `genshin impact\)` ungültige Tokens
- Ab Zeile 2: Das `matchParen` der Vorzeile bleibt aktiv und saugt den restlichen Text in einen riesigen Token ein, wodurch Farben verschwinden
- Zeile 3: Da innerhalb von `()` ein `\(` steht, funktioniert das Escape-Handling in `findMatchingClose` korrekt (dieser Unterschied war Ursache der Verwirrung)

---

## Root Cause

### Top-Level-Flow des Tokenizers (vor der Korrektur)

```
Eingabe: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: 'y' → kein Matcher passt → findTextEnd(text, 0) aufrufen
2. findTextEnd: 'y','u','k','o',' ' → OK, '\' → OK (nicht in specials)
                '(' → in specials enthalten → break → j=6 zurück
3. TEXT-Token: "yuko \" [0, 6)     ← '\' landet im Text
4. i=6: '(' → matchParen(text, 6) aufrufen
5. matchParen → findMatchingClose(text, 6, '(', ')')
6. findMatchingClose: depth=1, interner Scan:
   - 'g','i','r','l','s'... → OK
   - '\)' → als Escape überspringen (j += 2)  ← '\)' wird nicht als Klammerende erkannt!
   - ',' ' ' 'g','i','r','l','s'... → scannt auch die nächste Zeile
   - Bis zum Dateiende kein passendes ')' gefunden
   → return null
7. matchParen: result === null → ERROR-Token { type: 'error', value: '(' }
8. i=7: Folgender Text wird fragmentiert geparst, der eigentlich ein Token sein sollte,
   wird zerstückelt, was die Hervorhebung aller folgenden Zeilen zerstört
```

**Kern des Problems**: `findTextEnd` konsumiert `\` als normalen Text, stoppt beim folgenden
`(`. Das nackte `(` erreicht die Prüfung `text[i] === '('` der Hauptschleife, die dann
`matchParen` auslöst. Innerhalb von `findMatchingClose` wird `\)` als Escape übersprungen,
`\)` daher nicht als Klammerende erkannt, sodass die Match-Suche bis zum Dateiende weiterläuft.

### Asymmetrie zwischen Klammerinnerem und Top-Level

In `findMatchingClose` existiert bereits ein Escape-Handling:
```javascript
if (text[j] === '\\' && j + 1 < text.length) { j += 2; continue; }
```

Dies funktioniert im **Inneren von Klammern** korrekt, etwa für
`(artist:example_artist \(art style\):1.2)` (das äußere `()` matcht zuerst,
innere `\(` `\)` werden übersprungen).

Jedoch im **Top-Level**-`\(` werden `\` und `(` in getrennten Schritten verarbeitet,
sodass sie nicht als Escape erkannt werden. Das ist die Wurzel des Bugs.

---

## Korrektur

### Escape-Klammern-Handling in `findTextEnd()` ergänzt

**Datei**: `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js`

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
      // ... bestehende Checks ...
    }
    return j;
}
```

### Flow nach der Korrektur

```
Eingabe: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: findTextEnd(text, 0) aufrufen
2. findTextEnd: 'y','u','k','o',' ' → OK
                '\' + '(' → Escape-Klammer erkannt → j += 2 (2 Zeichen konsumieren)
                'g','i','r','l','s',' ','u','n','d',' ','p','a','n','z','e','r' → OK
                '\' + ')' → Escape-Klammer erkannt → j += 2
                ')' bereits konsumiert → ',' → specials → break
3. TEXT-Token: "yuko \(girls und panzer\)" [0, 30)  ← alles ein einziger Text
4. i=30: ',' → COMMA-Token
5. Weiteres Parsen funktioniert normal
```

### Umfang der Änderung

- Die 6 Escapes `\(`, `\)`, `\[`, `\]`, `\{`, `\}` werden auf Top-Level als Text behandelt
- Das Escape-Handling im Klammerinneren (`findMatchingClose` / `findMatchingBrace`) bleibt unverändert
- Kein Einfluss auf normale Klammern `()`, `[]`, `{}` und deren Matcher
- Konform mit der in Prompt-Syntax-Spec Section 9 definierten Escape-Notation

---

## Prüfpunkte

| Test | Erwartetes Ergebnis | Status |
|--------|----------|------|
| `lumine \(genshin impact\)` | 1 TEXT-Token, kein ERROR | PASS |
| Nach mehreren `\(`-Zeilen dann `(masterpiece:1.2)` | Korrekt als SD_WEIGHT erkannt | PASS |
| `\[brackets\]` und `\{braces\}` | TEXT-Token, kein ERROR | PASS |
| Normales `(masterpiece:1.2)` | Funktioniert als SD_WEIGHT | PASS |
| Normales `{emphasis}` | Funktioniert als NAI_EMPHASIS | PASS |
| Normales `[suppress]` | Funktioniert als NAI_SUPPRESS | PASS |
| `\(` im Klammerinneren: `(artist:a \(b\):1.2)` | Funktioniert als SD_WEIGHT | PASS |
| Rekonstruktion des Plaintext | Stimmt mit Eingabe überein | PASS |

---

## Verwandte Dateien

- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js` — Korrekturstelle
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-main.js` — Haupttokenizer-Schleife
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-helpers.js` — `findMatchingClose`
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-paren.js` — `matchParen`
- `docs/development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md` — Section 9 Escape-Spec

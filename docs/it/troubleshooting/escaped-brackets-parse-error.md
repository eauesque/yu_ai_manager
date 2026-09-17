# Bug di perdita della colorazione sintattica dovuto a parentesi escaped `\(` `\[` `\{`

**Versione**: corretto in v2.21.26
**Gravità**: P1 — colpisce in generale i file wildcard
**Data di scoperta**: 2026-02-23

---

## Sintomi

Aprendo un file wildcard (ad esempio `__characters_genshin_impact__`) in WC Manager,
solo le prime righe del file mostrano correttamente la colorazione sintattica,
mentre dalla riga che contiene `\(` in poi i colori scompaiono su tutte le righe successive.

Nello specifico:
1. La `(` di `\(` viene visualizzata come token ERROR di colore rosso
2. Dal momento di quella riga in poi la sintassi di evidenziazione viene persa in tutte le voci
3. Anche i tag LoRA `<lora:...>` e i pesi `(tag:1.2)` non ricevono più colore

### Esempio di dati colpiti

```
lumine \(genshin impact\)
yuko \(girls und panzer\), girls und panzer,
(artist:example_artist \(art style\):1.2)
```

- Riga 1: `\(` genera un ERROR, e tutto ciò che segue `genshin impact\)` diventa token non valido
- Riga 2 e successive: il `matchParen` della riga precedente continua a scorrere nell'intero testo rimanente e lo assorbe in un token enorme, quindi i colori scompaiono
- Riga 3: quando un `\(` si trova all'interno di `()`, la gestione dell'escape in `findMatchingClose` funziona correttamente (questa differenza è stata una delle cause principali della confusione)

---

## Causa radice

### Flusso di elaborazione top-level del tokenizer (prima della correzione)

```
Input: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: 'y' → nessun matcher corrisponde → chiamata a findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK, '\' → OK (non incluso in specials)
                '(' → incluso in specials → break → restituisce j=6
3. Token TEXT: "yuko \" [0, 6)     ← il '\' è incluso nel testo
4. i=6: '(' → chiamata a matchParen(text, 6)
5. matchParen → findMatchingClose(text, 6, '(', ')')
6. findMatchingClose: depth=1, scorre l'interno:
   - 'g','i','r','l','s'... → OK
   - '\)' → saltato come escape (j += 2)  ← '\)' non viene riconosciuto come parentesi di chiusura!
   - ',' ' ' 'g','i','r','l','s'... → scorre anche la riga successiva
   - anche scorrendo fino alla fine del file non trova alcuna ')' corrispondente
   → return null
7. matchParen: result === null → token ERROR { type: 'error', value: '(' }
8. i=7: anche il testo successivo viene analizzato a frammenti, ma il testo
   che dovrebbe stare in un unico token viene suddiviso, distruggendo
   l'evidenziazione di tutte le righe successive
```

**Essenza del problema**: dopo che `findTextEnd` ha consumato `\` come testo normale,
si ferma sulla `(` successiva. La `(` nuda raggiunge il controllo `text[i] === '('`
del loop principale e viene invocato `matchParen`. All'interno di `findMatchingClose`
la `\)` viene saltata come escape, quindi non viene riconosciuta come parentesi
di chiusura e la ricerca di corrispondenza prosegue fino alla fine del file.

### Asimmetria tra interno di parentesi e top-level

`findMatchingClose` contiene già una gestione dell'escape:
```javascript
if (text[j] === '\\' && j + 1 < text.length) { j += 2; continue; }
```

Questo funziona correttamente all'**interno** di espressioni tra parentesi, come
`(artist:example_artist \(art style\):1.2)` (le `()` esterne corrispondono per prime
e le `\(` `\)` interne vengono saltate).

Tuttavia, al **livello top-level**, `\(` viene gestito con `\` e `(` in passaggi
separati, quindi l'escape non viene riconosciuto. Questa è la causa radice del bug.

---

## Contenuto della correzione

### Aggiunta della gestione delle parentesi escaped a `findTextEnd()`

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
      // ... controlli esistenti ...
    }
    return j;
}
```

### Flusso dopo la correzione

```
Input: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: chiamata a findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK
                '\' + '(' → rilevata parentesi escaped → j += 2 (consuma 2 caratteri)
                'g','i','r','l','s',' ','u','n','d',' ','p','a','n','z','e','r' → OK
                '\' + ')' → rilevata parentesi escaped → j += 2
                ')' già consumata → ',' → specials → break
3. Token TEXT: "yuko \(girls und panzer\)" [0, 30)  ← tutto in un unico testo
4. i=30: ',' → token COMMA
5. L'analisi prosegue normalmente
```

### Ambito delle modifiche

- I 6 simboli `\(`, `\)`, `\[`, `\]`, `\{`, `\}` vengono trattati come testo al livello top-level
- La gestione dell'escape all'interno di espressioni tra parentesi (`findMatchingClose` / `findMatchingBrace`) resta invariata
- Nessun impatto sul comportamento dei matcher per le normali parentesi `()`, `[]`, `{}`
- Conforme alla notazione di escape già definita nella Sezione 9 delle specifiche di sintassi dei prompt

---

## Elementi di verifica

| Test | Risultato atteso | Stato |
|--------|----------|------|
| `lumine \(genshin impact\)` | Un solo token TEXT, nessun ERROR | PASS |
| Voci `\(` su più righe seguite da `(masterpiece:1.2)` | Riconosciuto correttamente come SD_WEIGHT | PASS |
| `\[brackets\]` e `\{braces\}` | Token TEXT, nessun ERROR | PASS |
| `(masterpiece:1.2)` normale | Funziona correttamente come SD_WEIGHT | PASS |
| `{emphasis}` normale | Funziona correttamente come NAI_EMPHASIS | PASS |
| `[suppress]` normale | Funziona correttamente come NAI_SUPPRESS | PASS |
| `\(` all'interno di parentesi: `(artist:a \(b\):1.2)` | Funziona correttamente come SD_WEIGHT | PASS |
| Ricostruzione del testo semplice | Corrisponde all'input | PASS |

---

## File correlati

- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js` — punto della correzione
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-main.js` — loop principale del tokenizer
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-helpers.js` — `findMatchingClose`
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-paren.js` — `matchParen`
- `docs/development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md` — Sezione 9, specifica dell'escape

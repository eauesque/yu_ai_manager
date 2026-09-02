# Bug: pérdida del resaltado de sintaxis por paréntesis escapados `\(` `\[` `\{`

**Versión**: corregido en v2.21.26
**Gravedad**: P1 — afecta a todos los archivos de wildcards
**Fecha de descubrimiento**: 2026-02-23

---

## Síntoma

Al abrir un archivo de wildcards (por ejemplo `__characters_genshin_impact__`) en WC Manager,
el resaltado de sintaxis funciona correctamente en las primeras líneas,
pero se pierde el color en todas las líneas a partir de una entrada que contiene `\(`.

Concretamente:
1. El `(` de `\(` se muestra como token ERROR en rojo
2. A partir de esa línea se pierde el resaltado en todas las entradas siguientes
3. Tampoco se colorean los tags LoRA `<lora:...>` ni los pesos `(tag:1.2)`.

### Ejemplo de datos afectados

```
lumine \(genshin impact\)
yuko \(girls und panzer\), girls und panzer,
(artist:example_artist \(art style\):1.2)
```

- Línea 1: `\(` provoca ERROR, y a partir de `genshin impact\)` se tokenizan incorrectamente
- Líneas siguientes: el `matchParen` de la línea anterior recorre todo el texto restante y lo absorbe como un token enorme, perdiendo el color
- Si como en la línea 3 hay un `\(` dentro de `()`, funciona correctamente gracias al manejo de escape de `findMatchingClose` (esta diferencia era la fuente de la confusión)

---

## Causa raíz

### Flujo de procesamiento top-level del tokenizador (antes del fix)

```
Entrada: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: 'y' → no coincide con ningún matcher → llama a findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK, '\' → OK (no está en specials)
                '(' → está en specials → break → devuelve j=6
3. Token TEXT: "yuko \" [0, 6)     ← el '\' queda en el texto
4. i=6: '(' → llama a matchParen(text, 6)
5. matchParen → findMatchingClose(text, 6, '(', ')')
6. findMatchingClose: depth=1, recorre el interior:
   - 'g','i','r','l','s'... → OK
   - '\)' → se salta como escape (j += 2)  ← ¡`\)` no se reconoce como cierre!
   - ',' ' ' 'g','i','r','l','s'... → recorre también la siguiente línea
   - Recorre hasta el final del archivo sin encontrar `)` coincidente
   → return null
7. matchParen: result === null → token ERROR { type: 'error', value: '(' }
8. i=7: el texto posterior se parsea de forma fragmentada; lo que debería haber sido
   un solo token queda partido, destruyendo el resaltado de las líneas siguientes.
```

**Esencia del problema**: `findTextEnd` consume `\` como texto normal y luego se detiene en el siguiente `(`. El `(` desnudo llega al chequeo `text[i] === '('` del bucle principal y activa `matchParen`. Dentro de `findMatchingClose` el `\)` se salta como escape, por lo que no se reconoce como cierre y la búsqueda del coincidente sigue hasta el final del archivo.

### Asimetría entre interior de paréntesis y top-level

`findMatchingClose` ya tiene manejo de escape:
```javascript
if (text[j] === '\\' && j + 1 < text.length) { j += 2; continue; }
```

Esto funciona correctamente para escapes **dentro de paréntesis** como `(artist:example_artist \(art style\):1.2)` (el `()` exterior coincide primero y los `\(` `\)` internos se saltan).

Sin embargo, en el **top-level**, `\` y `(` se procesan en pasos separados, por lo que no se reconocen como escape. Esa es la causa raíz del bug.

---

## Contenido de la corrección

### Añadir manejo de paréntesis escapados en `findTextEnd()`

**Archivo**: `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js`

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
      // ... checks existentes ...
    }
    return j;
}
```

### Flujo tras la corrección

```
Entrada: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: llama a findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK
                '\' + '(' → paréntesis escapado detectado → j += 2 (consume 2 caracteres)
                'g','i','r','l','s',' ','u','n','d',' ','p','a','n','z','e','r' → OK
                '\' + ')' → paréntesis escapado detectado → j += 2
                ')' ya consumido → ',' → specials → break
3. Token TEXT: "yuko \(girls und panzer\)" [0, 30)  ← un único texto
4. i=30: ',' → token COMMA
5. A partir de aquí el parseo continúa normalmente
```

### Alcance del cambio

- Los 6 pares `\(`, `\)`, `\[`, `\]`, `\{`, `\}` se tratan como texto en el top-level
- El manejo de escape dentro de expresiones de paréntesis (`findMatchingClose` / `findMatchingBrace`) no cambia
- No afecta al comportamiento de los matchers de paréntesis normales `()`, `[]`, `{}`
- Se alinea con la notación de escape ya definida en la Sección 9 de la especificación de sintaxis de prompt

---

## Elementos de verificación

| Test | Resultado esperado | Estado |
|--------|----------|------|
| `lumine \(genshin impact\)` | 1 token TEXT, sin ERROR | PASS |
| Tras varias líneas con `\(`, `(masterpiece:1.2)` | Reconocido correctamente como SD_WEIGHT | PASS |
| `\[brackets\]` y `\{braces\}` | Tokens TEXT, sin ERROR | PASS |
| `(masterpiece:1.2)` normal | Funciona correctamente como SD_WEIGHT | PASS |
| `{emphasis}` normal | Funciona correctamente como NAI_EMPHASIS | PASS |
| `[suppress]` normal | Funciona correctamente como NAI_SUPPRESS | PASS |
| `\(` dentro de paréntesis: `(artist:a \(b\):1.2)` | Funciona correctamente como SD_WEIGHT | PASS |
| Reconstrucción del texto plano | Coincide con la entrada | PASS |

---

## Archivos relacionados

- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js` — punto corregido
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-main.js` — bucle principal del tokenizador
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-helpers.js` — `findMatchingClose`
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-paren.js` — `matchParen`
- `docs/development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md` — Sección 9 especificación de escape

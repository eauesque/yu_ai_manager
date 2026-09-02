# Bug de perda de syntax color por parênteses escapados `\(` `\[` `\{`

**Versão**: corrigido na v2.21.26
**Severidade**: P1 — afeta wildcards em geral
**Data da descoberta**: 2026-02-23

---

## Sintoma

No WC Manager, ao abrir um arquivo de wildcard (ex.: `__characters_genshin_impact__`),
apenas as primeiras linhas do arquivo exibem o syntax color corretamente,
e a cor some em todas as linhas a partir da entrada que contém `\(`.

Concretamente:
1. O `(` do `\(` é exibido como token ERROR em vermelho
2. A partir dessa linha, o syntax highlighting some em todas as entradas seguintes
3. Tags LoRA `<lora:...>` e pesos `(tag:1.2)` também deixam de ter cor

### Exemplo de dados afetados

```
lumine \(genshin impact\)
yuko \(girls und panzer\), girls und panzer,
(artist:example_artist \(art style\):1.2)
```

- Linha 1: ocorre ERROR em `\(`, e `genshin impact\)` em diante fica com tokens inválidos
- Da linha 2 em diante: o `matchParen` da linha anterior "come" toda a restante do texto, virando um token gigante — a cor some
- Quando o `\(` está dentro de `()` como na linha 3, o tratamento de escape em `findMatchingClose` funciona normalmente (essa diferença gerou confusão)

---

## Causa raiz

### Fluxo de processamento no topo do tokenizador (antes da correção)

```
Entrada: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: 'y' → não bate com nenhum matcher → chama findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK, '\' → OK (não está em specials)
                '(' → está em specials → break → retorna j=6
3. Token TEXT: "yuko \" [0, 6)     ← '\' entra no texto
4. i=6: '(' → chama matchParen(text, 6)
5. matchParen → findMatchingClose(text, 6, '(', ')')
6. findMatchingClose: depth=1, percorre internamente:
   - 'g','i','r','l','s'... → OK
   - '\)' → pulado como escape (j += 2)  ← '\)' NÃO é reconhecido como fechamento!
   - ',' ' ' 'g','i','r','l','s'... → percorre também a próxima linha
   - até o fim do arquivo, não acha ')' correspondente
   → return null
7. matchParen: result === null → token ERROR { type: 'error', value: '(' }
8. i=7: o texto seguinte é parseado em fragmentos, mas o que deveria ser
   um único token é quebrado, destruindo o highlighting das linhas seguintes
```

**Essência do problema**: depois que `findTextEnd` consome `\` como texto comum,
ele para no próximo `(`. Esse `(` solto chega ao check `text[i] === '('` do loop principal
e aciona `matchParen`. Dentro de `findMatchingClose`, como `\)` é pulado por ser escape,
ele não é reconhecido como fechamento, e a busca por correspondência continua até o fim do arquivo.

### Assimetria entre interior de parênteses e nível de topo

O `findMatchingClose` já tem tratamento de escape:
```javascript
if (text[j] === '\\' && j + 1 < text.length) { j += 2; continue; }
```

Isso funciona bem para escapes **dentro de parênteses**, como em
`(artist:example_artist \(art style\):1.2)` (o `()` externo casa primeiro e o `\(` `\)` interno é pulado).

Mas no **nível de topo**, `\` e `(` são processados em passos separados,
e não são reconhecidos como um escape. Esta é a causa raiz do bug.

---

## Conteúdo da correção

### Adicionar tratamento de parênteses escapados em `findTextEnd()`

**Arquivo**: `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js`

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

### Fluxo após a correção

```
Entrada: "yuko \(girls und panzer\), girls und panzer,"

1. i=0: chama findTextEnd(text, 0)
2. findTextEnd: 'y','u','k','o',' ' → OK
                '\' + '(' → detectado escape de parêntese → j += 2 (consome 2 chars)
                'g','i','r','l','s',' ','u','n','d',' ','p','a','n','z','e','r' → OK
                '\' + ')' → detectado escape de parêntese → j += 2
                ')' já consumido → ',' → specials → break
3. Token TEXT: "yuko \(girls und panzer\)" [0, 30)  ← tudo é um único texto
4. i=30: ',' → token COMMA
5. Dali em diante, o parse continua normalmente
```

### Abrangência da alteração

- No nível de topo, os 6 tipos `\(`, `\)`, `\[`, `\]`, `\{`, `\}` passam a ser tratados como texto
- O tratamento de escape dentro de parênteses (`findMatchingClose` / `findMatchingBrace`) permanece inalterado
- Não afeta a operação dos matchers para parênteses normais `()`, `[]`, `{}`
- Está em conformidade com a notação de escape definida na Seção 9 da especificação de sintaxe de prompt

---

## Itens de verificação

| Teste | Resultado esperado | Estado |
|--------|----------|------|
| `lumine \(genshin impact\)` | 1 token TEXT, sem ERROR | PASS |
| Após várias linhas com `\(`, um `(masterpiece:1.2)` | Reconhecido normalmente como SD_WEIGHT | PASS |
| `\[brackets\]` e `\{braces\}` | Token TEXT, sem ERROR | PASS |
| `(masterpiece:1.2)` comum | Funciona normalmente como SD_WEIGHT | PASS |
| `{emphasis}` comum | Funciona normalmente como NAI_EMPHASIS | PASS |
| `[suppress]` comum | Funciona normalmente como NAI_SUPPRESS | PASS |
| `\(` dentro de parênteses: `(artist:a \(b\):1.2)` | Funciona normalmente como SD_WEIGHT | PASS |
| Reconstrução do texto em plano | Idêntica à entrada | PASS |

---

## Arquivos relacionados

- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js` — local da correção
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-main.js` — loop principal do tokenizador
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-helpers.js` — `findMatchingClose`
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-paren.js` — `matchParen`
- `docs/development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md` — Seção 9 de especificação de escape

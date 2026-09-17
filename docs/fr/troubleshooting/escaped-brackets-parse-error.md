# Bug de Disparition de Coloration Syntaxique Due aux Parenthèses Échappées `\(` `\[` `\{`

**Version** : corrigé en v2.21.26
**Sévérité** : P1 — affecte tous les fichiers wildcard
**Date de découverte** : 2026-02-23

---

## Symptôme

Quand on ouvre un fichier wildcard dans WC Manager (ex : `__characters_genshin_impact__`), seules les premières lignes ont la coloration syntaxique correcte, et toutes les lignes après une entrée contenant `\(` perdent leur couleur.

Concrètement :
1. Le `(` de `\(` s'affiche comme un token ERROR en rouge
2. Toutes les entrées après cette ligne perdent la coloration syntaxique
3. Les tags LoRA `<lora:...>` et les poids `(tag:1.2)` perdent aussi leur couleur

### Exemple de Données Affectées

```
lumine \(genshin impact\)
yuko \(girls und panzer\), girls und panzer,
(artist:example_artist \(art style\):1.2)
```

- Ligne 1 : ERROR sur `\(`, `genshin impact\)` et au-delà deviennent des tokens invalides
- Ligne 2 et suivantes : `matchParen` de la ligne précédente scanne tout le texte restant et l'absorbe dans un token gigantesque, perdant la couleur
- Ligne 3 où `\(` est à l'intérieur de `()` fonctionne correctement via le traitement d'échappement de `findMatchingClose` (cette différence était la source de confusion)

---

## Cause Racine

### Flux de Traitement Top-Level du Tokenizer (avant correction)

```
Entrée : "yuko \(girls und panzer\), girls und panzer,"

1. i=0 : 'y' → aucun matcher ne correspond → appel findTextEnd(text, 0)
2. findTextEnd : 'y','u','k','o',' ' → OK, '\' → OK (non inclus dans specials)
                '(' → inclus dans specials → break → retourne j=6
3. Token TEXT : "yuko \" [0, 6)     ← '\' inclus dans le texte
4. i=6 : '(' → appel matchParen(text, 6)
5. matchParen → findMatchingClose(text, 6, '(', ')')
6. findMatchingClose : depth=1, scan intérieur :
   - 'g','i','r','l','s'... → OK
   - '\)' → saut comme échappement (j += 2)  ← '\)' non reconnu comme fermeture !
   - ',' ' ' 'g','i','r','l','s'... → scan aussi la ligne suivante
   - Scan jusqu'à fin de fichier sans trouver ')' correspondant
   → return null
7. matchParen : result === null → token ERROR { type: 'error', value: '(' }
8. i=7 : le texte suivant est parsé fragmentairement, mais ce qui devrait être
   un seul token est morcelé, détruisant la coloration de toutes les lignes suivantes
```

**Essence du problème** : après que `findTextEnd` consomme `\` comme texte normal, il s'arrête sur le `(` suivant. Le `(` nu atteint la vérification `text[i] === '('` de la boucle principale, et `matchParen` démarre. Comme `findMatchingClose` saute `\)` comme échappement, `\)` n'est pas reconnu comme fermeture, et la recherche de correspondance continue jusqu'à la fin du fichier.

### Asymétrie entre l'Intérieur des Parenthèses et le Top-Level

`findMatchingClose` a déjà un traitement d'échappement :
```javascript
if (text[j] === '\\' && j + 1 < text.length) { j += 2; continue; }
```

Cela fonctionne correctement pour les échappements **à l'intérieur de parenthèses** comme `(artist:example_artist \(art style\):1.2)` (la `()` extérieure matche en premier, et les `\(` `\)` internes sont sautés).

Mais au **top-level**, `\(` n'est pas reconnu comme échappement car `\` et `(` sont traités en étapes séparées. C'est la cause racine du bug.

---

## Contenu de la Correction

### Ajout du Traitement des Parenthèses Échappées à `findTextEnd()`

**Fichier** : `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js`

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
      // ... checks existants ...
    }
    return j;
}
```

### Flux Après Correction

```
Entrée : "yuko \(girls und panzer\), girls und panzer,"

1. i=0 : appel findTextEnd(text, 0)
2. findTextEnd : 'y','u','k','o',' ' → OK
                '\' + '(' → détection de parenthèse échappée → j += 2 (consomme 2 caractères)
                'g','i','r','l','s',' ','u','n','d',' ','p','a','n','z','e','r' → OK
                '\' + ')' → détection de parenthèse échappée → j += 2
                ')' déjà consommé → ',' → specials → break
3. Token TEXT : "yuko \(girls und panzer\)" [0, 30)  ← tout en un seul texte
4. i=30 : ',' → token COMMA
5. Parsing continue normalement
```

### Portée des Changements

- Les 6 types `\(`, `\)`, `\[`, `\]`, `\{`, `\}` sont traités comme texte au top-level
- Aucun changement dans le traitement d'échappement à l'intérieur des expressions de parenthèses (`findMatchingClose` / `findMatchingBrace`)
- Aucun impact sur le comportement des matchers pour les parenthèses normales `()`, `[]`, `{}`
- Conforme à la notation d'échappement définie en Section 9 de la spec syntaxe de prompt

---

## Points de Validation

| Test | Résultat attendu | État |
|--------|----------|------|
| `lumine \(genshin impact\)` | 1 token TEXT, pas d'ERROR | PASS |
| `(masterpiece:1.2)` après plusieurs lignes d'entrées `\(` | Reconnu correctement comme SD_WEIGHT | PASS |
| `\[brackets\]` et `\{braces\}` | Token TEXT, pas d'ERROR | PASS |
| `(masterpiece:1.2)` normal | Fonctionnement SD_WEIGHT normal | PASS |
| `{emphasis}` normal | Fonctionnement NAI_EMPHASIS normal | PASS |
| `[suppress]` normal | Fonctionnement NAI_SUPPRESS normal | PASS |
| `\(` dans parenthèses : `(artist:a \(b\):1.2)` | Fonctionnement SD_WEIGHT normal | PASS |
| Reconstruction du texte brut | Correspond à l'entrée | PASS |

---

## Fichiers Associés

- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-general.js` — Emplacement de la correction
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-main.js` — Boucle principale du tokenizer
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-helpers.js` — `findMatchingClose`
- `extensions/builtin_prompt_syntax/prompt-syntax-engine-core-lex-matchers-paren.js` — `matchParen`
- `docs/development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md` — Spécification d'échappement Section 9

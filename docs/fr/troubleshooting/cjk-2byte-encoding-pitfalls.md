# Pièges et Contre-mesures d'Encodage des Caractères CJK / 2 Octets

Ce document résume les bugs spécifiques à l'espace 2 octets centré sur le japonais (CP932/Shift-JIS), et les solutions adoptées dans ce projet. Destiné à servir de référence aux développeurs et agents IA confrontés à des problèmes similaires.

---

## 1. Crash cp932 de la Console Windows

### Symptôme

`cmd.exe` / PowerShell / Git Bash Windows ont par défaut l'encodage de sortie **cp932 (Shift-JIS)**. L'affichage via `print()` d'un caractère Unicode inexistant en cp932 crashe immédiatement avec `UnicodeEncodeError`.

```
UnicodeEncodeError: 'charmap' codec can't encode character '—' in position 12
```

### Exemples de caractères rencontrés

| Caractère | Nom | Où utilisé |
|------|------|------------|
| `—` (U+2014) | em dash | Séparateur de logs |
| `–` (U+2013) | en dash | Affichage de progression |
| `✓ ✗ ✅ ❌ ⚠️` | Marques de validation, emojis | Affichage succès/échec |
| `🧹 📦 📁 🔍 🔧` | Emojis | Affichage du contenu de traitement |
| `█ ░` | Caractères bloc | Barre de progression |

### Contre-mesure

- **N'utilisez que des caractères ASCII-safe dans `print()`** : `[OK]`, `[NG]`, `[!]`, `--`, `#`, `-`, etc.
- Même principe avec le logger (`logging`). Si l'encodage du handler est cp932, le même problème survient
- Définir `PYTHONIOENCODING=utf-8` contourne le problème, mais dépend de l'environnement utilisateur : il est plus sûr de rester défensivement en ASCII

### Portée de l'Impact

Dans ce projet, **19 fichiers** ont été corrigés en bloc (v2.28.0). Quand on fait générer du code par IA (Claude/GPT), la probabilité d'utiliser emojis et em dashes est élevée, ce qui en fait **l'un des points les plus critiques à vérifier lors de la revue de code généré par IA**.

---

## 2. Mojibake de Noms de Fichiers ZIP (CP437 mojibake)

### Symptôme

Les ZIP créés sur les anciens Windows (95/98/XP) stockent les noms en **Shift-JIS (CP932)**, mais la spécification ZIP n'a pas d'information d'encodage. Le `zipfile` Python décode en **CP437** si le bit UTF-8 (bit 11) n'est pas levé, donc les noms japonais deviennent du mojibake comme `âwâCâèâb`.

### Contre-mesure : chaîne de fallback en 10 étapes

Liste de priorité d'encodage CJK définie dans `core/infra_core/encoding.py` :

```
UTF-8 (zipfile essaye d'abord) → CP932 → EUC-JP → ISO-2022-JP
→ EUC-KR → CP949 → GB2312 → GBK → Big5 → CP950
```

- **Ne pas utiliser** `chardet` / `cchardet` : trop de fausses détections sur les noms courts (10-30 octets)
- La méthode d'ordre de priorité fixe est plus reproductible et plus facile à déboguer

### Paramètre `metadata_encoding` de Python 3.11+

```python
# En Python 3.11+, spécification directe via metadata_encoding
zf = zipfile.ZipFile(path, metadata_encoding='cp932')
```

Mais ne fonctionne pas pour les ZIP avec encodage autre que CP932, donc en cas d'échec, réouvrir sans `metadata_encoding` et tenter restauration avec `repair_cp437_name()`.

### Cas du 7z

7-Zip a son propre traitement des noms. Via la CLI 7z, le mojibake CP437 peut aussi se produire ; restauration similaire avec `repair_cp437_name()`.

---

## 3. Le Scan se Bloque sur ZIP/7z avec Caractères 2 Octets

### Symptôme

`zipfile.ZipFile()` entre en I/O bloquant et se bloque lors de la lecture du répertoire central d'un vieux ZIP encodé Shift-JIS, pour certaines séquences d'octets. Survient particulièrement avec les archives à nombreux fichiers.

### Contre-mesure

1. **Protection par timeout** : introduction de l'helper thread démon `run_with_timeout()`
   - Listing des fichiers : 30 secondes
   - I/O scan : 60 secondes
2. **Table scan_errors** (migration v24) : enregistrement permanent en DB des erreurs de timeout/encodage
   - Classification des types d'erreurs : `encoding` / `timeout` / `scan` / `archive_scan` / `archive_timeout` / `filesystem`

---

## 4. Problème de Guillemets dans tokenchars FTS5 SQLite

### Symptôme

Lors de l'utilisation de l'option `tokenchars` dans la directive `tokenize` de SQLite FTS5, certaines combinaisons de guillemets produisent une erreur de parse.

```sql
-- NG : simple quote extérieur + double quote intérieur → parse error
tokenize='unicode61 tokenchars "_:."'

-- OK : double quote extérieur + simple quote intérieur
tokenize="unicode61 tokenchars '_:.'"
```

### Cause

Le parseur du tokenizer FTS5 SQLite ne sait pas analyser correctement les double quotes dans un simple quote extérieur. Possibilité de différence de comportement selon la version SQLite (confirmé en 3.45.1).

### Contre-mesure

Côté code Python, distinguer les types de triple-quote :

```python
# OK : utiliser les deux " et ' SQL dans ''' Python
con.execute('''
    CREATE VIRTUAL TABLE fts USING fts5(
        col1,
        tokenize="unicode61 tokenchars '_:.'"
    )
''')
```

### Origine de la Découverte

Survenu lors de la reconstruction de la table FTS5 en migration 29 de ce projet. Le code généré par IA utilisait la syntaxe à simple quote extérieur, causant un crash au démarrage serveur en environnement SQLite 3.45.1 (corrigé en v2.70.1).

---

## 5. Encodage UTF-16 d'EXIF WebP

### Symptôme

Certains outils de génération d'image (notamment la famille NAI) encodent les métadonnées EXIF WebP en **UTF-16 (avec BOM)**. Le décodage UTF-8 classique produit du mojibake.

### Contre-mesure

- Détecter le BOM (Byte Order Mark) pour identifier UTF-16 BE/LE
- Sans BOM, estimer BE/LE par heuristique
- En fallback, essayer UTF-8 → latin-1 dans l'ordre

---

## 6. Encodage de Chunk tEXt PNG

### Symptôme

La spec PNG définit les chunks tEXt en **Latin-1 (ISO-8859-1)**, mais de nombreux outils de génération d'image IA stockent directement des chaînes UTF-8. Le décodage `latin-1` rend le japonais illisible.

### Contre-mesure

Décoder prioritairement en UTF-8, fallback sur latin-1 en cas d'échec :

```python
try:
    text = raw_bytes.decode('utf-8')
except UnicodeDecodeError:
    text = raw_bytes.decode('latin-1')
```

---

## 7. Backslashes dans les Chemins Windows de config.json

### Symptôme

Les chemins Windows contenant des backslashes (`\`), quand on écrit des chemins manuellement dans un JSON, créent des séquences d'échappement invalides.

```json
{"scan_roots": ["C:\Users\test"]}  // \U et \t deviennent des séquences d'échappement
```

### Contre-mesure

- Réparation automatique au démarrage serveur via `_repair_json_backslashes()`
- En interne, les chemins sont normalisés avant stockage

---

## 8. pathlib et Chemins UNC WSL

### Symptôme

Sur WSL (Windows Subsystem for Linux), `pathlib.Path.exists()` peut retourner un résultat erroné pour les chemins UNC (`\\server\share\...`).

### Contre-mesure

- Utiliser `os.path.exists()` pour vérifier l'existence de chemins UNC
- `pathlib` est pratique mais peu fiable sur les chemins réseau

---

## 9. BOM UTF-8 d'Export CSV

### Symptôme

Un CSV UTF-8 ouvert dans Excel sans BOM donne du mojibake. Excel interprète l'UTF-8 sans BOM comme ANSI (CP932 en environnement japonais).

### Contre-mesure

```python
buf.write("﻿")  # UTF-8 BOM for Excel compatibility
```

Ajouter un BOM (`﻿`) en tête du CSV. Excel reconnaîtra correctement comme UTF-8.

---

## 10. `ensure_ascii=False` pour JSON

### Symptôme

`json.dumps()` Python échappe par défaut les caractères non-ASCII en `\uXXXX`. Dans les réponses d'outils MCP, les noms de tags japonais ou chemins de fichiers échappés comme `タグ` deviennent difficiles à comprendre pour l'agent IA.

### Contre-mesure

```python
json.dumps(data, ensure_ascii=False, indent=2)
```

Dans ce projet, utilisé uniformément dans tous les modules d'outils MCP (10 fichiers).

---

## 11. Décodage de Sortie du Dialogue de Sélection de Dossier

### Symptôme

Lors de l'appel d'un dialogue de sélection de dossier sur PowerShell Windows, la sortie `subprocess` est encodée en CP932. Le décodage UTF-8 par défaut produit `UnicodeDecodeError`.

### Contre-mesure

```python
result = subprocess.run(..., capture_output=True)
path = result.stdout.decode('cp932', errors='replace').strip()
```

`errors='replace'` permet un traitement sûr même en cas d'échec de décodage.

---

## Notes Importantes pour les Agents IA

La plupart des problèmes ci-dessus sont des **patterns facilement oubliés lors de la génération de code par IA** :

1. **Ne pas utiliser d'emojis/caractères décoratifs dans `print()`** — l'IA a tendance à les utiliser pour l'esthétique
2. **Ne pas supposer l'encodage des noms de fichiers** — écrire en supposant UTF-8 casse en environnement CP932
3. **Les guillemets SQLite nécessitent un test réel** — peut ne pas fonctionner même conforme à la doc
4. **`json.dumps()` avec `ensure_ascii=False`** — indispensable pour les données japonaises
5. **Décoder la sortie subprocess avec l'encodage d'environnement** — Windows utilise souvent CP932
6. **Mettre un BOM sur les CSV** — pour compatibilité Excel

---

## Référence : Fichiers Associés du Projet

| Fichier | Contenu |
|---------|------|
| `core/infra_core/encoding.py` | Chaîne de fallback CJK, réparation mojibake CP437 |
| `core/schema_core/schema_migrate_steps_29.py` | Syntaxe correcte des guillemets tokenchars FTS5 |
| `core/tools/fs_dialog.py` | Décodage CP932 du dialogue de sélection de dossier |
| `core/configuration/json_rw.py` | Réparation des backslashes dans config.json |
| `routes/collections.py` | Ajout de BOM dans l'export CSV |
| `CLAUDE.md` | Section « Notes sur l'environnement Windows > Sortie console » |

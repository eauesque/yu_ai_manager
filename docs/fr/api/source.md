# API de navigation du code source

API en lecture seule pour naviguer le code source du projet.
Elle est conçue pour que les outils MCP et les agents IA externes puissent afficher et rechercher en toute sécurité dans la base de code.

## Modèle de sécurité

Trois couches de défense garantissent la sécurité :

### 1. Normalisation des chemins (prévention de traversal)

- Tous les chemins sont normalisés avec `os.path.realpath()` et vérifiés contre la racine du projet via correspondance de préfixe.
- Les attaques de traversal telles que `../../etc/passwd` ou `../../../Windows/System32` sont bloquées.
- L'injection de byte nul (`\x00`) est également détectée et rejetée.

### 2. Liste blanche des extensions

Extensions de fichier autorisées pour la lecture :

| Catégorie | Extensions |
|-----------|-----------|
| Python | `.py` |
| TypeScript / JavaScript | `.ts`, `.js`, `.mjs`, `.tsx`, `.jsx` |
| Web | `.html`, `.css`, `.scss` |
| Configuration | `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini` |
| Documentation | `.md`, `.txt`, `.rst` |
| Scripts | `.sh`, `.bat`, `.cmd`, `.ps1` |
| Autre | `.sql`, `.gitignore`, `.gitattributes`, `.editorconfig` |

Les fichiers sans extension suivants sont spécialement autorisés : `Dockerfile`, `Makefile`, `Procfile`, `VERSION`, `LICENSE`, `CHANGELOG`, `TODO`

### 3. Liste de blocage des fichiers sensibles

Les fichiers correspondant aux modèles suivants sont rejetés :

| Modèle | Raison |
|--------|--------|
| `config.json`, `config_*.json` | Données d'authentification telles que PIN et clé API |
| `*.env`, `.env.*` | Variables d'environnement (secrets) |
| `secret.salt`, `*.key`, `*.pem`, `*.cert` | Clés de chiffrement et certificats |
| `credentials*`, `*token*`, `*secret*` | Données d'authentification |
| `*.db`, `*.sqlite*` | Fichiers de base de données |
| `pnpm-lock.yaml`, `package-lock.json`, etc. | Fichiers de verrouillage (volumineux) |
| Image, vidéo, police et fichiers de modèle | Fichiers binaires |

### Répertoires bloqués

`.git`, `__pycache__`, `node_modules`, `venv`, `dist`, `data`, `backups`, `screenshots`, `reports`, `src-tauri`

### Limites de lecture

| Article | Limite |
|---------|--------|
| Taille du fichier | 1 MB |
| Lignes par lecture | 2 000 |
| Profondeur de traversal d'arborescence | 6 |
| Résultats de recherche | 50 |

---

## Points d'accès

### GET /api/source/tree

Récupérer une arborescence du répertoire.

#### Paramètres

| Paramètre | Type | Par défaut | Description |
|-----------|------|-----------|-------------|
| `path` | string | `""` (racine) | Chemin relatif |
| `depth` | int | `3` | Profondeur de traversal (1-6) |

#### Réponse

```json
{
  "ok": true,
  "root": ".",
  "depth": 3,
  "entries": [
    {
      "name": "core",
      "type": "dir",
      "path": "core",
      "children": [
        {
          "name": "source_core",
          "type": "dir",
          "path": "core/source_core",
          "children": [
            {
              "name": "source_browser.py",
              "type": "file",
              "path": "core/source_core/source_browser.py",
              "size": 8234
            }
          ]
        }
      ]
    },
    {
      "name": "web_ui.py",
      "type": "file",
      "path": "web_ui.py",
      "size": 3456
    }
  ]
}
```

- Les répertoires apparaissent d'abord, suivis des fichiers (triés par nom).
- `size` est en octets (fichiers uniquement).
- `children` est omis une fois que le traversal atteint la `depth` spécifiée.

---

### GET /api/source/read

Lire les contenus de fichier avec numéros de ligne.

#### Paramètres

| Paramètre | Type | Par défaut | Description |
|-----------|------|-----------|-------------|
| `path` | string | — (obligatoire) | Chemin relatif du fichier |
| `offset` | int | `0` | Ligne de démarrage (basée sur 0) |
| `limit` | int | `2000` | Nombre maximum de lignes |

#### Réponse

```json
{
  "ok": true,
  "path": "core/source_core/source_browser.py",
  "total_lines": 250,
  "offset": 0,
  "limit": 2000,
  "content": "    1\t\"\"\"Source code browser...\n    2\t\n    3\timport os\n..."
}
```

- `content` utilise le format `{line_number}\t{line_content}`.
- Utilisez `offset` + `limit` pour paginer les fichiers longs.

#### Exemples d'erreur

```json
{
  "ok": false,
  "error": "This file is not eligible for reading"
}
```

```json
{
  "ok": false,
  "error": "Access outside the project root is prohibited"
}
```

---

### GET /api/source/search

Rechercher dans le code source par texte.

#### Paramètres

| Paramètre | Type | Par défaut | Description |
|-----------|------|-----------|-------------|
| `q` | string | — (obligatoire) | Texte de recherche (minimum 2 caractères) |
| `glob` | string | `""` (tous les fichiers) | Filtre de nom de fichier (par ex. `*.py`) |
| `limit` | int | `30` | Nombre maximum de résultats (1-50) |

#### Réponse

```json
{
  "ok": true,
  "query": "def source_tree",
  "glob": "*.py",
  "total": 2,
  "results": [
    {
      "file": "core/source_core/source_browser.py",
      "line": 120,
      "text": "def source_tree("
    },
    {
      "file": "routes/source_api.py",
      "line": 15,
      "text": "    result = source_tree(rel_path, depth_int)"
    }
  ]
}
```

- La recherche est insensible à la casse.
- `text` est tronqué à un maximum de 200 caractères.

---

## Outils MCP

| Outil | Description | Paramètres clés |
|-------|-------------|----------------|
| `source_tree` | Afficher l'arborescence des répertoires | `path`: str = '', `depth`: int = 3 |
| `source_read` | Lire les contenus du fichier | `path`: str (obligatoire), `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | Rechercher le code source par texte | `query`: str (obligatoire), `glob`: str = '', `limit`: int = 30 |

### Exemples d'utilisation avec MCP

```
# Afficher la structure du projet
source_tree(path="", depth=2)

# Lire un fichier spécifique
source_read(path="core/source_core/source_browser.py")

# Rechercher dans la base de code
source_search(query="def register_blueprints", glob="*.py")
```

### Scope & Limitation de débit

- **Scope Fence** : Disponible dans le scope `read_only` (autorisé dans tous les présets)
- **Suivi du budget** : catégorie `read` (pas de limite de débit)
- **Porte HITL** : Niveau 0 (aucune approbation requise)

---

## Fichiers d'implémentation

| Fichier | Rôle |
|---------|------|
| `core/source_core/source_browser.py` | Couche de sécurité + logique métier |
| `routes/source_api.py` | Points d'accès API Flask (Blueprint) |
| `mcp_server/source_tools.py` | Enregistrement des outils MCP |

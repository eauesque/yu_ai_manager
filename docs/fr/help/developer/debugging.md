# Manuel de débogage

Manuel complet de débogage pour YU AI Manager.
Guide pour les développeurs et agents IA pour investiguer et corriger les bugs efficacement.

---

## Démarrage du serveur

### Pour la vérification (recommandé)

```bash
source venv/Scripts/activate  # Windows Git Bash
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

Si `config_test.json` n'existe pas, créer avec le contenu suivant :

```json
{
  "scan_roots": [],
  "server": { "host": "127.0.0.1", "port": 5100, "lan": false },
  "extract_a1111": true,
  "extract_comfyui": true,
  "lowercase_tags": true,
  "compute_hash": false,
  "enable_fts": true,
  "extensions": {}
}
```

> **Note** : Lors du bind sur `0.0.0.0`, le PIN est obligatoire. Depuis v4.8.1, le flag `--debug` est ignoré lors de l'exposition LAN.

### Liste des options CLI

| Option | Type | Défaut | Description |
|-----------|-----|----------|------|
| `--db` | chemin | `data/tags.db` | Chemin du fichier SQLite DB |
| `--config` | chemin | `config.json` | Chemin du fichier de configuration |
| `--host` | str | `127.0.0.1` | Adresse de liaison |
| `--port` | int | 5000 | Port de liaison |
| `--lan` | flag | - | Lier sur `0.0.0.0` (accès LAN) |
| `--pin` | str | - | Activer l'authentification PIN |
| `--debug` | flag | - | Activer le mode debug Quart |
| `--debug-log` | `on`/`off` | - | Activer/désactiver les logs de débogage structurés |
| `--allow-restart` | flag | - | Activer `/api/server/restart` |

---

## Logs de débogage

### Activation

```bash
# Via CLI
python web_ui.py --db ./tags.db --debug-log on

# Via variable d'environnement
export TAGDB_DEBUG=1
python web_ui.py --db ./tags.db
```

### Format des logs

```
[DEBUG] 2026-03-15 12:34:56 | scan:prepare | counting_start | root=/path/to/dir, recursive=True
```

Format : `[DEBUG] timestamp | source | nom_événement | key=value, ...`

### Surveillance en temps réel

```bash
tail -f logs/debug.log
curl http://127.0.0.1:5100/api/debug/logs
curl -N "http://127.0.0.1:5100/api/debug/logs?stream=1"
```

---

## Exécution des tests

```bash
source venv/Scripts/activate

# Tous les tests
python -m pytest tests/test_basic.py -v

# Tests spécifiques
python -m pytest tests/test_basic.py::TestImports -v

# Arrêt à la première failure
python -m pytest tests/test_basic.py -x

# Tests API
python -m pytest tests/api/ -v
```

### Tests Playwright navigateur

```bash
# 1. Démarrer le serveur de vérification
python web_ui.py --db ./tags.db --config config_test.json --port 5100 &

# 2. Exécuter les tests
TARGET_URL=http://localhost:5100 python -m pytest tests/test_webui_browser.py -v
```

---

## Débogage DB

### Vérification de la version du schéma

```bash
python -c "
import sqlite3
con = sqlite3.connect('data/tags.db')
v = con.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
print(f'Schema version: {v}')
"
```

### Vérification de l'intégrité DB

```bash
python db_health.py --db ./tags.db
```

### Requêtes SQL de débogage

Disponible uniquement avec `YU_DEBUG_MODE=1` :

```bash
curl -X POST http://127.0.0.1:5100/api/debug/query \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"sql":"SELECT COUNT(*) as cnt FROM files WHERE is_deleted=0"}'
```

> **Note** : Depuis v4.8.1, seules les instructions SELECT sont autorisées.

### Requêtes d'investigation courantes

```sql
-- Nombre de fichiers (par source)
SELECT meta_source, COUNT(*) as cnt FROM files WHERE is_deleted=0 GROUP BY meta_source;

-- Classement d'utilisation des modèles
SELECT model_name, COUNT(*) as cnt FROM templates GROUP BY model_name ORDER BY cnt DESC LIMIT 20;

-- Tags orphelins
SELECT t.id, t.name FROM tags t LEFT JOIN file_tags ft ON t.id=ft.tag_id WHERE ft.tag_id IS NULL;

-- Détection des chemins dupliqués
SELECT path, COUNT(*) as cnt FROM files GROUP BY path HAVING cnt > 1;
```

### Utilisation des connexions DB

| Fonction | Usage | Contexte d'utilisation |
|------|------|---------|
| `get_readonly_db()` | Lecture seule | API GET, recherche, statistiques |
| `get_db()` | Écriture possible | API POST/PUT/DELETE |
| `get_raw_db()` | Écriture possible (sans Row factory) | Traitement en lot, scan, migrations |

> **Important** : Utiliser `get_db()` dans les API en lecture seule cause des conflits de lock pendant le scan. Toujours utiliser `get_readonly_db()`.

---

## Contournement et test de l'authentification

### Ignorer l'authentification PIN

Démarrer avec `config_test.json` (sans PIN défini) pour ignorer toute authentification.

### Test de clé API

```bash
curl -H "Authorization: Bearer sk_xxxxxxxxxxxxxx" \
  http://127.0.0.1:5000/api/stats/all
```

### Portées des clés API

| Portée | Opérations autorisées |
|---------|--------------|
| `read` | Recherche, détails fichier, miniatures, statistiques |
| `rate` | Définition/récupération/lot des notes |
| `tag.write` | Ajout/suppression de tags |
| `collection.write` | CRUD collections, favoris |
| `annotate` | Lecture/écriture annotations |
| `scan` | Démarrer/arrêter/reprendre scan |
| `admin` | Gestion clés API, modification paramètres, sauvegarde/restauration |

---

## Débogage MCP

### Démarrage du serveur MCP

```bash
source venv/Scripts/activate
python -m mcp_server
```

### Activation des outils de débogage

```bash
export YU_DEBUG_MODE=1
export YU_BASE_URL=http://127.0.0.1:5100
export YU_API_KEY=sk_...
python -m mcp_server
```

### Outils de débogage MCP (YU_DEBUG_MODE=1)

| Outil | Usage |
|--------|------|
| `debug_health_check` | Vérification de vie serveur, DB, tables |
| `debug_validate_counts` | Rapprochement statistiques API et DB réelle |
| `debug_validate_search` | Validation régression API de recherche |
| `debug_validate_collection` | Cohérence interne du comptage des collections |
| `debug_validate_annotations` | Cohérence des tables d'annotations |
| `debug_sample_files` | Analyse de champs par échantillonnage aléatoire |
| `debug_roundtrip_test` | Test aller-retour annotation/rating/tag |
| `debug_readonly_query` | Exécution de requête SELECT arbitraire |
| `debug_full_report` | Rapport intégré de tous les outils d'observation |

---

## Sécurité des Extensions

### Mécanisme de scan automatique

```
1. ManifestAuthority.review()   — Revue du manifeste
2. CodeVerifier.verify()        — Analyse statique AST (tous les fichiers .py)
3. Confirmation d'approbation utilisateur
4. Émission de Capability Token
```

### Ce que CodeVerifier détecte

| Catégorie | Cibles | Sévérité |
|---------|---------|----------|
| Modules dangereux | `subprocess`, `ctypes`, `importlib` | block |
| Accès DB direct | `import sqlite3` | block |
| Réseau | `requests`, `urllib`, `httpx`, `aiohttp`, `socket` | warn |
| Exécution dynamique | `eval()`, `exec()`, `__import__()`, `compile()` | block |

---

## Débogage Frontend

### Build TypeScript

```bash
pnpm run build        # Bundle avec esbuild
pnpm run typecheck    # Vérification de types uniquement
```

Sortie : `ui/default/static/dist/` (gitignore)

---

## Variables d'environnement

### Débogage et logs

| Variable | Valeurs | Défaut | Description |
|------|-----|----------|------|
| `TAGDB_DEBUG` | `1`/`0` | `0` | Activer les logs de débogage structurés |
| `TAGDB_DEBUG_LOG` | chemin | `logs/debug.log` | Chemin du fichier de log |
| `TAGDB_DEBUG_LOG_MAX_MB` | int | `10` | Taille de rotation du log (MB) |
| `TAGDB_DEBUG_LOG_BACKUPS` | int | `5` | Nombre de générations de backup |
| `TAGDB_DEBUG_STDOUT` | `1`/`0` | `1` | Sortie des logs vers stderr |

### Serveur

| Variable | Valeurs | Description |
|------|-----|------|
| `TAGDB_DB` | chemin | Chemin du fichier DB |
| `TAGDB_CONFIG` | chemin | Chemin de config.json |
| `TAGDB_ALLOW_RESTART` | `1`/`0` | Activer l'API de redémarrage |

### MCP

| Variable | Valeurs | Description |
|------|-----|------|
| `YU_DEBUG_MODE` | `1` | Enregistrer 9 outils de débogage supplémentaires |
| `YU_BASE_URL` | URL | BASE URL pour client MCP |
| `YU_API_KEY` | `sk_...` | Clé API pour client MCP |

---

## Erreurs courantes et solutions

### Démarrage du serveur

| Erreur | Cause | Solution |
|--------|------|------|
| `Address already in use` | Port occupé | `--port 5200` |
| `database is locked` | Conflit de lock DB | Vérifier que la DB n'est pas sur un chemin réseau |
| `--pin is required` | PIN non défini pour bind LAN | `--pin <chiffres>` |
| `ModuleNotFoundError` | venv non activé | `uv pip install -r requirements.txt` |

### Authentification

| Erreur | Cause | Solution |
|--------|------|------|
| Écran PIN en boucle | Erreur cookie | Vérifier les cookies dans DevTools → Application |
| `CSRF header missing` (403) | En-tête manquant | Ajouter `X-Requested-With: XMLHttpRequest` au fetch |
| Clé API refusée | Portée insuffisante | Attribuer la portée nécessaire |

### DB

| Erreur | Cause | Solution |
|--------|------|------|
| `no such table: schema_version` | Premier démarrage | Auto-généré, ignorer |
| Échec de migration | Bug de script | Vérifier avec `db_health.py` |
| `SQLITE_BUSY` (timeout) | Transaction longue | Vérifier l'utilisation de `get_readonly_db()` |

---

## Débogage de performance

### Blocage de la visionneuse pendant le scan

**Symptôme** : L'affichage des images s'arrête pendant le scan

**Cause** : L'API de lecture utilisait `get_db()` (connexion accessible en écriture)

**Solution** : Toujours utiliser `get_readonly_db()` dans les API de lecture seule

### Limite de débit

| Niveau | Cible | Limite |
|--------|------|------|
| **HEAVY** | Recherche similaire, analyse IA, scan | ~20 req/min (burst 5) |
| **DESTRUCTIVE** | purge, hard-delete, écriture config | ~12 req/min (burst 3) |
| **WRITE** | Autres POST/PUT/DELETE | ~120 req/min (burst 30) |
| GET | Lecture | Illimité |

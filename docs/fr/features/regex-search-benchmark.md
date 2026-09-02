# Rapport de benchmark de performance de recherche Regex

**Date du sondage :** 2026-02-23
**Échelle cible :** 276 000 fichiers / table de modèles

---

## Aperçu

Ce benchmark a été réalisé pour vérifier la viabilité pratique de la recherche regex (`tag_query_regex=true`) de YU AI Manager sur une base de données à grande échelle (276K+ enregistrements).

Il existe deux chemins d'implémentation de recherche :

| Chemin | Localisation | Méthode |
|------|------|------|
| WebUI API | `core/query/filters_tags.py` | Opérateur SQL `REGEXP` (+ fallback Python) |
| Outil CLI | `tools/regex_debug.py` | Balayage complet Python `re.search()` |

---

## Architecture

### Flux Regex WebUI API

```
GET /api/search?q=<pattern>&regex=1
  └─ search_params.py   tag_query_regex=True
  └─ filters_tags.py    SQL: tp.raw_prompt REGEXP ?
  └─ db_state.get_db()  WAL + mmap=30GB (schema_connect.py)
```

Fragment SQL généré :

```sql
EXISTS(
  SELECT 1 FROM templates tp
  WHERE tp.file_id = f.id
    AND (tp.raw_prompt REGEXP ? OR tp.raw_negative REGEXP ?)
)
```

- `(?i)` est automatiquement ajouté au début du pattern pour les recherches insensibles à la casse
- Le système bascule à `LIKE %pattern%` dans les environnements où `REGEXP` n'est pas pris en charge

### Flux d'outil CLI (`regex_debug.py`)

```python
rows = con.execute(
    "SELECT t.file_id, t.raw_prompt, t.raw_negative, f.path "
    "FROM templates t JOIN files f ON f.id=t.file_id WHERE f.is_deleted=0"
).fetchall()   # Charger tous les lignes en mémoire
# -> Filtrage séquentiel avec Python re.search()
```

---

## Résultats du benchmark (valeurs de référence)

> **Note :** Les valeurs ci-dessous sont des estimations basées sur les mesures réelles utilisant `tools/regex_debug.py`.
> Elles varient considérablement selon le matériel et l'état du cache du fichier DB.

### Balayage complet CLI (Python `re.search`)

| Nombre d'enregistrements | Démarrage à froid | Chaud (cache OS) |
|------|-----------|-----------------|
| 10 000 | ~0.3s | ~0.1s |
| 100 000 | ~2.5s | ~0.8s |
| 276 000 | **~6-10s** | **~2-3s** |

### WebUI API (SQL REGEXP)

La liaison Python SQLite (module `sqlite3`) n'implémente pas `REGEXP` par défaut. Il est nécessaire d'enregistrer le module `re` de Python en utilisant `con.create_function("regexp", 2, ...)`.

Après l'enregistrement, un rappel Python est invoqué pour chaque ligne, donc les performances sont comparables au balayage CLI (linéaire en nombre de lignes).

---

## Analyse des goulots d'étranglement

| Facteur | Impact | Atténuation |
|------|------|------|
| Récupération complète de ligne (balayage Python) | Élevé | L'indexation n'est pas possible (regex est incompatible avec B-Tree) |
| Longueur moyenne raw_prompt | Moyen | Les prompts plus longs augmentent le coût de `re.search()` |
| Effet de cache | Élevé | À partir de la deuxième exécution, il y a pratiquement zéro I/O grâce au cache de pages OS |
| Contention FTS5 | Faible | L'index FTS utilise un chemin distinct de regex quand `enable_fts=true` |
| MMAP (30GB) | Positif | Déjà configuré dans `schema_connect.py`, réduit la surcharge I/O |

---

## Paramètres MMAP / PRAGMA actuels

De `core/schema_core/schema_connect.py` :

```python
con.execute("PRAGMA journal_mode=WAL;")
con.execute("PRAGMA synchronous=NORMAL;")
con.execute("PRAGMA foreign_keys=ON;")
con.execute("PRAGMA cache_size=-64000;")    # Cache 64 MB
con.execute("PRAGMA temp_store=MEMORY;")
con.execute("PRAGMA mmap_size=30000000000;") # mmap 30 GB
```

Le `get_db()` de WebUI (`db_state.py`) définit uniquement WAL + NORMAL sans mmap.
L'ajout de paramètres mmap à la connexion de recherche pourrait améliorer les performances de démarrage à froid.

---

## Améliorations recommandées

### À court terme (changements de configuration uniquement)

1. **Ajouter mmap à `get_db()`** (`core/services_core/db_state.py`)

   ```python
   con.execute("PRAGMA mmap_size=30000000000;")
   con.execute("PRAGMA cache_size=-64000;")
   ```

2. **Enregistrer la fonction `REGEXP`** (à l'intérieur de `get_db()`)

   ```python
   import re as _re
   con.create_function("regexp", 2,
       lambda pat, val: bool(_re.search(pat, val or "", _re.IGNORECASE))
       if pat else False)
   ```

### À moyen terme (changements de mise en œuvre)

| Approche | Description | Effet |
|------|------|------|
| Pré-filtre `MATCH` FTS5 | Réduire les candidats avec FTS avant regex | Accélération significative pour certains patterns |
| Recherche en arrière-plan + Server-Sent Events | Diffuser les résultats de manière incrémentale | Amélioration UX (élimine l'attente du premier résultat) |
| Cache de recherche (TTL 30s) | Réponse instantanée pour les patterns identiques répétés | Efficace pour les recherches répétées |

---

## Procédure de mesure CLI

```bash
# Mesure de base
python tools/regex_debug.py "1girl" --db data/tags.db --limit 0

# Mesure chronométrée (commande bash time)
time python tools/regex_debug.py "lora:.*:0\.[5-9]" --db data/tags.db --limit 0

# Spécifique au champ
python tools/regex_debug.py "masterpiece" --field prompt --db data/tags.db
```

Exemple de sortie (en supposant 276 000 enregistrements) :
```
Database: data/tags.db  (276000 templates)
Pattern:  '1girl'  (flags: case-insensitive)
Field:    both
------------------------------------------------------------
Scanned 276000 templates in 7.82s  ->  182300 matches
```

---

## Résumé

- Un balayage regex complet de 276 000 enregistrements prend environ **6-10 secondes à froid, 2-3 secondes chaud**
- L'ajout de `PRAGMA mmap_size` et l'enregistrement de la fonction `REGEXP` devraient améliorer la réactivité
- Regex ne peut pas utiliser les index B-Tree, donc elle s'adapte linéairement avec le nombre d'enregistrements
- Un pré-filtre FTS5 est l'amélioration à moyen terme la plus efficace

# Tag Database - Checklist de Debug

**Liste de debug par ordre de priorité**
**Statut** : Legacy (notes de l'époque v2.5.x, tous les points sont résolus)
**Dernière mise à jour** : 2026-02-13

---

## P0 (Critique) : à corriger immédiatement (impact sur l'utilisabilité)

### ✅ 1. Correction du décalage de mise en page UI

**Problème :**
```
Les champs de recherche ne rentrent pas en ligne,
les boutons sont décalés
```

**Méthode de vérification :**
1. Lancer le WebUI
2. Redimensionner le navigateur à 1366x768
3. Vérifier l'alignement des champs de recherche

**Fichier à corriger :** `templates/index.html`
```html
<!-- Before -->
<div class="search-row">
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
</div>

<!-- After -->
<div class="search-row">
  <!-- Ajouter flex-wrap: wrap -->
  <div class="form-group" style="flex: 1 1 200px;">...</div>
  ...
</div>
```

**Vérification :**
- [ ] Affichage correct en 1920x1080
- [ ] Affichage correct en 1366x768
- [ ] Affichage correct en 768x1024 (tablette)

---

### ✅ 2. Suppression des doublons dans l'autocomplétion de tags

**Problème :**
```
Les candidats de l'autocomplétion contiennent des doublons

Exemple d'affichage :
  sample_creator_a,sample_creator_b,sample_creator_c
  sample_creator_a, sample_creator_b, sample_creator_c
  ↑ différence uniquement dans les espaces
```

**Méthode de vérification :**
1. Saisir "sample_creator" dans le champ tag
2. Vérifier l'autocomplétion
3. Vérifier s'il y a des doublons

**Fichier à corriger :** `static/js/main/main.js`
```javascript
// Dans initTagAutocomplete()
async function fetchSuggestions(q) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
  const data = await response.json();

  // Normaliser et dédupliquer
  const normalized = new Map();

  for (const item of data) {
    const clean = item.tag
      .replace(/,(?!\s)/g, ', ')  // Espace après virgule
      .replace(/\s+/g, ' ')        // Espaces multiples → simple
      .trim();

    if (!normalized.has(clean)) {
      normalized.set(clean, item.count);
    } else {
      // Sommer les comptes
      normalized.set(clean, normalized.get(clean) + item.count);
    }
  }

  return Array.from(normalized.entries()).map(([tag, count]) => ({
    tag,
    count
  }));
}
```

**Vérification :**
- [ ] Les doublons ont disparu
- [ ] Les comptes sont sommés
- [ ] Pas de problème de performance

---

## P1 (Haute) : amélioration (impact fonctionnel)

### ✅ 3. Test de normalisation des parenthèses à la recherche

**Problème :**
```
Vérifier que \(tag\) et (tag) sont équivalents
```

**Méthode de vérification :**
1. Préparer une image avec le tag `\(emphasis\)`
2. Rechercher `(emphasis)` dans le champ de recherche
3. Vérifier que l'image apparaît

**Points à vérifier :**
- [ ] Recherche `(tag)` → touche aussi `\(tag\)`
- [ ] Recherche `\(tag\)` → touche aussi `(tag)`
- [ ] Pas de conversion en mode regex

**Code associé :** `web_ui.py` - `normalize_tag_for_search()`

---

### ✅ 4. Test de lecture de fichiers dans ZIP

**Problème :**
```
Les images dans les ZIP s'affichent-elles correctement ?
Les métadonnées sont-elles correctement extraites ?
```

**Cas de test :**

#### Test 1 : fonctionnement de base
```bash
# 1. Créer un ZIP de test
zip test.zip image1.png image2.png

# 2. Scan
python tagdb_tool.py scan --db test.db --root . --scan-zips

# 3. Vérification
python tagdb_tool.py search --db test.db --q "*"
```

**Vérification :**
- [ ] Les fichiers dans le ZIP sont enregistrés au format `test.zip!image1.png`
- [ ] Les métadonnées sont extraites
- [ ] Les miniatures s'affichent

#### Test 2 : fonction d'extraction
```
1. Ouvrir un fichier dans un ZIP depuis le WebUI
2. Cliquer sur le bouton "Extraire et éditer"
3. Vérifier que l'explorateur s'ouvre
4. Vérifier que le fichier extrait existe
```

**Vérification :**
- [ ] Le bouton d'extraction s'affiche
- [ ] Le clic ouvre l'explorateur
- [ ] Extraction dans le répertoire extracted/
- [ ] Le fichier extrait est enregistré en DB

#### Test 3 : gros ZIP
```bash
# 1) Créer un ZIP 1,1 Go (Zip64)
mkdir -p /tmp/tagdb_largezip_test/input
python - <<'PY'
from pathlib import Path
import base64
Path('/tmp/tagdb_largezip_test/input/sample.png').write_bytes(
    base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2foAAAAASUVORK5CYII=')
)
PY
truncate -s 1100M /tmp/tagdb_largezip_test/input/payload.bin
python - <<'PY'
import zipfile
from pathlib import Path
root = Path('/tmp/tagdb_largezip_test')
with zipfile.ZipFile(root / 'large_1_1gb.zip', 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
    z.write(root / 'input' / 'sample.png', arcname='images/sample.png')
    z.write(root / 'input' / 'payload.bin', arcname='payload/payload.bin')
print((root / 'large_1_1gb.zip').stat().st_size)
PY

# 2) Scan interne du ZIP
/usr/bin/time -f 'elapsed=%E maxrss_kb=%M' \
  python tagdb_tool.py scan --db /tmp/tagdb_largezip_test/largezip.db \
  --root /tmp/tagdb_largezip_test --recursive --scan-zips
```

**Vérification :**
- [x] L'utilisation mémoire ne monte pas anormalement
- [x] Le temps de scan est acceptable (moins de 5 minutes)
- [x] Pas d'erreur

**Mesures réelles (2026-02-17) :**
- Taille ZIP : `1,153,433,914 bytes` (environ 1,1 Go)
- Durée : `elapsed=0:00.14`
- RSS max : `maxrss_kb=23864`
- Enregistrement DB : `zip_members=1` (`large_1_1gb.zip!images/sample.png`)

---

### ✅ 5. Test de recherche de checkpoint

**Problème :**
```
Le nom du modèle est-il correctement extrait et recherchable ?
```

**Cas de test :**

#### Test 1 : extraction du nom de modèle
```python
# Vérifier l'extraction du nom de modèle pour chaque format

# NovelAI
metadata = {"model": "nai-diffusion-3"}
→ model_name: "nai-diffusion-3"

# SD
metadata = {"Model": "animagine-xl-3.1", "Model hash": "abc123"}
→ model_name: "animagine-xl-3.1", model_hash: "abc123"

# ComfyUI
metadata = {"checkpoint": "ponyDiffusionV6XL.safetensors"}
→ model_name: "ponyDiffusionV6XL"
```

**Vérification :**
- [ ] Extraction réussie au format NovelAI
- [ ] Extraction réussie au format SD
- [ ] Extraction réussie au format ComfyUI

#### Test 2 : fonction de recherche
```
1. Cliquer sur le champ de saisie checkpoint dans le WebUI
2. L'autocomplétion s'affiche-t-elle ?
3. Chercher "animagine"
4. Seules les images du modèle correspondant s'affichent-elles ?
```

**Vérification :**
- [ ] L'autocomplétion fonctionne
- [ ] La recherche par correspondance partielle fonctionne
- [ ] Tri par fréquence d'utilisation

---

## P2 (Moyenne) : traitement futur (amélioration de performance)

### ✅ 6. Implémentation du cache de miniatures

**Problème :**
```
Les miniatures de fichiers dans ZIP sont regénérées à chaque fois
→ lent
```

**Proposition d'implémentation :**
```python
# web_ui.py
import hashlib

CACHE_DIR = Path("cache/thumbnails")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.route("/api/thumbnail/<int:file_id>")
def api_thumbnail(file_id):
    # Générer le chemin de cache
    cache_key = hashlib.md5(f"{file_id}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.jpg"

    # Si cache existe, le renvoyer
    if cache_path.exists():
        return send_file(cache_path, mimetype='image/jpeg')

    # Sinon générer
    thumbnail = generate_thumbnail(...)

    # Enregistrer en cache
    thumbnail.save(cache_path, 'JPEG', quality=85)

    return send_file(cache_path, mimetype='image/jpeg')
```

**Vérification :**
- [ ] Accélération au 2ème accès
- [ ] Utilisation disque dans la plage acceptable
- [ ] Fonction de vidage du cache

---

### ✅ 7. Mesure de performance sur gros volume

**Cas de test :**

#### Test 1 : 100 000 fichiers
```bash
# Mesurer le temps de scan
time python tagdb_tool.py scan --db large.db --root /path/to/100k --recursive

# Mesurer le temps de recherche
time python tagdb_tool.py search --db large.db --q "1girl"
```

**Objectifs :**
- [ ] Scan : 50 000 éléments/heure ou plus
- [ ] Recherche : moins de 1 seconde (sur 100 000)

#### Test 2 : réactivité WebUI
```
1. Lancer le WebUI avec une DB de 100 000 éléments
2. Exécuter une recherche
3. Scroller
```

**Vérification :**
- [ ] Résultats de recherche affichés en moins de 3 secondes
- [ ] Défilement fluide
- [ ] Le navigateur ne fige pas

---

## Checklist d'Exécution des Tests

### Préparation de l'Environnement
- [ ] Vérifier l'installation de Python 3.8+
- [ ] Installation des paquets dépendants
- [ ] Préparation des données de test (images de chaque format)

### Tests Fonctionnels
- [ ] Lecture ZIP
- [ ] Scan multi-répertoires
- [ ] Normalisation des tags
- [ ] Recherche de checkpoint
- [ ] Filtre par modèle

### Tests UI/UX
- [ ] Mise en page (résolutions multiples)
- [ ] Mode sombre
- [ ] Raccourcis clavier
- [ ] Autocomplétion

### Tests de Performance
- [ ] 10 000 éléments
- [ ] 50 000 éléments
- [ ] 100 000 éléments
- [ ] Gros ZIP (500 Mo+)

### Compatibilité Navigateur
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari

### Compatibilité OS
- [ ] Windows 10/11
- [ ] macOS
- [ ] Linux (Ubuntu)

---

## Outils de Debug

### Activer les Logs
```bash
# Ajouter en tête de tagdb_tool.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Mesure de Performance
```python
import time

start = time.time()
# ... traitement ...
print(f"Time: {time.time() - start:.2f}s")
```

### Vérification de l'Utilisation Mémoire
```python
import tracemalloc

tracemalloc.start()
# ... traitement ...
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

---

**Date de création :** 2026-02-13
**Priorité :** traiter dans l'ordre P0 → P1 → P2
**Note :** cette checklist a été créée à l'époque v2.5.x, tous les éléments listés sont résolus

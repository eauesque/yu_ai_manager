# Spécification d'implémentation de l'extension Hailo Semantic Search

**Statut** : Implémenté — La version spécifique à Hailo a été remplacée par CLIP ONNX (v2.95.0)
**Cible** : Extension YU AI Manager
**Objectif** : Recherche sémantique d'images utilisant CLIP/SigLIP sur Hailo-10H (AI HAT 2)
**Implémentation** : `extensions/builtin_clip_search/core_impl/` (couche partagée) + `extensions/builtin_clip_onnx/core_impl/` (implémentation ONNX)
**Note** : Cette spécification décrit la conception initiale uniquement Hailo. L'implémentation actuelle utilise une architecture ONNX multi-moteur unifiée

---

## Aperçu

Cette Extension ajoute la possibilité de rechercher des images en utilisant du texte en langage naturel.
Exemples : "ciel bleu et océan", "fille souriante", "paysage urbain nocturne" — tous retournent des images visuellement similaires.

Elle doit fonctionner **en parallèle** avec la recherche de tags FTS5 existante et la recherche de similitude pHash.
L'Extension se désactive simplement dans les environnements où aucun appareil Hailo n'est présent.

---

## Architecture

```
[Lors du balayage d'image]
Fichier image -> Encodeur d'image CLIP (HEF Hailo) -> Vecteur 512-dim -> Stockage DB

[Lors de la recherche]
Entrée textuelle -> Encodeur de texte CLIP (CPU / HEF Hailo) -> Vecteur 512-dim
           -> Recherche de similitude cosinus -> liste file_id -> Fusion avec les résultats de recherche existants
```

**À la fois CLIP et SigLIP sont pris en charge**, commutables via configuration.
SigLIP offre une meilleure précision, mais CLIP a un historique plus solide et plus de ressources communautaires.
L'approche recommandée est de commencer par CLIP et d'ajouter SigLIP plus tard.

---

## Ventilation par phase

### Phase 1 : Vérification de la faisabilité (À faire en premier)

Après le déplacement vers l'environnement Pi5, avoir Claude Code exécute les étapes suivantes **de haut en bas**.
Arrêtez à toute étape qui échoue et traitez le problème avant de continuer.

#### Étape 1-1 : Vérifier l'exécution HailoRT

```bash
# Vérifier la reconnaissance du dispositif
hailortcli fw-control identify

# Vérifier les liaisons Python
python3 -c "import hailo_platform; print('HailoRT version:', hailo_platform.__version__)"
```

- **Appareil non visible** : Vérifier l'état du pilote avec `dmesg | grep hailo`. Vérifier la connexion PCIe d'AI HAT 2
- **Importation échoue** : Installer via `pip install hailort` ou à partir du dépôt APT Hailo (`python3-hailort`)

#### Étape 1-2 : Télécharger les fichiers HEF CLIP

```bash
mkdir -p ~/hailo_models && cd ~/hailo_models

# Encodeur d'image
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef

# Encodeur de texte
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_text_encoder.hef
```

- **403 / Accès refusé** : L'enregistrement sur Hailo Developer Zone (https://hailo.ai/developer-zone/) est requis.
  Après l'enregistrement, essayez de télécharger via Model Zoo CLI (`hailo_model_zoo`)
- **Vérification de la taille** : Chaque fichier doit faire des dizaines à ~100 MB. Un fichier anormalement petit indique un échec de téléchargement

#### Étape 1-3 : Installer les dépendances Python

```bash
# Requis pour le prétraitement d'image (utilisé dans Phase 1)
pip install opencv-python-headless numpy

# Vérifier
python3 -c "import cv2; import numpy; print('cv2:', cv2.__version__, 'numpy:', numpy.__version__)"
```

#### Étape 1-4 : Test d'inférence minimal

```python
from hailo_platform import HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams
import numpy as np

hef_path = "/home/<user>/hailo_models/clip_vit_b_16_image_encoder.hef"
hef = HEF(hef_path)

# Vérifier les informations de couche d'entrée/sortie HEF (les noms de couches varient selon le modèle)
print("Input layers:", [l.name for l in hef.get_input_vstream_infos()])
print("Output layers:", [l.name for l in hef.get_output_vstream_infos()])

with VDevice() as target:
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = target.configure(hef, configure_params)
    network_group = network_groups[0]

    input_info = hef.get_input_vstream_infos()[0]
    input_name = input_info.name
    input_shape = input_info.shape  # Attendu : (224, 224, 3) etc.
    print(f"Input: name={input_name}, shape={input_shape}")

    # Test d'inférence avec une image fictive
    dummy = np.random.randint(0, 255, (1, *input_shape), dtype=np.uint8)
    with InferVStreams(network_group, {}) as pipeline:
        result = pipeline.infer({input_name: dummy})
        for name, data in result.items():
            print(f"Output: name={name}, shape={data.shape}, dtype={data.dtype}")
            # Succès si un vecteur 512-dim est en sortie
```

- **Erreur VDevice (`not enough free devices`)** : hailo-ollama peut être en cours d'exécution. Arrêtez-le avec `systemctl stop hailo-ollama` et réessayez
- **Inférence réussie mais la sortie n'est pas 512-dim** : Vérifier la version HEF et la variante du modèle

#### Étape 1-5 : Critères de décision

| Résultat | Action suivante |
|------|----------------|
| Sortie de vecteur 512-dim | Procéder à la Phase 2 et au-delà |
| HEF se charge avec succès mais les dimensions de sortie diffèrent | Essayez une variante de modèle différente (clip_resnet_50 etc.) |
| Impossible de télécharger HEF | S'enregistrer sur Developer Zone -> télécharger via Model Zoo CLI |
| Impossible d'importer hailo_platform | Réinstaller HailoRT. Revenir à CPU CLIP si non résolu |
| Appareil non reconnu | Problème de connexion matérielle / pilote. Mettre en pause ce développement Extension |

Procéder à l'implémentation complète si Phase 1 réussit. Considérer CPU CLIP comme alternative sinon.

---

### Phase 2 : Extension du schéma DB

Ajouter à la migration DB existante :

```sql
-- migration 14: vecteurs de recherche sémantique
CREATE TABLE IF NOT EXISTS file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip',   -- 'clip' | 'siglip'
    vector      BLOB NOT NULL,                  -- array numpy float32 -> bytes
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model);
```

Stockage : `numpy.ndarray.tobytes()` -> BLOB
Chargement : `numpy.frombuffer(blob, dtype=numpy.float32)`

**Note** : SQLite n'a pas d'index ANN (Approximate Nearest Neighbor), donc les 200 000 enregistrements nécessitent un calcul complet de similitude cosinus. Le calcul par lot avec numpy doit maintenir cela dans les limites acceptables sur Pi5 (mesure requise). Considérer l'extension `sqlite-vec` si le nombre d'enregistrements croît considérablement.

---

### Phase 3 : Noyau d'inférence Hailo

**Structure des fichiers** :
```
extensions/hailo_semantic_search/
├── __init__.py
├── extension.py          # Point d'entrée Extension
├── core/
│   ├── hailo_clip.py     # Wrapper d'inférence Hailo CLIP
│   ├── cpu_clip.py       # Fallback CPU pour les environnements non-Hailo (optionnel)
│   └── vector_store.py   # CRUD vecteur DB
├── routes/
│   └── semantic_search.py  # Points de terminaison API
└── templates/
    └── _semantic_search_ui.html
```

**Responsabilités de `hailo_clip.py`** :
- Chargement HEF et initialisation VDevice (singleton, une fois au démarrage)
- Image -> prétraitement (redimensionnement 224x224, normalisation) -> inférence HEF -> vecteur 512-dim
- Texte -> tokenization -> inférence HEF -> vecteur 512-dim
  * Utiliser l'HEF encodeur de texte s'il est disponible pour Hailo-10H ; sinon utiliser CPU (bibliothèque transformers)

**Prétraitement** :
```python
import cv2
import numpy as np

def preprocess_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (224, 224))
    img = img.astype(np.float32) / 255.0
    mean = np.array([0.48145466, 0.4578275, 0.40821073])
    std  = np.array([0.26862954, 0.26130258, 0.27577711])
    img = (img - mean) / std
    return img[np.newaxis, ...]  # (1, 224, 224, 3)
```

---

### Phase 4 : API de construction d'index

**Point de terminaison** :
```
POST /api/extensions/hailo-semantic/index
```
- Traite les images non indexées séquentiellement dans un thread d'arrière-plan
- Envoie la progression via SSE comme événements `semantic_index.progress`
- Optionnellement raccordé à l'événement `scan.complete` existant pour l'exécution automatique

**Taille de lot** : 32 images par lot (équilibre entre mémoire et vitesse)

```
GET /api/extensions/hailo-semantic/index/status
-> { "total": 200000, "indexed": 12500, "running": true }
```

---

### Phase 5 : API de recherche sémantique

```
GET /api/extensions/hailo-semantic/search?q=blue sky&limit=50&threshold=0.25
```

**Flux de traitement** :
1. Convertir le texte `q` en vecteur
2. Charger tous les vecteurs de `file_vectors` (numpy)
3. Calculer la similitude cosinus par lot
4. Trier les résultats au-dessus de `threshold` par similitude décroissante
5. Retourner la liste `file_id` dans le format `/api/search` existant

**Calcul de similitude cosinus** :
```python
def cosine_similarity_batch(query_vec: np.ndarray, stored_vecs: np.ndarray) -> np.ndarray:
    # query_vec: (512,), stored_vecs: (N, 512)
    query_norm = query_vec / np.linalg.norm(query_vec)
    stored_norm = stored_vecs / np.linalg.norm(stored_vecs, axis=1, keepdims=True)
    return stored_norm @ query_norm  # (N,)
```

**Cible de performance** : Moins de 1 seconde pour 200 000 enregistrements (réalisable avec le calcul par lot numpy, même sur Pi5)

---

### Phase 6 : Intégration UI

Ajouter un onglet "Semantic Search" à l'interface de recherche existante.
Il peut s'agir d'une interface utilisateur autonome indépendante du constructeur de conditions existant (l'intégration est pour l'avenir).

```html
<!-- Ajouter un bouton de basculement à côté de la barre de recherche -->
<button id="semantic-search-toggle" class="btn-secondary">
  🔍 Semantic Search (Hailo)
</button>
```

- Masquer ou griser le bouton quand aucun appareil Hailo n'est détecté
- Réutiliser la grille existante pour les résultats de recherche
- Afficher une invite pour construire l'index quand aucun index n'existe

---

## Configuration (ajout config.json)

```json
{
  "hailo_semantic_search": {
    "enabled": true,
    "model": "clip",           // "clip" | "siglip"
    "device": "auto",          // "auto" | "hailo" | "cpu"
    "batch_size": 32,
    "similarity_threshold": 0.25,
    "auto_index_on_scan": false,
    "hef_dir": "~/.local/share/hailo-ollama/models"
  }
}
```

---

## Faits vérifiés (en date du 2026-02-27)

Les informations suivantes ont été confirmées par la recherche antérieure. Les utiliser comme référence lors de l'exécution de la Phase 1.

### Disponibilité HEF CLIP

Hailo Model Zoo v5.2.0 contient **à la fois les HEF encodeur d'image et de texte** pour Hailo-10H dans les variantes CLIP/SigLIP :

| Modèle | HEF encodeur d'image | HEF encodeur de texte |
|--------|-------------------|-------------------|
| clip_vit_b_16 | Disponible | Disponible |
| clip_vit_b_32 | Disponible | Disponible |
| clip_vit_l_14 | Disponible | Disponible |
| clip_resnet_50 | Disponible | Disponible |
| siglip_b_16 | Disponible | Disponible |
| siglip_l_16_256 | Disponible | Disponible |
| siglip2_b_32_256 | Disponible | Disponible |
| Variantes TinyCLIP | Disponible | Disponible |

Modèle d'URL S3 : `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef`

### Statut de l'encodeur de texte

- L'application officielle `hailo-CLIP` exécute **l'encodeur de texte sur CPU (PyTorch)**
- Les HEF d'encodeur de texte pour Hailo-10H existent dans Model Zoo, mais **aucune application publiée ne les utilise**
- Approche recommandée : **Implémenter l'encodeur de texte sur CPU (`sentence-transformers`)**. Il s'exécute une seule fois par requête de recherche, donc la vitesse n'est pas une préoccupation
- L'encodeur d'image est l'endroit où l'accélération Hailo fournit une valeur réelle (indexation par lot de 200K images)

### Coexistence avec hailo-ollama

- Le partage de dispositif via `SHARED_VDEVICE_GROUP_ID` est officiellement pris en charge
- Cependant, **le binaire hailo-ollama ne participe pas à ce partage** (il occupe exclusivement l'appareil)
- Exemple communautaire : Un gestionnaire de dispositifs personnalisé a été construit pour exécuter 6 services simultanément
- **Approche pratique** : Arrêter hailo-ollama lors de la construction d'index et partager le temps d'appareil
  - `systemctl stop hailo-ollama` -> Construire l'index -> `systemctl start hailo-ollama`

### Estimations de recherche de vecteurs pour 200 000 enregistrements

- 200K x 512 float32 = environ 400MB — s'adapte à la RAM Pi5 (8GB)
- La similitude cosinus par lot numpy devrait se terminer dans 1 seconde sur le Cortex-A76 Pi5

### Accélération FAISS pour la recherche vectorielle à grande échelle (v3.26.0)

Le support FAISS (Facebook AI Similarity Search) a été ajouté dans v3.26.0. Le système détecte automatiquement `faiss-cpu` quand installé et utilise la recherche du voisin le plus proche approximatif au lieu de la force brute NumPy.

| Échelle | NumPy (O(N)) | FAISS IndexFlatIP | FAISS IndexIVFFlat |
|------|-------------|-------------------|-------------------|
| 10K | ~10ms | ~2ms | - |
| 100K | ~100ms | ~20ms | ~5ms |
| 500K | ~500ms | ~100ms | ~10ms |
| 1.5M | ~1.5s | ~300ms | ~20ms |

- **< 50K** : IndexFlatIP (recherche exacte du produit interne) est auto-sélectionné
- **>= 50K** : IndexIVFFlat (clustering IVF) est auto-sélectionné, nprobe = nlist/10
- Revenir à NumPy quand FAISS n'est pas installé (pas d'impact)

**Installation** :
```bash
source venv/bin/activate
uv pip install faiss-cpu  # L'installation pip directe fonctionne sur x86_64
# Sur aarch64 (RPi) : conda install -c conda-forge faiss-cpu ou construire à partir de la source
```

Le journal de démarrage affiche `FAISS x.x.x detected — using accelerated vector search` quand actif.

### Notes sur l'application hailo-CLIP

- `hailo-ai/hailo-CLIP` cible **Hailo-8/8L**. Hailo-10H n'est pas pris en charge
- Il est conçu pour la classification zéro-coup en temps réel, pas pour les pipelines de recherche d'images
- Il sert de matériel de référence mais ne peut pas être utilisé directement. Un pipeline personnalisé doit être construit avec l'API HailoRT

---

## Alternative (Quand Hailo est indisponible)

`sentence-transformers` avec `clip-ViT-B-32` fournit le support CLIP uniquement CPU.
C'est plus lent mais permet à la même Extension de fonctionner dans les environnements sans Hailo.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('clip-ViT-B-32')
image_embedding = model.encode(Image.open(path))
text_embedding  = model.encode("blue sky")
```

Définir `"device": "cpu"` dans la configuration Extension active le mode CPU. Cette approche d'architecture double maximise la portabilité.

---

## Priorité de mise en œuvre

```
Phase 1 (Vérification)   -> Requise, à faire en premier
Phase 2 (DB)             -> Après succès Phase 1
Phase 3 (Noyau d'inférence) -> Après Phase 2
Phase 4 (Indexation)       -> Après Phase 3
Phase 5 (API de recherche)     -> Après Phase 4
Phase 6 (Interface utilisateur)           -> Après Phase 5, dernier
```

Basculer l'approche entière à CPU CLIP si Phase 1 échoue.

---

## Dépôts de référence

- `hailo-ai/hailo-apps` : Exemples de classification zéro-coup CLIP
- `hailo-ai/hailort` : Référence API pyHailoRT
- `hailo-ai/Hailo-Application-Code-Examples` : Exemples d'inférence Python
- `hailo-ai/hailo_model_zoo` : Source de téléchargement HEF CLIP/SigLIP

---

*Créé : 2026-02-27*
*Addendum de recherche : 2026-02-27 — Détails de procédure Phase 1, confirmation de disponibilité HEF, analyse de coexistence hailo-ollama*

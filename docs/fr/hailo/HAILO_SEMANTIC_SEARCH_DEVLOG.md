# Hailo-10H Semantic Search — Journal de Développement

**Projet** : YU AI Manager — Recherche sémantique d'image CLIP sur Hailo-10H
**Objectif** : Réaliser une recherche d'images en langage naturel basée sur CLIP avec Raspberry Pi 5 + AI HAT 2 (Hailo-10H)
**Date de début** : 2026-03-01
**Statut** : Phases 1-8 terminées, Phases 9-12 (intégration VLM caption, S2T vidéo, LLM multi-tour, API compatible OpenAI) terminées

---

## Pourquoi ce Projet est Important

Le Hailo-10H (AI HAT 2) est un accélérateur IA edge relativement récent sorti fin 2025, à connecter au slot M.2 du Raspberry Pi 5. Il dispose d'une performance d'inférence de 40 TOPS, mais **presque aucun cas d'usage pratique n'a encore été publié**.

Ce projet réalise, avec le Hailo-10H, une recherche sémantique (recherche d'images en langage naturel) sur une bibliothèque d'images de l'ordre de 200 000 éléments, devenant probablement le premier logiciel pratique.

---

## Phase 1 : Vérification de Faisabilité (2026-03-01)

### Informations sur l'Environnement

| Élément | Valeur |
|------|-----|
| Matériel | Raspberry Pi 5 (8 Go) + AI HAT 2 (Hailo-10H) |
| OS | Raspberry Pi OS Trixie (Linux 6.12.62+rpt-rpi-2712) |
| Python | 3.13.5 |
| Pilote HailoRT | 5.2.0 (hailort-pcie-driver) |
| Bibliothèque HailoRT | 5.2.0 (hailort deb) |
| HailoRT Python | 5.2.0 (**build depuis la source**) |

### Étape 1-1 : Reconnaissance du périphérique — OK

```bash
$ hailortcli fw-control identify
Firmware Version: 5.2.0 (release,app)
Device Architecture: HAILO10H
```

Le périphérique est reconnu sans problème. Connexion PCIe et chargement du pilote normaux.

### Étape 1-2 : Téléchargement du HEF — OK

Téléchargeable directement depuis le bucket S3 de Hailo Model Zoo v5.2.0 (sans authentification).

```
~/hailo_models/clip_vit_b_16_image_encoder.hef  (76 Mo)
~/hailo_models/clip_vit_b_16_text_encoder.hef   (77 Mo)
```

Modèle d'URL :
```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

### Étape 1-3 : Bindings Python — Build depuis la Source Requis

#### Problème : Conflit de versions de paquets

Dans les dépôts de Raspberry Pi OS, 2 familles de paquets existent :

| Famille de paquets | Version | Remarques |
|---------------|-----------|------|
| `hailort` + `hailort-pcie-driver` | 5.2.0 | Deb officiel Hailo. Pas de binding Python |
| `h10-hailort` + `python3-h10-hailort` | 5.1.1 | Fournie par l'équipe Raspberry Pi. Avec Python |

**Problème** : les 2 familles ne peuvent coexister à cause de la configuration `Conflicts`. Installer `h10-hailort` (5.1.1) installe aussi le pilote 5.1.1, mais hailo-ollama requiert 5.2.0.

#### Solution : Build du wheel Python hailort 5.2.0 depuis la source

**Pas de wheel sur PyPI**. La page de téléchargement Hailo Developer Zone n'a **pas non plus de wheel pour aarch64** (uniquement x86_64).

Résolu par build depuis la source depuis le dépôt GitHub :

```bash
git clone --depth 1 --branch v5.2.0 https://github.com/hailo-ai/hailort.git ~/hailort

# Dépendances de build
sudo apt install -y swig build-essential
pip install pybind11 setuptools wheel

# Build (environ 2 min)
cd ~/hailort/hailort/libhailort/bindings/python/platform
HAILORT_INCLUDE_DIR=/usr/include/hailo \
LIBHAILORT_PATH=/usr/lib/libhailort.so.5.2.0 \
PYBIND11_PYTHON_VERSION=3.13 \
python3 setup.py bdist_wheel --plat-name linux_aarch64

# Installation
pip install dist/hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

**Points d'attention** :
- `--plat-name linux_aarch64` est obligatoire. Sinon, le parsing du nom de répertoire `LIBHAILORT_PATH` produit `ValueError: not enough values to unpack` (bug ligne 163 de setup.py)
- Le deb `hailort` (bibliothèque C) doit être installé au préalable
- `h10-hailort` et `hailort` ne peuvent coexister à cause de `Conflicts`, supprimer `h10-hailort` d'abord puis installer `hailort` 5.2.0

### Étape 1-4 : Test d'inférence — Succès (changement d'API)

#### Découverte Majeure : Hailo-10H Ne Supporte Pas l'Ancienne API VStreams

Le code avec `InferVStreams` + `ConfigureParams.create_from_hef()` écrit dans la spec **ne fonctionne pas sur Hailo-10H**. `VDevice.configure()` retourne `HAILO_NOT_IMPLEMENTED (error 7)`.

C'est un **fait important de différence d'API fondamentale entre Hailo-8/8L et Hailo-10H**, pas clairement documenté officiellement.

#### API Correcte : InferModel

Sur Hailo-10H, utiliser `VDevice.create_infer_model()` :

```python
from hailo_platform import VDevice
import numpy as np

hef_path = "~/.hailo_models/clip_vit_b_16_image_encoder.hef"

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(hef_path)

    # inputs/outputs sont des propriétés (pas callable)
    inp_info = infer_model.inputs[0]   # PAS inputs()
    out_info = infer_model.outputs[0]

    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # Entrée : image uint8
    dummy = np.random.randint(0, 255, inp_info.shape, dtype=np.uint8)
    bindings.input().set_buffer(dummy)

    # Sortie : allouer explicitement le buffer uint8
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    configured.run([bindings], timeout=10000)

    vec = output_buf.flatten()  # (512,) uint8
```

#### Points de blocage et solutions

| Problème | Erreur | Solution |
|------|--------|------|
| `infer_model.inputs()` TypeError | `'list' object is not callable` | C'est une propriété, `inputs[0]` (sans parenthèses) |
| Buffer de sortie non défini | `not configured as view` | Allouer explicitement avec `bindings.output().set_buffer(buf)` |
| Buffer de sortie alloué en float32 | `buffer size 2048 != expected 512` | Allouer en **uint8** (512 octets). float32 fait 2048 octets |
| Erreur à la fermeture de VDevice | `Lost communication with server` | Problème d'ordre de cleanup de VDevice. **Pas d'impact sur le résultat d'inférence** |

### Performance d'Inférence

| Élément | Valeur |
|------|-----|
| Modèle | CLIP ViT-B/16 Image Encoder |
| Entrée | (224, 224, 3) uint8 |
| Sortie | (1, 1, 512) uint8 (quantifié) |
| Temps d'inférence | **~20 ms** |
| Throughput théorique | **~50 images/sec** |

Construction d'index de 200 000 images : environ 67 minutes pour l'inférence seule. Avec prétraitement, terminé en quelques heures.

### Jugement Phase 1

| Critère | Résultat |
|------|------|
| Sortie vecteur 512 dimensions | **OK** (quantifié uint8, déquantification requise) |
| Vitesse d'inférence | **Excellente** (20ms/image) |
| Compatibilité API | Utiliser l'API InferModel (API VStreams de la spec impossible) |
| Jugement | **Passer en Phase 2** |

### Points à Transmettre à la Phase Suivante

1. **Déquantification** : il faut convertir la sortie uint8 en float32. Les paramètres de quantification (scale/zero_point) devraient être inclus dans le HEF. `hailo_platform.pyhailort._pyhailort.dequantize_output_buffer` peut être utilisable
2. **Encodeur de texte** : le HEF existe mais non testé. Vérifier que la même API InferModel fonctionne. L'implémenter en CPU (sentence-transformers) comme la spec pourrait être plus sûr
3. **Coexistence avec hailo-ollama** : VDevice utilise le périphérique exclusivement. Il faut arrêter hailo-ollama pendant la construction d'index
4. **Cleanup VDevice** : le message d'erreur à la sortie est inoffensif, mais attention aux fuites de ressources dans les processus serveur longs

---

## Phase 2 : Extension du Schéma DB (2026-03-01)

### Contenu de l'Implémentation

Ajout de la table `file_vectors` comme Migration 25.

```sql
CREATE TABLE file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip_vit_b_16',
    vector      BLOB NOT NULL,        -- float32 numpy array tobytes() (512*4=2048 bytes)
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX idx_file_vectors_model ON file_vectors(model);
```

**Décisions de conception** :
- `vector` stocke le BLOB float32 post-déquantification. Stocker en uint8 dégrade la précision
- `file_id` est PRIMARY KEY (1 fichier 1 vecteur). Pour futur support multi-modèles, changer en UNIQUE(file_id, model)
- `ON DELETE CASCADE` supprime automatiquement à la suppression de files

**Test** : application de la migration en DB in-memory → vérification existence table/index → OK

### Fichiers

- `core/schema_core/schema_migrate_steps_25.py` (nouveau)
- `core/schema_core/schema_migrate.py` (import + ajout `if current_version < 25`)
- `core/schema_core/schema_constants.py` (`CURRENT_SCHEMA_VERSION = 25`)
- `core/hailo_clip_core/vector_store.py` (nouveau - CRUD vecteurs DB) *(actuellement déplacé dans `extensions/builtin_hailo_semantic_search/core_impl/`)*

---

## Phase 3 : Noyau d'Inférence Hailo (2026-03-01)

### Contenu de l'Implémentation

Création du package `core/hailo_clip_core/` *(actuellement `extensions/builtin_hailo_semantic_search/core_impl/`)* :

| Fichier | Responsabilité |
|---------|------|
| `hailo_inference.py` | Singleton HailoClipEncoder. Wrapper API InferModel |
| `image_preprocess.py` | Redimensionnement 224x224 + conversion BGR→RGB avec cv2 |
| `dequantize.py` | Déquantification uint8→float32 + normalisation L2 + extraction quant_params |
| `text_encoder.py` | Encodeur de texte CLIP CPU (`openai/clip-vit-base-patch16`) |

**Décisions de conception** :
- Préprocessing image passe uint8 tel quel à Hailo (normalisation dans le HEF)
- Utilisation du CLIPModel de `transformers` pour l'encodeur de texte (pas `sentence-transformers`). Raison : `openai/clip-vit-base-patch16` est le même modèle que le CLIP ViT-B/16 HEF Hailo, l'espace vectoriel correspond
- Tente d'obtenir les paramètres de déquantification depuis `infer_model.outputs[0].quant_infos[0]`, fallback sur scale=1.0, zero_point=0.0 en cas d'échec

**Paquets dépendants** : `opencv-python-headless`, `numpy` (obligatoires), `transformers`, `torch` (pour recherche textuelle)

---

## Phase 4 : Indexeur + Extension (2026-03-01)

### Contenu de l'Implémentation

| Fichier | Responsabilité |
|---------|------|
| `core/hailo_clip_core/indexer.py` *(actuellement `extensions/builtin_clip_search/core_impl/`)* | Construction d'index par lot en thread d'arrière-plan |
| `core/hailo_clip_core/event_handler.py` *(actuellement `extensions/builtin_clip_search/core_impl/`)* | Indexation automatique sur événement scan.complete |
| `extensions/builtin_hailo_semantic_search/extension.json` | Manifeste d'Extension |
| `extensions/builtin_hailo_semantic_search/hailo_semantic_search.py` | Blueprint 5 API |

**Endpoints API** :
- `GET /ext/hailo-semantic/api/status` — État du périphérique et de l'index
- `POST /ext/hailo-semantic/api/index/start` — Démarrer la construction d'index
- `GET /ext/hailo-semantic/api/index/status` — Progression
- `POST /ext/hailo-semantic/api/index/stop` — Interrompre
- `GET /ext/hailo-semantic/api/search` — Recherche sémantique
- `POST /ext/hailo-semantic/api/index/clear` — Effacer l'index

**Événements** : ajout de `semantic_index.start/progress/complete` à event_bus

---

## Phase 5 : Moteur de Recherche Sémantique (2026-03-01)

### Contenu de l'Implémentation

`core/hailo_clip_core/search.py` *(actuellement `extensions/builtin_clip_search/core_impl/search.py`)* — recherche par similarité cosinus avec cache mémoire

**Algorithme** :
1. Chargement en masse de tous les vecteurs depuis la DB → cache mémoire
2. Pré-normalisation L2 des vecteurs
3. Texte de requête → encodeur de texte CLIP → vecteur 512D
4. Calcul par lots de similarité cosinus via produit matriciel (dot product)
5. Tri des éléments ≥ threshold → retour des résultats

**Estimation mémoire** : 200K x 512 x 4 octets = ~400 Mo (acceptable sur Pi5 8 Go RAM)

**Format de réponse** :
```json
{
    "status": "ok",
    "total": 25,
    "results": [{"file_id": 123, "score": 0.82, "path": "..."}],
    "query": "blue sky",
    "indexed_count": 200000,
    "threshold": 0.2,
    "timing": {"encode_ms": 150.3, "search_ms": 12.5}
}
```

---

## Phase 6 : Intégration UI (2026-03-01)

### Page de Recherche

- Ajout d'un toggle de recherche sémantique (icône cerveau style `regex-pill`) à côté de la barre de recherche
- Affiché uniquement quand Hailo est disponible ET que l'index est construit
- Quand toggle ON : interception de la soumission du formulaire → API recherche sémantique → affichage dans la grille existante
- Remplacement du placeholder par un exemple en texte anglais

### Page Tools

- Ajout d'une section Recherche sémantique dans l'onglet Search & Analysis
- Affichage de l'état du périphérique / état de l'index
- Slider de taille de batch + checkbox d'indexation automatique
- Boutons Build Index / Stop / Clear + barre de progression (polling 2 sec)

---

## Notes Techniques

### Principales Différences Hailo-10H vs Hailo-8/8L (point de vue développeur)

| Élément | Hailo-8/8L | Hailo-10H |
|------|-----------|-----------|
| API VStreams | Supportée | **Non supportée** (NOT_IMPLEMENTED) |
| API InferModel | Supportée | Supportée |
| ConfigureParams | create_from_hef(hef, interface) | Non requis (create_infer_model le remplace) |
| Format de sortie | float32 ou uint8 choisi | uint8 fixe (déquantification requise) |
| Package Python | Wheel PyPI disponible | **Aucun** (build source requis) |
| Paquet APT | `hailort` intégré | `h10-hailort` famille séparée (5.1.1 uniquement) |

### Stockage du Wheel Construit

```
~/hailort/hailort/libhailort/bindings/python/platform/dist/
  hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

Pour déploiement vers d'autres environnements Pi5, copier et installer ce wheel (mais libhailort.so.5.2.0 et hailort-pcie-driver 5.2.0 sont requis).

---

## Journal des Corrections de Bugs Après Implémentation Phase 2-6 (2026-03-01)

### 1. Problème de compatibilité `get_text_features` de l'encodeur de texte

**Problème** : `CLIPModel.get_text_features(**inputs)` dans les nouvelles versions de transformers retourne un objet `BaseModelOutputWithPooling` au lieu de `torch.Tensor`. Par conséquent, l'appel `.squeeze()` provoque `AttributeError`, causant une erreur `Search failed` de la recherche sémantique.

**Symptôme** : `curl /ext/hailo-semantic/api/search?q=girl` → `{"message":"Search failed","status":"error"}`

**Cause** : la valeur de retour de `_model.get_text_features()` dépend de la version de transformers. Dans les nouvelles versions, l'objet de sortie complet du modèle est retourné, il faut extraire `.pooler_output` soi-même.

**Correction** : dans `text_encoder.py`, traitement explicite en 2 étapes `text_model()` → `text_projection()` :

```python
# Before (broken)
text_features = _model.get_text_features(**inputs)
vec = text_features.squeeze().numpy()

# After (fixed)
text_out = _model.text_model(**inputs)
text_features = _model.text_projection(text_out.pooler_output)
vec = text_features.squeeze().numpy()
```

**Performance** :
- Première requête (chargement du modèle inclus) : ~6 secondes
- 2e et suivantes : ~100-170ms (inférence CPU uniquement)
- Recherche vectorielle : <1ms (51 éléments, cache mémoire)

### 2. Boucle de retry infinie lors de la construction d'index

**Problème** : les fichiers en échec de décodage (non-images, fichiers corrompus, etc.) n'étaient pas tracés comme `failed_ids`, `get_unindexed_file_ids()` retournait à chaque fois les mêmes fichiers en échec, le compteur d'erreurs dépassait 3 millions.

**Correction** : ajout de `failed_ids: set` dans `indexer.py`. Enregistrement des file_id en échec, exclusion dans le batch suivant.

### 3. Échec de lecture d'image dans les archives

**Problème** : `cv2.imread('test.7z!image.png')` ne comprend pas les chemins de membres d'archive.

**Correction** : dans `image_preprocess.py`, détection des chemins d'archive avec `is_archive_member()` et bascule au pattern `read_bytes_from_zip` / `read_bytes_from_7z` + `cv2.imdecode()`.

### 4. Mise à jour de progression en temps réel SSE

**Problème** : avec polling de 2 secondes, la progression est saccadée et l'expérience mauvaise.

**Correction** : bascule vers connexion SSE `EventSource`. Mise à jour en temps réel via événement `semantic_index.progress`. Sur `visibilitychange`, déconnexion SSE quand onglet invisible, reconnexion au retour.

---

## Phase 7 : Détection d'Objets YOLO (2026-03-02)

### Vue d'ensemble

Après la recherche sémantique CLIP, implémentation de la détection d'objets YOLO sur le même Hailo-10H. Détection d'objets COCO 80 classes sur images/vidéos, résultats stockés dans la table `file_annotations`.

### Conception de l'Architecture

#### Problème de partage VDevice

Hailo-10H n'utilise qu'un seul VDevice par processus, et InferModel est aussi exclusif. CLIP et YOLO ne peuvent fonctionner en même temps.

**Solution** : création de `core/hailo_device_core/device_manager.py`.
- `acquire_device(owner, hef_path)` — si un autre owner le détient, libération automatique et switch
- Même owner + même HEF → réutilisation (évite la réinitialisation)
- Thread-safe avec `threading.Lock`
- Refactor de `hailo_inference.py` de CLIP pour déléguer au device_manager

#### Gestion des tenseurs de sortie YOLO

CLIP a 1 tenseur de sortie, mais YOLO a plusieurs tenseurs de sortie (correspondant aux têtes de chaque stride). `device_manager` collecte et retourne les paramètres de quantification de toutes les sorties.

#### Pipeline de post-traitement

Post-traitement YOLO en étapes :
1. Déquantification uint8 → float32 (avec scale/zero_point par output)
2. Décodage grid cell → coordonnées pixel (sigmoid + grid offset + stride)
3. Filtre de confidence
4. NMS par classe (pure numpy)
5. Conversion coordonnées letterbox → coordonnées normalisées (0-1) de l'image d'origine

#### Support vidéo

Extraction de frames avec ffmpeg → détection indépendante de chaque frame → agrégation par classe. Conservation de la confidence max + nombre de frames d'apparition par classe.

### Nouvelle Structure de Modules

| Module | Rôle |
|---|---|
| `core/hailo_device_core/device_manager.py` | Gestion du cycle de vie VDevice partagé |
| `core/hailo_yolo_core/hailo_yolo_inference.py` | Singleton YOLODetector |
| `core/hailo_yolo_core/yolo_postprocess.py` | NMS, box decode, dequantize |
| `core/hailo_yolo_core/yolo_labels.py` | Labels 80 classes COCO |
| `core/hailo_yolo_core/yolo_preprocess.py` | Redimensionnement letterbox 640x640 |
| `core/hailo_yolo_core/yolo_video.py` | Extraction de frames vidéo + agrégation |
| `core/hailo_yolo_core/yolo_indexer.py` | Détection batch en arrière-plan |
| `core/hailo_yolo_core/model_download.py` | Téléchargement HEF |
| `core/hailo_yolo_core/event_handler.py` | Handler scan.complete |
| `extensions/builtin_hailo_yolo_detect/` | Extension + Blueprint API + UI |

### Notes Techniques

- **Tenseurs de sortie multiples** : le HEF YOLO a plusieurs tenseurs de sortie (correspondant aux têtes de chaque stride). Parcourir `infer_model.outputs` et collecter tous les shape/quant_params
- **Buffer de sortie** : allouer un buffer uint8 individuel pour chaque tenseur de sortie, binder par nom avec `bindings.output(out.name).set_buffer(buf)`
- **Layout des tenseurs** : shape typique `(1, H, W, C)`. C contient bbox (4) + class scores (80)
- **Téléchargement HEF** : directement depuis Hailo Model Zoo v5.2.0. Sans User-Agent, bloqué par Cloudflare, définir `_USER_AGENT`
- **Stockage des détections** : dans la table `file_annotations` avec `source='hailo:<model>'`, `key='detections'`, stocké en tableau JSON. Réutilise directement l'API CRUD d'annotations existante

---

## Phase 8 : Intégration GenAI (LLM / VLM / Speech2Text) (2026-03-02)

### Objectif

Intégrer le module `hailo_platform.genai` (LLM, VLM, Speech2Text) de Hailo-10H dans le device_manager, rendant disponibles depuis le WebUI la génération de texte, la compréhension d'image et la transcription audio.

### Extension de device_manager

- **Problème** : le device_manager existant ne supporte que l'API InferModel (CLIP/YOLO). Les classes GenAI reçoivent VDevice directement et non InferModel, mode différent
- **Solution** : variable `_mode` (`"infer"` | `"genai"`) pour distinguer les modes. Ajout de `acquire_genai(owner, model_path, genai_factory)`, génération d'instances LLM/VLM/S2T via pattern factory
- **Différences de traitement de release** :
  - InferModel : `del configured` → `del infer_model` → `del vdevice`
  - GenAI : `instance.release()` → `vdevice.release()` (méthode release explicite)

### Découvertes sur l'API GenAI

- **Format de message** : structure role/content compatible OpenAI. Content est un tableau au format `{"type": "text", "text": "..."}`
- **Entrée d'image VLM** : tableau numpy 336x336 RGB uint8. Passage en liste avec `frames=[image]`. Placer un placeholder `{"type": "image"}` dans le prompt
- **Entrée S2T** : float32 little-endian (`<f4`), mono, 16kHz. Normalisation int16→float32 indispensable
- **Segments S2T** : `generate_all_segments()` retourne une liste d'objets `SegmentInfo`. Attributs `.text`, `.start`, `.end`
- **Gestion du contexte** : LLM/VLM gèrent la fenêtre de contexte via `get_context_usage_size()`, `max_context_capacity()`, `clear_context()`
- **Streaming** : `generate()` retourne un itérateur, yield par token

### URL de Téléchargement HEF des Modèles

- Pattern : `https://dev-public.hailo.ai/v{hailort_version}/blob/{ModelName}.hef`
- HailoRT 5.2.0 → `v5.2.0`
- Noms de modèle en CamelCase (ex : `Qwen2.5-1.5B-Instruct.hef`, `Whisper-Base.hef`)
- Confirmé dans le type source `gen-ai-mz` de `download_resources.py` de `hailo-apps-infra`

### Nouveaux Fichiers

| Fichier | Description |
|----------|------|
| `core/hailo_genai_core/__init__.py` | Init du package |
| `core/hailo_genai_core/genai_types.py` | Enum GenAIModelType + dataclass GenAIModelInfo |
| `core/hailo_genai_core/model_download.py` | Gestion téléchargement HEF de 7 modèles |
| `core/hailo_genai_core/llm_inference.py` | Wrapper HailoLLM (singleton, streaming) |
| `core/hailo_genai_core/vlm_inference.py` | Wrapper HailoVLM (singleton, préprocessing image) |
| `core/hailo_genai_core/s2t_inference.py` | Wrapper HailoS2T (singleton, support segments) |
| `extensions/builtin_hailo_genai/extension.json` | Manifeste d'Extension |
| `extensions/builtin_hailo_genai/hailo_genai_ext.py` | Blueprint 8 API (SSE streaming) |
| `extensions/.../templates/hailo_genai/_genai_ui.html` | UI page Tools (4 panneaux) |

### Notes Techniques

- **VDevice.create_params()** : en mode GenAI, créer les paramètres avec `VDevice.create_params()` et instancier avec `VDevice(params)`. Différent du `VDevice()` (sans arg) du mode InferModel
- **Streaming SSE** : avec `Response(generator(), mimetype='text/event-stream')` de Flask, envoi par token de `data: {"token": "..."}\n\n`. `data: {"done": true}\n\n` à la fin
- **Envoi FormData VLM** : pour envoyer fichier image + texte prompt simultanément, l'API VLM utilise `multipart/form-data` et non JSON
- **Lecture WAV S2T** : côté serveur, lecture directe depuis les bytes WAV uploadés via module `wave` + `io.BytesIO`

---

## Phase 9 : Intégration Recherche Sémantique + Caption VLM (2026-03-03)

### Objectif

Génération de captions en masse des images résultats CLIP par VLM (Qwen2-VL), stockage dans `file_annotations`.

### Implémentation

- **`core/hailo_clip_core/caption_runner.py`** *(actuellement `extensions/builtin_hailo_semantic_search/core_impl/caption_runner.py`)* (~150 lignes) : exécution batch de génération de captions VLM en thread d'arrière-plan. Suit le pattern `_state_lock` + `_stop_requested` + `_progress` de `indexer.py`. Événements SSE `vlm_caption.start/progress/complete`
- **Extension Blueprint** : ajout des 3 endpoints `/api/caption/start`, `/api/caption/status`, `/api/caption/stop` à `hailo_semantic_search.py`
- **UI** : ajout du panneau « VLM Caption Generation » à la section Semantic Search de la page Tools. Saisie de prompt, barre de progression SSE, lien automatique avec les file_ids des résultats de recherche

### Contrôle d'Exclusivité VDevice

- Acquisition du VLM par `acquire_genai("vlm", ...)`. Si l'indexeur CLIP fonctionne, libération automatique par le comportement existant du device_manager
- Après la fin de la génération de caption, le VLM continue de détenir le périphérique, donc la reprise de l'index CLIP requiert le déchargement du modèle

### Convention de Stockage des Annotations

- `source="hailo:vlm"`, `key="caption"`, `value=<texte du caption>`

---

## Phase 10 : Transcription Audio Vidéo — Pipeline S2T (2026-03-03)

### Objectif

Extraction audio des fichiers vidéo avec ffmpeg → transcription avec Whisper (S2T) → stockage dans `file_annotations`.

### Implémentation

- **`core/files_core/video_audio.py`** (~80 lignes) : `extract_audio_wav()` extrait l'audio ffmpeg (mono PCM s16le 16kHz). Calcul dynamique du timeout depuis la durée vidéo (max 120 secondes). `check_ffmpeg()` réutilisé depuis `media_video.py`
- **Extension Blueprint** : ajout de 3 endpoints à `hailo_genai_ext.py` :
  - `POST /api/s2t/transcribe-video` : transcription d'une vidéo unique (file_id, language)
  - `POST /api/s2t/batch-transcribe` : transcription batch de plusieurs vidéos (file_ids, language), thread d'arrière-plan + progression SSE (`video_s2t.*`)
  - `GET /api/s2t/transcript/<file_id>` : récupération de transcription stockée
- **UI** : ajout d'une sous-section « Video Transcription » dans le panneau S2T. Saisie file_id, sélection langue (ja/en), bouton de récupération

### Convention de Stockage des Annotations

- `source="hailo:s2t"`, `key="transcript"`, `value=<texte intégral>`
- `source="hailo:s2t"`, `key="transcript_segments"`, `value=<JSON [{text, start, end}, ...]>`

### Points d'Attention

- Le WAV temporaire est créé avec `tempfile.NamedTemporaryFile`, suppression garantie dans finally
- S2T et LLM/VLM sont mutuellement exclusifs sur le périphérique (utilisation simultanée impossible)

---

## Phase 11 : Amélioration UI Conversation Multi-tour LLM (2026-03-03)

### Objectif

Extension des prompts uniques vers la prise en charge de l'historique de conversation. Continuation/réinitialisation du contexte, UI type bulle.

### Implémentation

- **Correction API** : `api_llm_generate()` peut recevoir un tableau `messages`. Compatibilité descendante : si seulement `prompt`, conversion comme avant en messages system + user. `generate_stream()` supporte déjà le multi-tour (via `_normalise_prompt()`)
- **UI chat type bulle** : `hg-chat-container` + `hg-bubble` (user=aligné droite violet, AI=aligné gauche gris). Classes CSS : `hg-bubble-user`, `hg-bubble-ai`, `hg-bubble-label`
- **Gestion de l'historique de conversation** : côté JS, accumulation `{role, content}` dans `_chatHistory = []`. Passage `messages: [systemMsg, ..._chatHistory]` lors de l'envoi API. `hgLlmClear()` réinitialise le tableau + clear du contexte HailoRT
- **Streaming** : insertion DOM préalable de la bulle AI, ajout séquentiel des tokens SSE

### Correction de Bug : Erreur system role en Conversation Multi-tour (2026-03-03)

Découvert via requête de debug MCP + logs hailort. Dans l'appel à `generate()` à partir du 2e tour, l'erreur suivante survient :

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_OPERATION(6)
```

**Cause** : le template UI envoyait à chaque fois system role en tête avec `[systemMsg].concat(_chatHistory)`. L'API LLM HailoRT n'accepte pas le system role quand le contexte existe (à partir du 2e tour).

**Correction** :
1. Ajout de la méthode `_prepare_prompt()` à `llm_inference.py` : exclusion automatique du message system role si `get_context_usage_size() > 0`
2. Template UI (`_genai_ui.html`) : ajout de system uniquement si `_chatHistory.length <= 1` (seulement le premier message utilisateur)

**Note technique** : contrainte HailoRT : `LLM.generate()` ne traite le system role qu'au premier appel. Comportement différent de l'API OpenAI, attention lors de l'implémentation de conversation multi-tour

---

## Test Réel WD-Tagger VLM × Hailo-10H (2026-03-03)

### Environnement de Test
- Raspberry Pi 5 + Hailo AI HAT 2 (Hailo-10H)
- HailoRT FW 5.2.0, hailo_platform Python 5.2.0
- hailo-ollama v0.5.1 (version buildée)
- Qwen2-VL-2B-Instruct.hef (3,0 Go)

### Découverte Importante : hailo-ollama Ne Supporte Pas VLM

Explicite dans la documentation officielle hailo-ollama (USAGE.rst) :
> "The Hailo-Ollama API is currently limited to language models (LLMs) and cannot be used for VLMs."

Dans la table MODELS, la colonne Inference API de `Qwen2-VL-2B-Instruct` indique uniquement "C++, Python", sans "Hailo-Ollama".

Liste de modèles retournée par `/hailo/v1/list` :
```
deepseek_r1:1.5b, llama3.2:1b, qwen2.5-coder:1.5b, qwen2.5:1.5b, qwen2:1.5b
```
`qwen2-vl` n'est pas inclus.

### Résultats des Tests hailo-ollama

**Point d'attention config** : la version buildée utilise la macro `NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE`, la clé `limits` est obligatoire dans le JSON de config. Non incluse dans le template officiel, il faut ajouter :
```json
"limits": {"max_in_flight": 4, "max_queue": 10, "retry_after_sec": 1}
```

- **Génération de texte LLM (qwen2.5:1.5b)** : OpenAI + Ollama native tous deux OK, 6.5 TPS
- **Requête vision OpenAI API** : erreur 500 (`Node is NOT a STRING`)
- **API Ollama native + images** : acceptée mais LLM ne peut traiter les images
- **Fallback VlmWdTaggerEngine** : OpenAI 500 → bascule automatique vers Ollama native OK
- **response_format: json_object** : accepté mais la sortie JSON n'est pas forcée

### Résultats des Tests VLM Direct avec Hailo Python SDK

VLM nécessite `{"type": "image"}` dans le format de message :
```python
messages = [
    {"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": "Tag this image."}
    ]}
]
vlm.generate_all(messages, frames=[frame_336x336_rgb_uint8])
```

- **Chargement du modèle** : 33 secondes (cold start initial. Différence avec les 6,2 s annoncés dominée par I/O disque)
- **Vitesse d'inférence** : ~5,1 TPS (128 tokens / 20 s). La différence avec les 6,73 TPS annoncés inclut le TTFT
- **Précision de reconnaissance d'image** : compréhension correcte du contenu (description précise « deux femmes se tenant la main dans un paysage enneigé »)
- **Qualité de sortie JSON** : faible. Le modèle 2B est instable dans la génération de JSON structuré (virgules manquantes, markdown code fences intrusifs)

### Bugs Découverts

1. **Format de prompt dans `engines_hailo_vlm.py`** : passait un message texte seul à VLM → corrigé en format liste incluant `{"type": "image"}`
2. **Argument frames dans `vlm_inference.py`** : `generate_all()` du VLM requiert `frames` mais déclaré Optional → corrigé en obligatoire

### Notes Techniques

- **Contrainte d'exclusivité VDevice** : pendant l'exécution de hailo-ollama, `hailo_platform.VDevice()` ne peut être obtenu. Pour l'inférence VLM directe, arrêter hailo-ollama
- **VLM.generate_all() requiert frames** : l'inférence texte seule donne l'erreur `HAILO_INVALID_OPERATION`. Les prérequis API diffèrent entre LLM et VLM
- **Template prompt Qwen2-VL** : template Jinja2 insérant `<|vision_start|><|image_pad|><|vision_end|>`. En incluant `{"type": "image"}` dans le format de message, le SDK traite automatiquement

---

## Phase 12 : API Compatible OpenAI + Correction de Bug de Changement de Périphérique (2026-03-14)

### Objectifs

1. Fournir une API compatible OpenAI permettant l'utilisation directe de Hailo GenAI depuis des outils externes comme OpenAI SDK / LiteLLM / Continue.dev / Open WebUI
2. Corriger les défauts de prise en charge async de Quart
3. Support des endpoints SSE pour les outils MCP

### Implémentation : API Compatible OpenAI (`hailo_openai_routes.py`)

Nouveau fichier `extensions/builtin_hailo_genai/hailo_openai_routes.py`. Implémentation des 4 endpoints suivants :

| Endpoint | Fonction | Modèles supportés |
|---|---|---|
| `GET /v1/models` | Liste des modèles disponibles | Tous les modèles + CLIP |
| `POST /v1/chat/completions` | Chat texte/image (support stream) | LLM + VLM |
| `POST /v1/audio/transcriptions` | Transcription audio | Whisper |
| `POST /v1/embeddings` | Texte → vecteur CLIP | CLIP ViT-B/16 |

#### Décisions de Conception

- **Support Vision** : accepte directement le format OpenAI Vision API (`image_url` avec `data:` base64). De plus, référence directe aux images de la bibliothèque YU via format `file_id:123`
- **HTTP URL non supporté** : pour prévention SSRF, `http://` / `https://` non acceptés dans `image_url`
- **Alias de modèles** : définition d'alias compatibles OpenAI comme `whisper-1` → `whisper-base`, `clip` → `clip-vit-b-16`
- **Audio non-WAV** : conversion automatique par ffmpeg (16kHz mono PCM16)
- **Champ Usage** : le SDK Hailo ne retourne pas le nombre de tokens, donc fixé à `0`. Possibilité d'amélioration future

#### Outils MCP

- `hailo_genai_openai_info` : outil helper retournant la liste des endpoints et les méthodes d'utilisation (généré localement sans appel API)

### Correction : Générateurs SSE async Quart

Défauts de prise en charge async dans les générateurs SSE de tous les fichiers de routes :

| Fichier | Problème | Correction |
|---|---|---|
| `hailo_llm_routes.py` | `def generate_sse()` était une fonction synchrone | Changé en `async def`, `get_llm()` et `next(it)` exécutés via `asyncio.to_thread` |
| `hailo_vlm_routes.py` | Idem + référence DB synchrone | Idem + wrap avec `run_db_sync` |
| `hailo_s2t_routes.py` | Transcribe en exécution synchrone + DB synchrone | Wrap avec `asyncio.to_thread` + `run_db_sync` |
| `hailo_chat_routes.py` | Idem (LLM/VLM tous deux) | Rendu async de tous les appels bloquants |

Avec Quart (ASGI), si le générateur n'est pas `async def`, il bloque la boucle d'événements et les autres requêtes ne sont plus traitées pendant la diffusion SSE.

### Bug Découvert : Incohérence de Singleton au Changement de Périphérique

#### Symptôme

Appel du LLM après utilisation du VLM provoque l'erreur `'NoneType' object has no attribute 'get_context_usage_size'`. Toujours présente dans l'ordre inverse (LLM→VLM→LLM).

#### Analyse de Cause

Hailo-10H ne peut détenir qu'un seul VDevice, géré exclusivement par `device_manager.py`. Flux lors du changement de modèle :

1. `get_vlm()` du VLM → `acquire_genai("vlm", ...)` → en interne `_release_internal()` libère le VDevice du LLM
2. Utilisation du VLM terminée
3. `get_llm()` du LLM → `_instance` persiste + `model_name` correspond → **réutilisation de l'instance existante**
4. Le VDevice derrière `_instance._llm` est déjà libéré → `get_context_usage_size()` appelé sur `None` et crash

Racine du problème : même si le `_instance` du singleton persiste, l'objet SDK Hailo interne (`self._llm`) pointe vers un VDevice déjà `.release()` par `_release_internal()` de `device_manager`. Côté compteur de références Python, `_instance._llm` est encore vivant, mais côté SDK Hailo, la ressource native est libérée.

#### Correction

Ajout d'une vérification de `device_manager.get_current_owner()` dans le check de réutilisation de singleton de `get_llm()` / `get_vlm()` / `get_s2t()` :

```python
def get_llm(model_name="qwen2.5-1.5b-chat"):
    global _instance
    with _lock:
        if _instance is not None and _instance.model_name == model_name:
            from core.hailo_device_core.device_manager import get_current_owner
            if get_current_owner() == "llm":
                return _instance  # Détient le périphérique → réutilisation OK
            # Périphérique pris par un autre modèle → recréer
            _instance = None
        ...
```

Même correction appliquée aux 3 singletons LLM / VLM / S2T.

#### Validation

Confirmation du fonctionnement normal sur 4 changements consécutifs LLM → VLM → LLM → VLM.

### Autres Corrections

- **Méthode MCP `post_sse`** : ajout de la méthode `post_sse()` à `mcp_server/client.py` consommant le stream SSE et retournant le texte final en JSON. Utilisée par les outils `hailo_llm_generate` et `hailo_vlm_generate`
- **Paramètre MCP `yolo_search`** : `labels` → renommé en `class_name` (correspond au nom de paramètre côté API)
- **Circuit Breaker** : ajout de `_READ_SUFFIXES` (`_status`, `_info`, `_list`, `_stats`). Les outils de type statut comme `hailo_genai_status` autorisés en état half_open
- **Semantic Search async** : wrap de `get_encoder_info()` et `semantic_search()` avec `run_db_sync` (prévention du blocage de boucle d'événements Quart)

### Notes Techniques

- **La contrainte d'exclusivité VDevice est au niveau SDK** : même en conservant la référence objet côté Python, dès que la ressource est libérée côté natif Hailo SDK, elle n'est plus utilisable. En utilisant le pattern singleton, il faut vérifier séparément la validité de la ressource native
- **Quart + générateur synchrone** : passer un générateur synchrone à une réponse SSE Quart fonctionne, mais le traitement entre les `yield` bloque la boucle d'événements. Pour des traitements lourds comme l'inférence Hailo, toujours déporter sur un autre thread via `asyncio.to_thread`
- **Intégration OpenAI Vision API et VLM** : OpenAI Vision API reçoit les images via le champ `image_url`, mais Hailo VLM reçoit `frames` (tableau numpy). La couche de conversion effectue décodage base64 → décodage OpenCV → redimensionnement 336x336 RGB

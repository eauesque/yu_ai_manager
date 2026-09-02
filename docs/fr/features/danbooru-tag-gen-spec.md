# Spécification d'implémentation du Danbooru Auto-Tagging

**Statut** : Implémenté (Phase 1-5 : v2.77.0)
**Cible** : YU AI Manager
**Objectif** : Assigner automatiquement des tags Danbooru aux images IA en utilisant une approche à deux niveaux : WD-Tagger ONNX (CPU) + VLM (API compatible OpenAI)
**Implémentation** : `extensions/builtin_wd_tagger/core_impl/` (12 fichiers), `routes/wd_tagger.py` (11 API)

---

## Statut de mise en œuvre

| Phase | Statut | Localisation |
|---|---|---|
| Phase 1 : WD-Tagger ONNX | **Complète** | `extensions/builtin_wd_tagger/core_impl/engine_onnx.py` |
| Phase 2 : Moteur VLM (compatible OpenAI) | **Complète** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` + `engine_composite.py` |
| Phase 3 : Post-traitement des tags | **Complète** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` |
| Phase 4 : API de lot | **Complète** | `extensions/builtin_wd_tagger/core_impl/batch_ops.py` + `routes/wd_tagger.py` |
| Phase 5 : Interface utilisateur | **Complète** | Page d'outils + modal de détail badges WD + lecteur XMP |

### Aperçu de la mise en œuvre Phase 2/3 (v2.77.0-v2.77.1)

- **Moteur VLM** (`engine_vlm.py`) : Basculement automatique entre l'API compatible OpenAI et l'API native Ollama
- **Moteur composite** (`engine_composite.py`) : Pipeline à deux niveaux ONNX + VLM (Mode B)
- **Post-traitement des tags** (`tag_postprocess.py`) : Normalisation (minuscules, trait de soulignement, suppression des caractères invalides, déduplication) + filtre NSFW (~30 tags)
- **Fabrique de moteur** : Routage par `engine_type` ("onnx" / "vlm" / "both")
- **Interface utilisateur** : Sélection du type de moteur, paramètres d'URL/modèle/délai d'attente VLM, test de connexion, filtre NSFW
- **API** : `GET /api/wd-tagger/vlm/test`, `GET /api/wd-tagger/vlm/models`
- **MCP** : Outils `wd_tagger_vlm_test`, `wd_tagger_vlm_models`
- **Testé** : Marquage d'image réelle confirmé avec Ollama qwen2.5vl:7b, 23 tests unitaires en cours

---

## Art préalable

### DeepDanbooru (KichangKim)
- **Approche** : Modèle de classification d'image (TensorFlow) pour la prédiction directe de tags
- **Forces** : Rapide, spécialisé dans les tags, convertible en ONNX
- **Faiblesses** : Ensemble de tags fixe, ne peut pas s'adapter aux nouveaux tags
- **Référence** : Déjà intégré dans A1111

### WD-Tagger (SmilingWolf) — Adopté dans la Phase 1
- **Approche** : Successeur de DeepDanbooru. Quatre architectures : SwinV2/ViT/ConvNeXt/EVA02
- **Forces** : Précision supérieure à DeepDanbooru, classification de catégorie incluse (général/personnage/droits d'auteur/évaluation)
- **ONNX** : Modèles ONNX officiels + `selected_tags.csv` distribués sur HuggingFace
- **Entrée** : 448x448 RGB (rapport d'aspect préservé + remplissage blanc)

### DanTagGen / DTG (KohakuBlueleaf)
- **Approche** : LLM basé sur LLaMA (400M) pour la génération et la complétion de tags
- **Forces** : Complétion de tags sensible au contexte
- **Faiblesses** : Lent en raison de l'inférence LLM
- **HuggingFace** : `KBlueLeaf/DanTagGen-beta`

### Justification du design
Le système supporte **à la fois** WD-Tagger ONNX (rapide, fiable) et Qwen2-VL via hailo-ollama (flexible, sensible au contexte), permettant aux utilisateurs de choisir le bon outil pour le travail.

---

## Architecture

```
[Entrée d'image]
    |
[Sélection du moteur]  (engine_factory.py)
    |-- WD-Tagger ONNX (rapide, ensemble de tags fixe ~10 000 tags)  [Phase 1 : implémenté]
    |       | Scores de confiance + liste de tags catégorisée
    |-- Qwen2-VL via hailo-ollama (lent, flexible, sensible au contexte)   [Phase 2]
    |       | Array JSON -> analyse des tags
    |-- Deux niveaux : ONNX -> complément Qwen2-VL                    [Phase 2 option]
    |       | Alimenter les tags ONNX dans le prompt, laisser le LLM générer des tags supplémentaires
    |
[Post-traitement : normalisation des tags, filtrage NSFW]  [Phase 3]
    |
[DB : sauvegarde dans la table file_wd_tags]  (store.py)
[XMP : intégrer dans le fichier (optionnel)]  (xmp_write.py)
```

---

## Phase 1 : Moteur WD-Tagger ONNX — Implémenté

**Modèle** : SmilingWolf/wd-swinv2-tagger-v3 (recommandé), ViT v3, ConvNeXt v3, EVA02-Large v3

**Fichiers d'implémentation** (`extensions/builtin_wd_tagger/core_impl/`):
| Fichier | Lignes | Rôle |
|---|---|---|
| `types.py` | ~60 | TagPrediction, WdTagResult, WdTaggerEngine ABC |
| `tag_csv.py` | ~70 | Analyse de selected_tags.csv, mappage des catégories |
| `model_download.py` | ~120 | Téléchargement HTTP HuggingFace |
| `engine_onnx.py` | ~150 | Inférence ONNX (448x448, BGR, filtrage des seuils) |
| `engine_factory.py` | ~50 | Cache + création de moteur |
| `store.py` | ~130 | CRUD DB (table file_wd_tags) |
| `xmp_xml.py` | ~60 | Construction de paquet XMP |
| `xmp_read.py` | ~90 | Lecture XMP |
| `xmp_write.py` | ~160 | Écriture XMP vers PNG/JPEG/WebP |
| `config_ops.py` | ~70 | Lecture/écriture config.json |
| `single_ops.py` | ~80 | Pipeline de marquage d'image unique |
| `batch_ops.py` | ~120 | Traitement par lot (intégration JobManager) |

**DB** : Table `file_wd_tags` (schéma v14)
```sql
CREATE TABLE file_wd_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    model      TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name, model)
);
```

**API** : `routes/wd_tagger.py` — 11 points de terminaison

---

## Phase 2 : Moteur VLM (API compatible OpenAI) — Implémenté (v2.77.0)

**Objectif** : Complémenter WD-Tagger ONNX avec des descriptions détaillées et des tags contextuels que ONNX ne peut pas capturer
**Implémentation** : `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` (moteur VLM générique compatible OpenAI)
**Note** : La spécification originale prévoyait un `engine_hailo.py` spécifique à Hailo, mais l'implémentation réelle utilise un moteur générique `engine_vlm.py` qui gère Ollama, hailo-ollama et d'autres serveurs compatibles OpenAI uniformément. Il supporte le basculement automatique entre l'API compatible OpenAI (`/v1/chat/completions`) et l'API native Ollama (`/api/chat`).

### Configuration du matériel

| Élément | Spécification |
|---|---|
| **Dispositif** | Raspberry Pi 5 + accélérateur AI Hailo-10H |
| **Mémoire** | 8 Go de RAM |
| **Modèle VLM** | **Qwen2-VL-2B-Instruct** (seul VLM du Hailo Model Zoo) |
| **Framework d'inférence** | hailo-ollama (API compatible OpenAI) |
| **Point de terminaison** | `http://<pi-ip>:8000/v1/chat/completions` |

### Caractéristiques du modèle

- **Qwen2-VL-2B-Instruct** : Un modèle Vision-Langage de la famille Qwen (2B paramètres)
- Il appartient à la famille Qwen, pas à la famille llava. La précision de la compréhension des images est généralement supérieure aux modèles basés sur llava
- À 2B paramètres, il s'adapte confortablement dans la RAM de 8 Go du Hailo-10H
- Le texte seul Qwen2 (1.5B) a été confirmé fonctionnant avec hailo-ollama
- **Note** : En février 2026, c'est le seul VLM disponible pour Hailo-10H

### Conception du prompt

```python
SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
Analyze the image and output ONLY Danbooru-style tags as a JSON array.
Rules:
- Use underscores instead of spaces (e.g., long_hair, blue_eyes)
- Output ONLY the JSON array, no other text
- Include tags for: character count, gender, hair, eyes, clothing, pose, background, art style
- Do NOT include copyright or character name tags unless clearly identifiable
- Maximum 40 tags
Example output: ["1girl", "solo", "long_hair", "blue_eyes", "smile"]"""

USER_PROMPT = "Tag this image with Danbooru tags."
```

### Conception de l'implémentation (`extensions/builtin_wd_tagger/core_impl/engine_hailo.py` — ~100 lignes)

```python
import base64
import json
import logging
import urllib.request
from pathlib import Path

from .types import TagPrediction, WdTagResult, WdTaggerEngine

logger = logging.getLogger(__name__)

_USER_AGENT = "YU-AI-Manager/2.0 (WD-Tagger Qwen2-VL)"

class HailoQwen2VLEngine(WdTaggerEngine):
    """Qwen2-VL-2B-Instruct via hailo-ollama (OpenAI-compatible API)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "qwen2-vl:2b",
        timeout: int = 60,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def tag_image(self, image_path: str) -> WdTagResult:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        # MIME type inference
        suffix = Path(image_path).suffix.lower()
        mime = {"png": "image/png", "webp": "image/webp"}.get(
            suffix.lstrip("."), "image/jpeg"
        )

        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime};base64,{image_b64}"
                        }},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 512,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )

        resp = urllib.request.urlopen(req, timeout=self._timeout)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        raw_tags = json.loads(content)

        # Response format: list or {"tags": [...]}
        if isinstance(raw_tags, dict) and "tags" in raw_tags:
            raw_tags = raw_tags["tags"]
        if not isinstance(raw_tags, list):
            raw_tags = []

        tags = []
        for t in raw_tags:
            name = str(t).strip().lower().replace(" ", "_")
            if name:
                tags.append(TagPrediction(
                    tag=name,
                    confidence=0.5,  # LLMs do not return confidence scores
                    category="general",
                ))

        return WdTagResult(tags=tags, model=self._model)

    def get_name(self) -> str:
        return f"Qwen2-VL ({self._model})"

    def is_available(self) -> bool:
        """Check connectivity to the hailo-ollama server."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/models",
                headers={"User-Agent": _USER_AGENT},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status == 200
        except Exception:
            return False
```

### Modes de fonctionnement

**Mode A : Qwen2-VL autonome**
```
Image -> Qwen2-VL -> Array de tags JSON -> Normalisation -> Sauvegarde DB
```
- Le LLM analyse directement l'image et génère les tags
- Pas de scores de confiance (uniformément définis à 0.5)
- Marquage flexible sans ensemble de tags fixe
- Vitesse : ~3-10 secondes par image (estimé sur Hailo-10H)

**Mode B : Complément WD-Tagger ONNX -> Qwen2-VL (Deux niveaux)**
```
Image -> WD-Tagger ONNX -> Tags haute-confiance (>=0.7)
                              |
                              v
    Qwen2-VL: "These tags describe the image. Suggest additional tags."
                              |
                              v
    Tags ONNX + tags complément LLM -> Fusion -> Normalisation -> Sauvegarde DB
```
- Combine les tags fiables ONNX avec la compréhension contextuelle du LLM
- L'inclusion de tags ONNX dans le prompt devrait améliorer la précision du LLM
- Vitesse : ONNX (~0.5s) + LLM (~3-10s) = ~4-11 secondes par image

**Prompt Mode B** :
```python
补完_SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
The image already has these tags from automated classification: {existing_tags}
Analyze the image and suggest ADDITIONAL Danbooru-style tags not in the list above.
Output ONLY a JSON array of new tags. Use underscores instead of spaces.
Focus on: composition, mood, background details, specific clothing items, art style.
Maximum 20 additional tags.
Example: ["looking_at_viewer", "outdoors", "cloudy_sky", "pleated_skirt"]"""
```

### Ajout à engine_factory.py

```python
# Addition to get_engine() in engine_factory.py

engine_type = config.get("engine_type", "onnx")  # "onnx" | "hailo" | "both"

if engine_type == "hailo":
    from .engine_hailo import HailoQwen2VLEngine
    engine = HailoQwen2VLEngine(
        base_url=config.get("hailo_url", "http://localhost:8000"),
        model=config.get("hailo_model", "qwen2-vl:2b"),
        timeout=config.get("hailo_timeout", 60),
    )
elif engine_type == "both":
    # Two-tier: ONNX -> Hailo complement (Phase 2 option)
    ...
```

### Entrées config.json

```json
{
  "wd_tagger": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "general_threshold": 0.35,
    "character_threshold": 0.85,
    "write_xmp": true,
    "auto_download": true,
    "engine_type": "onnx",
    "hailo_url": "http://localhost:8000",
    "hailo_model": "qwen2-vl:2b",
    "hailo_timeout": 60
  }
}
```

### Vérification pré-implémentation (Test matériel Pi)

1. **Confirmer que Qwen2-VL-2B-Instruct se lance sur hailo-ollama**
   ```bash
   # On the Pi
   hailo-ollama run qwen2-vl:2b
   ```

2. **Confirmer que les requêtes de vision fonctionnent via l'API compatible OpenAI**
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen2-vl:2b",
       "messages": [{"role": "user", "content": [
         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}},
         {"type": "text", "text": "What is in this image?"}
       ]}],
       "max_tokens": 256
     }'
   ```

3. **Confirmer que la sortie JSON au format Danbooru est stable**
   - Vérifier que hailo-ollama supporte `response_format: json_object`
   - Un fallback d'extraction JSON basé sur regex de la sortie textuelle est nécessaire s'il n'est pas pris en charge

4. **Mesurer la vitesse d'inférence réelle** — secondes par image (requis pour le calcul de la taille du lot)

---

## Phase 3 : Post-traitement des tags — Implémenté (v2.77.0)

**Implémentation** : `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`
**Intégration** : Appliqué automatiquement après l'inférence dans `single_ops.py` / `batch_ops.py`

```python
class TagPostProcessor:
    INVALID_CHARS = set('[](){}"\'/\\')
    MAX_TAG_LEN = 100

    def normalize(self, tags: list[str]) -> list[str]:
        result = []
        for tag in tags:
            tag = tag.strip().lower()
            tag = tag.replace(" ", "_")
            # Remove invalid characters
            tag = "".join(c for c in tag if c not in self.INVALID_CHARS)
            if 1 <= len(tag) <= self.MAX_TAG_LEN:
                result.append(tag)
        # Deduplicate and sort
        return sorted(set(result))

    def filter_nsfw(self, tags: list[str], allow_nsfw: bool) -> list[str]:
        # NSFW tag list (managed in a separate file)
        if allow_nsfw:
            return tags
        return [t for t in tags if t not in NSFW_TAG_SET]
```

**Intégration avec Phase 1** :
- WD-Tagger ONNX sépare déjà les tags de classification en utilisant la catégorie 9 (classification)
- Le filtre NSFW utilise les tags de classification (`explicit`, `questionable`) plus une liste NSFW supplémentaire
- Implémentation : `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` (~80 lignes)

---

## Phase 4 : API de traitement par lot — Implémenté

**API** (`routes/wd_tagger.py`) :

| Méthode | Chemin | Objectif |
|---|---|---|
| POST | `/api/wd-tagger/batch` | Démarrer un lot (file_ids, limit, force) |
| POST | `/api/wd-tagger/tag/<file_id>` | Marquer une seule image |
| GET | `/api/wd-tagger/tags/<file_id>` | Récupérer les tags |
| DELETE | `/api/wd-tagger/tags/<file_id>` | Supprimer les tags |
| GET | `/api/wd-tagger/stats` | Statistiques |
| GET | `/api/wd-tagger/untagged` | Lister les fichiers non marqués |
| GET/POST | `/api/wd-tagger/config` | Paramètres CRUD |
| POST | `/api/wd-tagger/model/download` | Téléchargement de modèle |
| GET | `/api/wd-tagger/model/status` | Statut du modèle |
| GET | `/api/wd-tagger/xmp/<file_id>` | Lecture XMP |

**Flux de traitement** (`batch_ops.py`) :
1. Traiter les fichiers dans `file_ids` séquentiellement (par défaut aux fichiers non marqués avec `meta_source=unknown` quand non spécifié)
2. Exécuter l'inférence via le moteur
3. UPSERT dans la table `file_wd_tags` (le moteur est identifié par la colonne du modèle)
4. Intégrer XMP dans le fichier (optionnel)
5. Suivre la progression et supporter l'annulation via JobManager

---

## Phase 5 : Interface utilisateur — Implémenté

**Page d'outils** (`templates/tools/content/primary/_wd_tagger.html`) :
- Sélection du modèle (4 modèles), curseurs de seuil (général/personnage)
- Bascule d'écriture XMP, bouton de téléchargement de modèle
- Bouton d'exécution par lot + barre de progression
- Affichage des statistiques (nombre de tags, répartition par catégorie, nombre de fichiers non marqués)

**Modal de détail** :
- Badges de tags WD (général=bleu, personnage=vert, droits d'auteur=orange, classification=rouge)
- Bouton de lecteur XMP (dc:subject + espace de noms wdtag + XML brut)
- Le clic sur le tag déclenche la recherche

---

## Structure de fichier (Actuelle)

```
extensions/builtin_wd_tagger/core_impl/
├── __init__.py              # Initialisation du module
├── types.py                 # TagPrediction, WdTagResult, WdTaggerEngine ABC
├── tag_csv.py               # Analyse de selected_tags.csv
├── model_download.py        # Téléchargement du modèle HuggingFace
├── engine_onnx.py           # Inférence WD-Tagger ONNX [Phase 1]
├── engine_vlm.py            # Moteur VLM (compatible OpenAI) [Phase 2 : complet]
├── engine_composite.py      # Deux niveaux ONNX + VLM [Phase 2 : complet]
├── engine_factory.py        # Création + cache du moteur
├── store.py                 # CRUD DB (file_wd_tags)
├── xmp_xml.py               # Construction de paquet XMP
├── xmp_read.py              # Lecture XMP
├── xmp_write.py             # Écriture XMP (PNG/JPEG/WebP)
├── config_ops.py            # Lecture/écriture config.json
├── single_ops.py            # Pipeline de marquage d'image unique
├── batch_ops.py             # Traitement par lot (JobManager)
├── batch_processors.py      # Logique interne du traitement par lot
└── tag_postprocess.py       # Normalisation des tags, filtre NSFW [Phase 3 : complet]

routes/wd_tagger.py          # Points de terminaison API (11 total)

src/ts/tools-page/wd-tagger/
├── core.ts                  # CRUD des paramètres, lot, téléchargement du modèle
└── render.ts                # Rendu DOM

src/ts/runtime-tools-ui/tools/
└── wd-tags.ts               # Modal de détail tags WD + lecteur XMP
```

---

## Priorité de mise en œuvre (Mise à jour)

```
Phase 1 (WD-Tagger ONNX)        -> Complète
Phase 4 (API de lot)             -> Complète
Phase 5 (Interface utilisateur)  -> Complète
Phase 3 (Post-traitement/NSFW)   -> Suivant (~80 lignes supplémentaires)
Phase 2 (Qwen2-VL hailo-ollama) -> Après test matériel Pi (~100 lignes supplémentaires + changements factory)
```

---

## Références

- WD-Tagger (SmilingWolf) : https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
- DeepDanbooru : https://github.com/KichangKim/DeepDanbooru
- DanTagGen : https://huggingface.co/KBlueLeaf/DanTagGen-beta
- Hailo Model Zoo VLM : Qwen2-VL-2B-Instruct (Hailo.ai Model Explorer)
- Spécification de l'API hailo-ollama : Référer à la source du fork modifié

---

*Créé : 2026-02-27 / Mis à jour : 2026-02-27 (implémentation Phase 1 complète, Phase 2 révisée vers la base Qwen2-VL)*

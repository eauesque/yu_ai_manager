# Extension Speech-to-Text

**Statut** : Implémenté (v3.28.0)
**Cible** : `extensions/builtin_speech_to_text/`
**Objectif** : Transcrire les fichiers vidéo et audio avec détection automatique du moteur

---

## Aperçu

Cette Extension extrait l'audio des fichiers vidéo et audio et le transcrit à l'aide des modèles Whisper.
Elle sélectionne automatiquement le moteur optimal en fonction du matériel disponible et fonctionne sur GPU ou CPU même sans NPU Hailo.

---

## Priorité des moteurs

| Priorité | Moteur | Bibliothèque | Matériel cible |
|--------|-------------|-----------|-----------------|
| P100 | `hailo` | `hailo_platform.genai` | Hailo-10H NPU |
| P70 | `torch-whisper-rocm` | `torch` (ROCm) + `transformers` | GPU AMD (ROCm/HIP) |
| P50 | `faster-whisper-cuda` | `faster-whisper` (CTranslate2) | GPU NVIDIA (CUDA) |
| P40 | `torch-whisper-cuda` | `torch` (CUDA) + `transformers` | GPU NVIDIA (CUDA) |
| P20 | `torch-whisper-cpu` | `torch` + `transformers` | CPU |
| P50 | `faster-whisper-cpu` | `faster-whisper` (CTranslate2) | CPU |
| P10 | `whisper-cpp` | `pywhispercpp` | CPU (le plus léger) |

En mode `auto`, le moteur ayant la priorité la plus élevée parmi ceux retournant `is_available() == True` est sélectionné.

---

## Configuration spécifique à l'environnement

### Exigences communes

- Python 3.11+
- ffmpeg (requis pour extraire l'audio de la vidéo)

### Hailo-10H NPU (Raspberry Pi AI HAT 2)

Aucun package supplémentaire n'est requis (`hailo_platform` doit déjà être installé).
Le modèle (`whisper-base` etc.) doit avoir été téléchargé via l'Extension GenAI.

```bash
# Télécharger le modèle à partir de l'interface utilisateur de l'Extension GenAI s'il n'est pas déjà présent
```

### GPU NVIDIA (CUDA)

```bash
# Recommandé : faster-whisper (léger, pas besoin de PyTorch)
pip install faster-whisper

# Le GPU est utilisé automatiquement quand CUDA est détecté (float16)
# Bascule au CPU automatiquement quand CUDA est absent (int8)
```

### GPU AMD (ROCm)

```bash
# 1. Installer PyTorch édition ROCm
#    Officiel : https://pytorch.org/get-started/locally/
#    Exemple (ROCm 6.x) :
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2

# 2. Installer HuggingFace transformers
pip install transformers

# 3. Définir le moteur dans la config (auto-détecté en mode "auto")
#    Dans les paramètres Extension : backend: "rocm" ou "auto"
```

**Mécanisme de détection ROCm** : PyTorch expose ROCm comme CUDA via HIP.
Le système identifie ROCm quand `torch.version.hip` n'est pas `None`.

**Exigences mémoire** (ROCm) :

| Modèle | Estimation VRAM |
|--------|----------|
| tiny | ~150 MB |
| base | ~300 MB |
| small | ~500 MB |
| medium | ~1.5 GB |

### CPU uniquement

```bash
# Option 1 : faster-whisper (recommandé, rapide avec quantification int8)
pip install faster-whisper

# Option 2 : whisper.cpp (le plus léger, pas besoin de PyTorch)
pip install pywhispercpp

# Option 3 : torch + transformers (à usage général mais lourd)
pip install torch transformers
```

**Estimations de performance CPU** (modèle base, 1 minute d'audio) :

| Moteur | RPi 5 | x86 (4 core) |
|---|---|---|
| faster-whisper (int8) | ~30 sec | ~5 sec |
| whisper.cpp | ~40 sec | ~8 sec |
| torch (float32) | ~90 sec | ~15 sec |

---

## Configuration

Configurer via la page des paramètres Extension (`/ext/speech-to-text/`) ou config.json :

| Élément | Choix | Défaut | Description |
|------|--------|-----------|------|
| `backend` | auto / hailo / cuda / rocm / cpu | auto | Moteur d'inférence |
| `model_size` | tiny / base / small / medium | base | Taille du modèle Whisper |
| `default_language` | Code BCP-47 (ja, en, etc.) | ja | Langue par défaut |

---

## Points de terminaison API

Tous les points de terminaison sont sous le préfixe `/ext/speech-to-text`.

### POST `/api/s2t/transcribe`

Transcrit l'audio WAV téléchargé.

- **Content-Type** : `multipart/form-data`
- **Paramètres** : `audio` (fichier), `language` (optionnel)
- **Réponse** : `{ status, text, segments, language, sample_rate, backend }`

### POST `/api/s2t/transcribe-video`

Transcrit un fichier vidéo/audio enregistré dans la DB. Les résultats sont enregistrés en tant qu'annotations.

- **Corps** : `{ file_id: int, language?: string }`
- **Réponse** : `{ status, text, segments, language, backend }`
- **Annotation** : `source="s2t"`, clés : `transcript`, `transcript_segments`, `transcript_backend`

### POST `/api/s2t/batch-transcribe`

Transcription par lot de plusieurs fichiers (s'exécute en arrière-plan).

Choisir **une seule** des trois méthodes d'entrée (mutuellement exclusive) :

#### Méthode 1 : Liste d'ID de fichier (Héritage)

```json
{
  "file_ids": [123, 456, 789],
  "language": "ja"
}
```

#### Méthode 2 : Répertoire

Détecte automatiquement les fichiers vidéo/audio dans le répertoire spécifié et traite uniquement ceux enregistrés dans la DB.

```json
{
  "directory": "/path/to/videos/",
  "recursive": true,
  "language": "en"
}
```

- `recursive` (par défaut : `true`) : Recherche récursive des sous-répertoires
- Extensions cibles : `.webm`, `.mp4`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv`, `.mp3`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.flac`

#### Méthode 3 : Liste Text/CSV

Spécifiez un fichier texte ou CSV listant les chemins de fichier.

```json
{
  "list_file": "/path/to/targets.txt",
  "language": "ja"
}
```

**Format du fichier texte** (`.txt` etc.) :
```
# Les lignes de commentaire (lignes commençant par # sont ignorées)
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```

**Format CSV** (`.csv`) :
```csv
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```
La première colonne est utilisée comme chemin de fichier. Les lignes commençant par `#` sont ignorées.

#### Options communes

| Paramètre | Type | Défaut | Description |
|-----------|---|-----------|------|
| `language` | string | Valeur config (généralement `ja`) | Code de langue (voir ci-dessous) |
| `recursive` | bool | `true` | Méthode répertoire uniquement : recherche récursive de sous-répertoires |

#### Limites et contraintes

- Nombre maximal de fichiers cibles : **500**
- Seuls les fichiers enregistrés dans la DB (table `files`) sont traités
- Les fichiers supprimés (`is_deleted=1`) sont exclus

#### Exemple de réponse

```json
{
  "status": "started",
  "total": 15,
  "mode": "directory",
  "directory": "/mnt/videos/",
  "recursive": true,
  "files_found": 23,
  "matched_in_db": 15
}
```

- **Événements SSE** : `s2t.batch_start`, `s2t.batch_progress`, `s2t.batch_complete`

### GET `/api/s2t/transcript/<file_id>`

Récupère les résultats de transcription enregistrés. À la fois `source="s2t"` et `source="hailo:s2t"` sont vérifiées pour la compatibilité rétroactive.

### GET `/api/s2t/status`

Retourne l'état du moteur et une liste des moteurs disponibles.

---

## Outils MCP

| Nom de l'outil | Description |
|---------|------|
| `s2t_status` | Obtenir l'état du moteur |
| `s2t_transcribe_video` | Transcrire un seul fichier vidéo |
| `s2t_batch_transcribe` | Démarrer la transcription par lot (file_ids / directory / list_file) |
| `s2t_get_transcript` | Récupérer la transcription enregistrée |

### Paramètres de `s2t_batch_transcribe`

| Paramètre | Type | Requis | Description |
|-----------|---|------|------|
| `file_ids` | list[int] | *1 | Liste d'ID fichier (max 500) |
| `directory` | string | *1 | Chemin du répertoire (auto-détecte vidéo/audio) |
| `list_file` | string | *1 | Chemin du fichier Text/CSV |
| `recursive` | bool | | Méthode répertoire uniquement. Recherche récursive de sous-répertoires (par défaut true) |
| `language` | string | | Code de langue. Vide = config par défaut |
| `expected_count` | int | | Pour détecter la troncature des file_ids |

*1 : Spécifier exactement un de `file_ids`, `directory` ou `list_file` (mutuellement exclusif)

---

## Structure de fichier

```
extensions/builtin_speech_to_text/
  extension.json                      # Manifeste
  speech_to_text_ext.py               # Point d'entrée (Blueprint)
  s2t_routes.py                       # Points de terminaison API d'un seul fichier
  s2t_batch_routes.py                 # Points de terminaison API par lot
  core_impl/
    base.py                           # Classe de base abstraite S2TBackend
    backend_hailo.py                  # Hailo-10H NPU
    backend_faster_whisper.py         # faster-whisper (CUDA/CPU)
    backend_torch_whisper.py          # PyTorch transformers (ROCm/CUDA/CPU)
    backend_whisper_cpp.py            # whisper.cpp (CPU)
    backend_registry.py               # Auto-détection + gestion singleton
  templates/speech_to_text/
    s2t.html                          # Page UI
mcp_server/
  s2t_tools.py                        # Définitions d'outils MCP
```

---

## Codes de langue pris en charge

Principaux codes de langue (BCP-47) pris en charge par Whisper :

| Code | Langue | Code | Langue |
|--------|------|--------|------|
| `ja` | Japonais | `en` | Anglais |
| `zh` | Chinois | `ko` | Coréen |
| `de` | Allemand | `fr` | Français |
| `es` | Espagnol | `it` | Italien |
| `pt` | Portugais | `ru` | Russe |
| `ar` | Arabe | `hi` | Hindi |
| `th` | Thaï | `vi` | Vietnamien |
| `nl` | Néerlandais | `tr` | Turc |
| `pl` | Polonais | `uk` | Ukrainien |
| `id` | Indonésien | `sv` | Suédois |

D'autres langues prises en charge par Whisper peuvent également être spécifiées. Une chaîne vide déclenche la détection automatique.
La langue par défaut peut être modifiée via le paramètre Extension `default_language` (valeur initiale : `ja`).

---

## Limitations connues

- **Délai de premier chargement** : transformers / faster-whisper télécharge les modèles depuis HuggingFace Hub (base : ~150MB). La première exécution peut prendre plusieurs minutes
- **Modèles HEF Hailo** : Doivent être téléchargés via l'Extension GenAI. L'Extension S2T elle-même n'a pas de fonctionnalité de téléchargement
- **Mémoire** : Le modèle moyen peut causer des erreurs d'insuffisance de mémoire sur RPi 5 (8GB). Le modèle base est recommandé
- **Concurrence** : Les moteurs sont gérés comme des singleton. Les requêtes arrivant lors du traitement par lot partagent la même instance
- **Format d'entrée** : WAV (PCM s16le, mono, 16kHz) est supposé. Les fichiers vidéo sont automatiquement convertis via ffmpeg
- **Entrée par lot** : Les méthodes directory / list_file traitent uniquement les fichiers enregistrés dans la DB. Les fichiers non scannés doivent d'abord être enregistrés via `start_scan`

---

## Transcription en direct

Transcrivez l'audio de la radio Internet, des flux RTSP et des fichiers vidéo en temps réel et affichez les sous-titres dans l'interface WebUI.

### Deux modes

- **Mode chunk** (par défaut) : Divise l'audio en chunks en utilisant la détection de silence basée sur RMS. Compatible avec tous les moteurs (Hailo/CUDA/CPU). Les résultats s'affichent après la fin de chaque énoncé.
- **Mode live** : Effectue la transcription incrémentale en utilisant le Silero VAD de faster-whisper. Affiche les résultats intermédiaires pendant que la parole est toujours en cours. Nécessite un moteur ONNX/faster-whisper.

### Sources d'entrée prise en charge

- Flux HTTP/HTTPS (radio Internet, etc.)
- Caméras RTSP
- Flux RTMP

### Points de terminaison API

| Point de terminaison | Méthode | Fonction |
|---|---|---|
| `/api/s2t/stream/start` | POST | Démarrer le streaming (`source_url`, `language`, `mode`) |
| `/api/s2t/stream/stop` | POST | Arrêter le streaming |
| `/api/s2t/stream/status` | GET | Obtenir le statut |
| `/api/s2t/stream/transcript` | GET | Obtenir la transcription complète |
| `/api/s2t/stream/export/txt` | GET | Exporter en tant que texte |
| `/api/s2t/stream/export/srt` | GET | Exporter en tant que sous-titres SRT |

### Événements SSE

| Événement | Description |
|---|---|
| `s2t.stream_chunk` | Texte finalisé |
| `s2t.stream_interim` | Texte intermédiaire (Mode live uniquement) |
| `s2t.stream_complete` | Streaming complété |

### Outils MCP

| Outil | Description |
|---|---|
| `s2t_stream_start(source_url, language)` | Démarrer le streaming |
| `s2t_stream_stop()` | Arrêter le streaming |
| `s2t_stream_status()` | Obtenir le statut |
| `s2t_stream_transcript()` | Obtenir la transcription complète |

### Configuration de streaming

Éléments configurables dans `extension.json` :

| Élément | Description | Défaut |
|---|---|---|
| `stream_chunk_min_sec` | Longueur minimale de chunk en mode Chunk (secondes) | — |
| `stream_chunk_max_sec` | Longueur maximale de chunk en mode Chunk (secondes) | — |
| `stream_silence_threshold` | Seuil RMS pour la détection de silence | — |
| `stream_silence_ms` | Durée du silence pour la détection (millisecondes) | — |
| `live_interval_sec` | Intervalle de transcription en mode Live (secondes) | — |

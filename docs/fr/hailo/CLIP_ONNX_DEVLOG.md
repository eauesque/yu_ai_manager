# Journal de développement — CLIP ONNX Embedding

## Vue d'ensemble

Extension de la recherche d'images sémantique CLIP, initialement réservée au Hailo-10H, vers un encodeur universel basé sur ONNX Runtime.
Fonctionne sur CPU / NVIDIA CUDA / AMD ROCm / DirectML (Ryzen AI NPU) / OpenVINO (Intel NPU) / CoreML.

## Date : 2026-03-04

### Phase 1 : Extraction de la couche core partagée (`core/clip_core/`, maintenant dans `extensions/builtin_clip_search/core_impl/`)

**Fichiers créés :**
- `encoder_abc.py` — ABC `ClipImageEncoder` (encode, encode_batch, close, output_dim, backend_name)
- `image_io.py` — E/S d'images (fichiers plats + archives ZIP/7z)
- `vector_store.py` — Déplacé directement depuis `hailo_clip_core`
- `text_encoder.py` — Déplacé directement depuis `hailo_clip_core`
- `search.py` — Déplacé + imports changés en relatifs
- `indexer.py` — Généralisé : `encoder_factory` et `preprocess_fn` paramétrés par injection
- `event_handler.py` — Déplacé + chemin import `indexer` changé
- `encoder_factory.py` — `get_best_encoder()` (priorité Hailo > ONNX), `get_preprocessor()`, `get_encoder_info()`

**Décisions de conception :**
- Import différé de `cv2` — le chargement du module réussit même sur les machines sans opencv-python
- Résolution automatique via `encoder_factory.py` si `encoder_factory`/`preprocess_fn` de `indexer.py` sont None
- `event_handler.py` utilise la clé de config extension `"builtin-hailo-semantic-search"` telle quelle (compatibilité ascendante)

### Phase 2 : Encodeur ONNX (`core/clip_onnx_core/`, maintenant dans `extensions/builtin_clip_onnx/core_impl/`)

**Fichiers créés :**
- `onnx_encoder.py` — Singleton `OnnxClipEncoder(ClipImageEncoder)`
- `preprocess.py` — Normalisation NCHW float32 (valeurs officielles CLIP mean/std)
- `model_download.py` — `onnx/vision_model.onnx` de HuggingFace `Xenova/clip-vit-base-patch16`

**Notes techniques :**
- Modèle : `Xenova/clip-vit-base-patch16` (ONNX converti avec HuggingFace Optimum)
- Entrée : `pixel_values` (batch, 3, 224, 224) float32
- Sortie : `image_embeds` (batch, 512) float32 — normalisé L2 avant stockage
- Conforme au pattern de `engine_onnx.py` de WD-Tagger (SessionOptions, batch inference)
- Sélection automatique d'ExecutionProvider via `ort_provider.select_providers()`

### Phase 3 : Refactorisation Hailo

- Ajout de l'héritage ABC `ClipImageEncoder` à `HailoClipEncoder` + propriété `backend_name`
- `vector_store.py`, `text_encoder.py`, `search.py`, `event_handler.py` → ré-exportation depuis `clip_core`
- `indexer.py` → Wrapper léger injectant l'encodeur/preprocess Hailo
- `image_preprocess.py` → Utilisation de `clip_core.image_io.read_and_decode()`

### Phase 4 : Extension de inference_core

- Ajout de `OpenVINOExecutionProvider` à `_PROVIDER_PRIORITY` dans `ort_provider.py`
- Ajout du champ `openvino_available` + `_detect_openvino()` à `gpu_detect.py`
- Ajout des informations du package OpenVINO à `ort_install_helper.py`

### Phase 5 : Extension de l'Extension

- Ajout du paramètre `preferred_backend` dans `extension.json`
- Changement de tous les imports vers `core.clip_core`
- Nouvelles API : `GET /api/backends`, `GET /api/model/status`, `POST /api/model/download`

### Phase 6 : Outils MCP

- `mcp_server/semantic_tools.py` — 5 outils
- `semantic_search`, `semantic_index_start/status/stop`, `semantic_backend_info`

### Phase 7 : runtime_runner.py

- Changement de l'import event handler vers `core.clip_core.event_handler`

## Compatibilité des vecteurs

Hailo HEF (quantification uint8 → déquantification) et ONNX (sortie float32 directe) sont basés sur le même modèle `openai/clip-vit-base-patch16`, donc la sortie est dans le même espace d'embedding 512 dimensions.
Les index construits avec Hailo et les vecteurs ajoutés avec ONNX peuvent coexister.

## Matrice de support NPU

| NPU | Package ORT | Provider |
|---|---|---|
| AMD Ryzen AI | `onnxruntime-directml` | DmlExecutionProvider |
| Intel NPU | `onnxruntime-openvino` | OpenVINOExecutionProvider |
| NVIDIA GPU | `onnxruntime-gpu` | CUDAExecutionProvider |
| AMD GPU | `onnxruntime-rocm` | ROCmExecutionProvider |
| Apple Silicon | `onnxruntime` | CoreMLExecutionProvider |
| CPU (fallback) | `onnxruntime` | CPUExecutionProvider |

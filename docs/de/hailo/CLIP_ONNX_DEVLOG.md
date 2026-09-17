# CLIP ONNX Embedding — Entwicklungsprotokoll

## Überblick

Die für Hailo-10H exklusive CLIP-semantische Bildsuche wurde auf einen universellen ONNX-Runtime-basierten Encoder erweitert.
Unterstützt CPU / NVIDIA CUDA / AMD ROCm / DirectML (Ryzen AI NPU) / OpenVINO (Intel NPU) / CoreML.

## Datum: 2026-03-04

### Phase 1: Extraktion der gemeinsamen Kernschicht (`core/clip_core/`, jetzt `extensions/builtin_clip_search/core_impl/`)

**Erstellte Dateien:**
- `encoder_abc.py` — `ClipImageEncoder` ABC (encode, encode_batch, close, output_dim, backend_name)
- `image_io.py` — Bild-I/O (einfache Dateien + ZIP/7z-Archiv-Unterstützung)
- `vector_store.py` — Direkt von `hailo_clip_core` übernommen
- `text_encoder.py` — Direkt von `hailo_clip_core` übernommen
- `search.py` — Übernommen + imports auf relativ geändert
- `indexer.py` — Verallgemeinert: `encoder_factory` und `preprocess_fn` als injizierte Parameter
- `event_handler.py` — Übernommen + `indexer`-Import geändert
- `encoder_factory.py` — `get_best_encoder()` (Priorität: Hailo > ONNX), `get_preprocessor()`, `get_encoder_info()`

**Designentscheidungen:**
- `cv2` wird verzögert importiert — Module laden auch ohne opencv-python
- Bei `None` für `encoder_factory`/`preprocess_fn` in `indexer.py` automatische Auflösung über `encoder_factory.py`
- `event_handler.py` verwendet weiterhin den Extension-Config-Schlüssel `"builtin-hailo-semantic-search"` für Rückwärtskompatibilität

### Phase 2: ONNX-Encoder (`core/clip_onnx_core/`, jetzt `extensions/builtin_clip_onnx/core_impl/`)

**Erstellte Dateien:**
- `onnx_encoder.py` — `OnnxClipEncoder(ClipImageEncoder)` Singleton
- `preprocess.py` — float32 NCHW-Normalisierung (mean/std sind offizielle CLIP-Werte)
- `model_download.py` — HuggingFace `Xenova/clip-vit-base-patch16` `onnx/vision_model.onnx`

**Technische Hinweise:**
- Modell: `Xenova/clip-vit-base-patch16` (ONNX, konvertiert mit HuggingFace Optimum)
- Eingabe: `pixel_values` (batch, 3, 224, 224) float32
- Ausgabe: `image_embeds` (batch, 512) float32 — L2-normalisiert gespeichert
- Entspricht dem Muster von WD-Tagger `engine_onnx.py` (SessionOptions, Batch-Inferenz)
- `ort_provider.select_providers()` für automatische ExecutionProvider-Auswahl

### Phase 3: Hailo-Refactoring

- `HailoClipEncoder` erhält `ClipImageEncoder` ABC-Vererbung + `backend_name`-Eigenschaft
- `vector_store.py`, `text_encoder.py`, `search.py`, `event_handler.py` → Re-Export aus `clip_core`
- `indexer.py` → Dünner Wrapper, der Hailo encoder/preprocess injiziert
- `image_preprocess.py` → Verwendet `clip_core.image_io.read_and_decode()`

### Phase 4: inference_core-Erweiterung

- `OpenVINOExecutionProvider` zu `_PROVIDER_PRIORITY` in `ort_provider.py` hinzugefügt
- `openvino_available`-Feld + `_detect_openvino()` zu `gpu_detect.py` hinzugefügt
- OpenVINO-Paketinformationen zu `ort_install_helper.py` hinzugefügt

### Phase 5: Extension-Erweiterung

- `preferred_backend`-Einstellung zu `extension.json` hinzugefügt
- Alle imports auf `core.clip_core` geändert
- Neue APIs: `GET /api/backends`, `GET /api/model/status`, `POST /api/model/download`

### Phase 6: MCP-Tools

- `mcp_server/semantic_tools.py` — 5 Tools
- `semantic_search`, `semantic_index_start/status/stop`, `semantic_backend_info`

### Phase 7: runtime_runner.py

- event handler import auf `core.clip_core.event_handler` geändert

## Vektor-Kompatibilität

Hailo HEF (uint8-quantisiert → dequantisiert) und ONNX (float32-Direktausgabe) basieren beide auf demselben `openai/clip-vit-base-patch16`-Modell, daher ist der Ausgaberaum derselbe 512-dimensionale Embedding-Raum.
Mit Hailo erstellte Indizes und mit ONNX hinzugefügte Vektoren können gemischt werden.

## NPU-Unterstützungsmatrix

| NPU | ORT-Paket | Provider |
|---|---|---|
| AMD Ryzen AI | `onnxruntime-directml` | DmlExecutionProvider |
| Intel NPU | `onnxruntime-openvino` | OpenVINOExecutionProvider |
| NVIDIA GPU | `onnxruntime-gpu` | CUDAExecutionProvider |
| AMD GPU | `onnxruntime-rocm` | ROCmExecutionProvider |
| Apple Silicon | `onnxruntime` | CoreMLExecutionProvider |
| CPU (Fallback) | `onnxruntime` | CPUExecutionProvider |

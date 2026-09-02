# Log de Desenvolvimento do CLIP ONNX Embedding

## Visão Geral

Extensão da pesquisa semântica de imagens CLIP, que era exclusiva do Hailo-10H, para um encoder genérico baseado em ONNX Runtime.
Funciona em CPU / NVIDIA CUDA / AMD ROCm / DirectML (Ryzen AI NPU) / OpenVINO (Intel NPU) / CoreML.

## Data: 2026-03-04

### Phase 1: Extração da Camada de Núcleo Compartilhada (`core/clip_core/`, atualmente `extensions/builtin_clip_search/core_impl/`)

**Arquivos criados:**
- `encoder_abc.py` — ABC `ClipImageEncoder` (encode, encode_batch, close, output_dim, backend_name)
- `image_io.py` — I/O de imagem (suporte a arquivo simples + arquivos ZIP/7z)
- `vector_store.py` — Movido diretamente de `hailo_clip_core`
- `text_encoder.py` — Movido diretamente de `hailo_clip_core`
- `search.py` — Movido + imports alterados para relativos
- `indexer.py` — Generalizado: `encoder_factory` e `preprocess_fn` parametrizados por injeção
- `event_handler.py` — Movido + import de `indexer` alterado
- `encoder_factory.py` — `get_best_encoder()` (prioridade Hailo > ONNX), `get_preprocessor()`, `get_encoder_info()`

**Decisões de design:**
- `cv2` usa import tardio — o módulo carrega com sucesso mesmo em máquinas sem opencv-python
- Quando `encoder_factory`/`preprocess_fn` do `indexer.py` são None, resolvidos automaticamente via `encoder_factory.py`
- `event_handler.py` usa a chave de config da extension `"builtin-hailo-semantic-search"` como está (compatibilidade retroativa)

### Phase 2: Encoder ONNX (`core/clip_onnx_core/`, atualmente `extensions/builtin_clip_onnx/core_impl/`)

**Arquivos criados:**
- `onnx_encoder.py` — Singleton `OnnxClipEncoder(ClipImageEncoder)`
- `preprocess.py` — Normalização float32 NCHW (valores oficiais CLIP de mean/std)
- `model_download.py` — `onnx/vision_model.onnx` do `Xenova/clip-vit-base-patch16` no HuggingFace

**Notas técnicas:**
- Modelo: `Xenova/clip-vit-base-patch16` (ONNX convertido com HuggingFace Optimum)
- Entrada: `pixel_values` (batch, 3, 224, 224) float32
- Saída: `image_embeds` (batch, 512) float32 — salvo com normalização L2
- Segue o padrão do WD-Tagger `engine_onnx.py` (SessionOptions, inferência em lote)
- Seleção automática do ExecutionProvider com `ort_provider.select_providers()`

### Phase 3: Refatoração do Hailo

- Adicionado herança de ABC `ClipImageEncoder` ao `HailoClipEncoder` + propriedade `backend_name`
- `vector_store.py`, `text_encoder.py`, `search.py`, `event_handler.py` → re-exportados de `clip_core`
- `indexer.py` → wrapper fino que injeta encoder/preprocess do Hailo
- `image_preprocess.py` → usa `clip_core.image_io.read_and_decode()`

### Phase 4: Extensão do inference_core

- Adicionado `OpenVINOExecutionProvider` a `_PROVIDER_PRIORITY` em `ort_provider.py`
- Adicionado campo `openvino_available` + `_detect_openvino()` a `gpu_detect.py`
- Adicionadas informações do pacote OpenVINO a `ort_install_helper.py`

### Phase 5: Extensão da Extension

- Adicionada configuração `preferred_backend` ao `extension.json`
- Todos os imports alterados para `core.clip_core`
- Nova API: `GET /api/backends`, `GET /api/model/status`, `POST /api/model/download`

### Phase 6: Ferramentas MCP

- `mcp_server/semantic_tools.py` — 5 ferramentas
- `semantic_search`, `semantic_index_start/status/stop`, `semantic_backend_info`

### Phase 7: runtime_runner.py

- Import do event handler alterado para `core.clip_core.event_handler`

## Compatibilidade de Vetores

O Hailo HEF (uint8 quantizado→desquantizado) e o ONNX (saída float32 direta) são baseados no mesmo modelo `openai/clip-vit-base-patch16`, portanto a saída está no mesmo espaço de embedding de 512 dimensões.
Os vetores do índice construído com Hailo e os vetores adicionados com ONNX podem coexistir.

## Matriz de Suporte a NPU

| NPU | Pacote ORT | Provider |
|---|---|---|
| AMD Ryzen AI | `onnxruntime-directml` | DmlExecutionProvider |
| Intel NPU | `onnxruntime-openvino` | OpenVINOExecutionProvider |
| NVIDIA GPU | `onnxruntime-gpu` | CUDAExecutionProvider |
| AMD GPU | `onnxruntime-rocm` | ROCmExecutionProvider |
| Apple Silicon | `onnxruntime` | CoreMLExecutionProvider |
| CPU (fallback) | `onnxruntime` | CPUExecutionProvider |

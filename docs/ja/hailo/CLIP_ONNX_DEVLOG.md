# CLIP ONNX Embedding 開発ログ

## 概要

Hailo-10H 専用だった CLIP セマンティック画像検索を、ONNX Runtime ベースの汎用エンコーダーに拡張。
CPU / NVIDIA CUDA / AMD ROCm / DirectML (Ryzen AI NPU) / OpenVINO (Intel NPU) / CoreML で動作。

## 日付: 2026-03-04

### Phase 1: 共有コア層の抽出 (`core/clip_core/`、現在は `extensions/builtin_clip_search/core_impl/`)

**作成ファイル:**
- `encoder_abc.py` — `ClipImageEncoder` ABC (encode, encode_batch, close, output_dim, backend_name)
- `image_io.py` — 画像 I/O (プレーンファイル + ZIP/7z アーカイブ対応)
- `vector_store.py` — `hailo_clip_core` からそのまま移動
- `text_encoder.py` — `hailo_clip_core` からそのまま移動
- `search.py` — 移動 + import 先を相対に変更
- `indexer.py` — 汎用化: `encoder_factory` と `preprocess_fn` を注入パラメータ化
- `event_handler.py` — 移動 + `indexer` import 先変更
- `encoder_factory.py` — `get_best_encoder()` (Hailo > ONNX 優先), `get_preprocessor()`, `get_encoder_info()`

**設計判断:**
- `cv2` は遅延 import — opencv-python がないマシンでもモジュール読み込みは成功
- `indexer.py` の `encoder_factory`/`preprocess_fn` が None の場合、`encoder_factory.py` 経由で自動解決
- `event_handler.py` は extension config キー `"builtin-hailo-semantic-search"` をそのまま使用 (後方互換)

### Phase 2: ONNX エンコーダー (`core/clip_onnx_core/`、現在は `extensions/builtin_clip_onnx/core_impl/`)

**作成ファイル:**
- `onnx_encoder.py` — `OnnxClipEncoder(ClipImageEncoder)` シングルトン
- `preprocess.py` — float32 NCHW 正規化 (mean/std は CLIP 公式値)
- `model_download.py` — HuggingFace `Xenova/clip-vit-base-patch16` の `onnx/vision_model.onnx`

**技術ノート:**
- モデル: `Xenova/clip-vit-base-patch16` (HuggingFace Optimum で変換済み ONNX)
- 入力: `pixel_values` (batch, 3, 224, 224) float32
- 出力: `image_embeds` (batch, 512) float32 — L2 正規化して保存
- WD-Tagger `engine_onnx.py` のパターンに準拠 (SessionOptions, batch inference)
- `ort_provider.select_providers()` で ExecutionProvider 自動選択

### Phase 3: Hailo リファクタリング

- `HailoClipEncoder` に `ClipImageEncoder` ABC 継承追加 + `backend_name` プロパティ
- `vector_store.py`, `text_encoder.py`, `search.py`, `event_handler.py` → `clip_core` からの再エクスポート
- `indexer.py` → Hailo encoder/preprocess を注入する薄いラッパー
- `image_preprocess.py` → `clip_core.image_io.read_and_decode()` を使用

### Phase 4: inference_core 拡張

- `ort_provider.py` の `_PROVIDER_PRIORITY` に `OpenVINOExecutionProvider` 追加
- `gpu_detect.py` に `openvino_available` フィールド + `_detect_openvino()` 追加
- `ort_install_helper.py` に OpenVINO パッケージ情報追加

### Phase 5: Extension 拡張

- `extension.json` に `preferred_backend` 設定追加
- import 先を全て `core.clip_core` に変更
- 新規 API: `GET /api/backends`, `GET /api/model/status`, `POST /api/model/download`

### Phase 6: MCP ツール

- `mcp_server/semantic_tools.py` — 5 ツール
- `semantic_search`, `semantic_index_start/status/stop`, `semantic_backend_info`

### Phase 7: runtime_runner.py

- event handler import を `core.clip_core.event_handler` に変更

## ベクトル互換性

Hailo HEF (uint8 量子化→脱量子化) と ONNX (float32 直接出力) は
同じ `openai/clip-vit-base-patch16` モデルベースなので、出力は同じ 512 次元 embedding 空間。
既存の Hailo で構築したインデックスと ONNX で追加したベクトルは混在可能。

## NPU サポートマトリックス

| NPU | ORT パッケージ | プロバイダー |
|---|---|---|
| AMD Ryzen AI | `onnxruntime-directml` | DmlExecutionProvider |
| Intel NPU | `onnxruntime-openvino` | OpenVINOExecutionProvider |
| NVIDIA GPU | `onnxruntime-gpu` | CUDAExecutionProvider |
| AMD GPU | `onnxruntime-rocm` | ROCmExecutionProvider |
| Apple Silicon | `onnxruntime` | CoreMLExecutionProvider |
| CPU (fallback) | `onnxruntime` | CPUExecutionProvider |

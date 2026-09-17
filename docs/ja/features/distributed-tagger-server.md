# 分散推論サーバー (Distributed Inference Server)

**ステータス**: 実装完了 (v4.53.2)
**対象**: `deploy/hailo_tagger_server.py`
**目的**: LAN 内の複数マシンで推論（タグ付け・CLIP・YOLO・Whisper）を分散実行する

---

## 概要

YU AI Manager の推論機能を LAN 内の複数マシンに分散させるスタンドアロン HTTP サーバーです。
メインの YU AI Manager 本体は不要で、Python + 依存パッケージのみで動作します。

```
┌─────────────────────────────┐
│   YU AI Manager (メイン)     │
│   Inference Server Registry │
│   共有キュー・ワークスティーリング  │
└──────────┬──────────────────┘
      ┌────┼────────────┐
 ┌────▼────┐ ┌─────▼─────┐ ┌────▼────┐
 │ Pi5 A   │ │ Windows B │ │ Pi5 C   │
 │Hailo NPU│ │CUDA GPU   │ │ONNX CPU │
 │:9090    │ │:9090      │ │:8080    │
 └─────────┘ └───────────┘ └─────────┘
```

### 対応推論モード

| モード | エンドポイント | 説明 |
|--------|-------------|------|
| **Tagger** | `POST /tag` | WD-Tagger によるタグ付け（`--model-dir` 指定時のみ有効） |
| **CLIP** | `POST /clip-encode` | CLIP ViT-B/16 画像エンコード（セマンティック検索用） |
| **YOLO** | `POST /yolo-detect` | YOLOv11n / YOLOv8n 物体検出 |
| **Whisper** | `POST /whisper-transcribe` | 音声文字起こし |

全モードは遅延初期化（lazy-init）で、最初のリクエスト時にモデルをロードします。
CLIP・YOLO の ONNX モデルは未配置時に自動ダウンロードされます。

---

## 推論バックエンドとプロバイダ

### バックエンド優先順位

各推論モードは以下の優先順位でバックエンドを選択します：

| モード | 1st | 2nd | 3rd |
|--------|-----|-----|-----|
| Tagger | Hailo NPU | ONNX | — |
| CLIP | Hailo NPU | ONNX（自動ダウンロード） | — |
| YOLO | Hailo NPU | ONNX（自動ダウンロード） | — |
| Whisper | Hailo GenAI SDK | faster-whisper | whisper.cpp |

### ONNX Runtime プロバイダ自動選択

ONNX バックエンドはプラットフォームに応じて最速のプロバイダを自動選択します：

| 優先順位 | プロバイダ | プラットフォーム |
|---------|-----------|---------------|
| 1 | TensorRT | NVIDIA GPU (最速、TensorRT SDK 要) |
| 2 | CUDA | NVIDIA GPU |
| 3 | ROCm | AMD GPU (Linux) |
| 4 | MIGraphX | AMD GPU (Linux) |
| 5 | DirectML | Windows GPU (NVIDIA/AMD/Intel) |
| 6 | OpenVINO | Intel GPU/NPU |
| 7 | QNN | Qualcomm NPU |
| 8 | CoreML | macOS Apple Silicon GPU/ANE |
| 9 | Azure | Copilot+ PC NPU |
| 10 | CPU | フォールバック（常に利用可能） |

`--ort-provider cuda` のように手動指定も可能です。

### Hailo バックエンド

Hailo-10H NPU 搭載の Raspberry Pi 5 で利用可能。YOLO・CLIP は公式プリコンパイル済み HEF を使用。
Tagger 用の HEF は現時点で入手不可（DFC が WD-Tagger のアーキテクチャを未サポート）。

---

## セットアップ

### venv 自動検出

スクリプトは venv 外から実行された場合、自動的に venv の Python で再起動します：

```bash
# venv 有効化を忘れても OK
python deploy/hailo_tagger_server.py --port 9090
# → [auto-venv] Re-launching with .../venv/bin/python
```

検索順序: スクリプトディレクトリ → 親ディレクトリ → カレントディレクトリ

### 1. 依存パッケージ

```bash
# 共通（必須）
pip install numpy Pillow

# ONNX バックエンド
pip install onnxruntime           # CPU のみ
pip install onnxruntime-gpu       # NVIDIA CUDA

# Whisper バックエンド (オプション、いずれか)
pip install faster-whisper        # faster-whisper (CUDA/CPU)
# pip install whisper-cpp-python  # whisper.cpp (CPU)

# Hailo バックエンド (Pi5 + Hailo-10H)
# hailo_platform は Hailo Developer Zone から
```

### CUDA + cuDNN の設定 (NVIDIA GPU)

ONNX Runtime GPU 版を使うには CUDA + cuDNN のランタイム DLL が必要です：

| ONNX Runtime バージョン | 必要な CUDA | 必要な cuDNN |
|------------------------|-----------|-------------|
| 安定版 (1.x) | CUDA 12.x | cuDNN 9.x |
| nightly | CUDA 13.x | cuDNN 9.x |

**Windows の場合:**

1. CUDA Toolkit をインストール
2. cuDNN をインストール（`C:\Program Files\NVIDIA\CUDNN\v9.x\bin\<version>\x64\` に DLL がある）
3. `cudnn64_9.dll` があるディレクトリを PATH に追加
4. **PowerShell を再起動**（環境変数の反映に必要）

確認:
```powershell
where.exe cudnn64_9.dll
# → パスが表示されれば OK
```

### 2. モデルファイル

| モード | モデル | 場所 | 備考 |
|--------|--------|------|------|
| Tagger | WD-SwinV2 等 | `--model-dir` で指定 | `model.onnx` + `selected_tags.csv` |
| CLIP | ViT-B/16 | `~/.cache/yu_ai_manager/clip_onnx/` | **自動ダウンロード** (329 MB) |
| YOLO | YOLOv11n | `~/.cache/yu_ai_manager/yolo_onnx/` | **自動ダウンロード** |
| Whisper | faster-whisper-base | HuggingFace cache | **自動ダウンロード** |

### 3. サーバー起動

```bash
# 全モード（CLIP + YOLO + Whisper）— Tagger なし
python deploy/hailo_tagger_server.py --port 9090

# Tagger も有効化
python deploy/hailo_tagger_server.py --port 9090 --model-dir ./models/wd-swinv2-tagger-v3

# 認証トークン付き
python deploy/hailo_tagger_server.py --port 9090 --token "my-secret-token"

# 設定ファイル使用
python deploy/hailo_tagger_server.py --config tagger.json
```

### 4. YU AI Manager 側の登録

#### 推論サーバーとして登録（YOLO・Whisper・CLIP）

WebUI の **設定 → 推論サーバー** で登録、または MCP ツール:

```
inference_servers_add:
  name: "Windows ONNX"
  endpoint_url: "http://192.168.50.247:9090"
  inference_types: ["clip", "yolo", "whisper"]
  priority: 50
```

#### Tagger サーバーとして登録

WebUI の **設定 → Tagger → Tagger Server Registry** で登録。

---

## API エンドポイント

### GET /health

```json
{
  "status": "idle",
  "queue_depth": 0,
  "model": "wd-swinv2-tagger-v3",
  "backend": "onnx",
  "device": "onnx-cuda",
  "auth_required": false,
  "inference_types": ["clip", "yolo", "whisper"]
}
```

**device の値:**

| 値 | 意味 |
|----|------|
| `hailo-10h` | Hailo-10H NPU |
| `onnx-cuda` | ONNX Runtime CUDA |
| `onnx-tensorrt` | ONNX Runtime TensorRT |
| `onnx-rocm` | ONNX Runtime ROCm |
| `onnx-migraphx` | ONNX Runtime MIGraphX |
| `onnx-directml` | ONNX Runtime DirectML |
| `onnx-openvino` | ONNX Runtime OpenVINO |
| `onnx-qnn` | ONNX Runtime QNN |
| `onnx-coreml` | ONNX Runtime CoreML |
| `onnx-azure` | ONNX Runtime Azure NPU |
| `onnx-cpu` | ONNX Runtime CPU |

### POST /tag

画像をタグ付けします。`--model-dir` 指定時のみ有効。

```bash
curl -X POST -F "image=@test.png" http://host:9090/tag
```

```json
{
  "tags": [
    {"tag": "1girl", "confidence": 0.97, "category": "general"},
    {"tag": "hatsune_miku", "confidence": 0.88, "category": "character"}
  ],
  "model": "wd-swinv2-tagger-v3",
  "elapsed_ms": 145
}
```

### POST /clip-encode

画像の CLIP 埋め込みベクトルを生成します。

```bash
curl -X POST -F "images=@test.png" http://host:9090/clip-encode
```

```json
{
  "vectors": ["<base64-encoded float32 array>"],
  "model": "clip_vit_b_16",
  "count": 1
}
```

### POST /yolo-detect

画像内の物体を検出します。

```bash
curl -X POST -F "images=@test.png" http://host:9090/yolo-detect
```

```json
{
  "detections": [[
    {"class": "person", "confidence": 0.92, "bbox": [100, 50, 300, 400]}
  ]],
  "model": "yolov11n",
  "count": 1
}
```

### POST /whisper-transcribe

音声を文字起こしします。

```bash
# Raw WAV
curl -X POST -H "Content-Type: application/octet-stream" \
  --data-binary @audio.wav "http://host:9090/whisper-transcribe?language=ja"

# Multipart
curl -X POST -F "image=@audio.wav" "http://host:9090/whisper-transcribe?language=ja"
```

```json
{
  "status": "ok",
  "text": "こんにちは世界",
  "segments": [
    {"text": "こんにちは世界", "start": 0.0, "end": 1.5}
  ],
  "language": "ja",
  "backend": "faster-whisper-cuda"
}
```

---

## 設定ファイル

```json
{
  "port": 9090,
  "host": "0.0.0.0",
  "backend": "auto",
  "model": "wd-swinv2-tagger-v3",
  "model_dir": "./models/wd-swinv2-tagger-v3",
  "ort_provider": "",
  "general_threshold": 0.35,
  "character_threshold": 0.85,
  "bearer_token": ""
}
```

---

## 分散構成例

### 例 1: Pi5 (Hailo NPU) + Windows (CUDA GPU)

実際に動作確認済みの構成:

```
Pi5 (192.168.50.4:9090)
  ├── Tagger: Hailo NPU
  ├── CLIP: Hailo NPU
  ├── YOLO: Hailo NPU
  └── Whisper: Hailo GenAI SDK (NPU)

Windows (192.168.50.247:9090)
  ├── CLIP: ONNX CUDAExecutionProvider
  ├── YOLO: ONNX CUDAExecutionProvider
  └── Whisper: faster-whisper CUDA
```

### 例 2: macOS (CoreML) + Linux (ROCm)

```
Mac (192.168.1.10:9090)
  ├── CLIP: ONNX CoreMLExecutionProvider (Apple Silicon ANE)
  ├── YOLO: ONNX CoreMLExecutionProvider
  └── Whisper: faster-whisper CPU

Linux (192.168.1.20:9090)
  ├── CLIP: ONNX ROCMExecutionProvider (AMD GPU)
  ├── YOLO: ONNX ROCMExecutionProvider
  └── Whisper: faster-whisper ROCm
```

### 例 3: フォールバック構成

```
Server A (priority 10) -- 通常はこちらを使用
Server B (priority 50) -- A が落ちた場合のみ
```

Mode: `single`（最優先のみ使用）

---

## systemd でデーモン化

```ini
# /etc/systemd/system/inference-server.service
[Unit]
Description=YU AI Manager Inference Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/yu_ai_manager
ExecStart=/home/pi/yu_ai_manager/venv/bin/python deploy/hailo_tagger_server.py \
  --config /home/pi/tagger.json
Restart=on-failure
RestartSec=5
Environment=TAGGER_BEARER_TOKEN=my-secret-token

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now inference-server
```

---

## トラブルシューティング

### ONNX Runtime が CPU フォールバックする

```
[W] Failed to create CUDAExecutionProvider. Require cuDNN 9.* and CUDA 12/13.*
```

→ `/health` の `device` フィールドで確認
→ `where.exe cudnn64_9.dll` (Windows) / `find / -name cudnn64_9.dll` (Linux) でライブラリの所在を確認
→ PATH に追加後、**ターミナルを再起動**（環境変数の反映に必要）

### CLIP が 503 を返す

→ 初回リクエスト時に HuggingFace からモデル（329 MB）を自動ダウンロードします。ネットワーク接続を確認
→ ログに `CLIP ONNX: downloading ...` が出ているか確認

### auto-venv が無限ループする

→ v4.53.2 で修正済み。`sys.prefix != sys.base_prefix` で venv 判定

### 古い Python プロセスが残る

→ Windows: `tasklist | findstr python` で確認、`taskkill /F /IM python.exe` で全終了
→ Linux: `pkill -f hailo_tagger_server`

### Hailo VDevice 排他エラー

→ Hailo NPU は同時に 1 モデルのみ。LLM・VLM・S2T が実行中の場合は停止してから再試行

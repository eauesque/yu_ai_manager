# Speech-to-Text Extension

**ステータス**: 実装完了 (v3.28.0)
**対象**: `extensions/builtin_speech_to_text/`
**目的**: 動画・音声ファイルの文字起こしをバックエンド自動検出で実行

---

## 概要

動画や音声ファイルから音声を抽出し、Whisper モデルで文字起こしを行う Extension。
ハードウェアに応じて最適なバックエンドを自動選択し、Hailo NPU がない環境でも GPU/CPU で動作する。

---

## バックエンド優先順位

| 優先度 | バックエンド | ライブラリ | 対象ハードウェア |
|--------|-------------|-----------|-----------------|
| P100 | `hailo` | `hailo_platform.genai` | Hailo-10H NPU |
| P70 | `torch-whisper-rocm` | `torch` (ROCm) + `transformers` | AMD GPU (ROCm/HIP) |
| P50 | `faster-whisper-cuda` | `faster-whisper` (CTranslate2) | NVIDIA GPU (CUDA) |
| P40 | `torch-whisper-cuda` | `torch` (CUDA) + `transformers` | NVIDIA GPU (CUDA) |
| P20 | `torch-whisper-cpu` | `torch` + `transformers` | CPU |
| P50 | `faster-whisper-cpu` | `faster-whisper` (CTranslate2) | CPU |
| P10 | `whisper-cpp` | `pywhispercpp` | CPU (最軽量) |

`auto` モードでは `is_available()` が True のバックエンドの中から最高優先度のものが選択される。

---

## 環境別セットアップ

### 共通要件

- Python 3.11+
- ffmpeg (動画からの音声抽出に必要)

### Hailo-10H NPU (Raspberry Pi AI HAT 2)

追加パッケージ不要（`hailo_platform` が既にインストールされていれば動作）。
GenAI Extension でモデル (`whisper-base` 等) をダウンロード済みであること。

```bash
# モデルが未ダウンロードの場合は GenAI Extension の UI からダウンロード
```

### NVIDIA GPU (CUDA)

```bash
# 推奨: faster-whisper (軽量、PyTorch 不要)
pip install faster-whisper

# CUDA が検出されれば自動で GPU 使用 (float16)
# CUDA がなければ自動で CPU フォールバック (int8)
```

### AMD GPU (ROCm)

```bash
# 1. PyTorch ROCm 版のインストール
#    公式: https://pytorch.org/get-started/locally/
#    例 (ROCm 6.x):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2

# 2. HuggingFace transformers のインストール
pip install transformers

# 3. config で backend を設定 (auto でも自動検出される)
#    Extension 設定画面で backend: "rocm" または "auto"
```

**ROCm 検出の仕組み**: PyTorch は ROCm を HIP 経由で CUDA として公開する。
`torch.version.hip` が `None` でなければ ROCm と判定。

**メモリ要件** (ROCm):

| モデル | VRAM 目安 |
|--------|----------|
| tiny | ~150 MB |
| base | ~300 MB |
| small | ~500 MB |
| medium | ~1.5 GB |

### CPU のみ

```bash
# 選択肢 1: faster-whisper (推奨、int8 量子化で高速)
pip install faster-whisper

# 選択肢 2: whisper.cpp (最軽量、PyTorch 不要)
pip install pywhispercpp

# 選択肢 3: torch + transformers (汎用だが重い)
pip install torch transformers
```

**CPU パフォーマンス目安** (base モデル、1 分の音声):

| バックエンド | RPi 5 | x86 (4 core) |
|---|---|---|
| faster-whisper (int8) | ~30 秒 | ~5 秒 |
| whisper.cpp | ~40 秒 | ~8 秒 |
| torch (float32) | ~90 秒 | ~15 秒 |

---

## 設定項目

Extension 設定画面 (`/ext/speech-to-text/`) または config.json で設定:

| 項目 | 選択肢 | デフォルト | 説明 |
|------|--------|-----------|------|
| `backend` | auto / hailo / cuda / rocm / cpu | auto | 推論バックエンド |
| `model_size` | tiny / base / small / medium | base | Whisper モデルサイズ |
| `default_language` | BCP-47 コード (ja, en 等) | ja | デフォルト言語 |

---

## API エンドポイント

全て `/ext/speech-to-text` プレフィックス配下。

### POST `/api/s2t/transcribe`

アップロードされた WAV 音声を文字起こし。

- **Content-Type**: `multipart/form-data`
- **パラメータ**: `audio` (file), `language` (optional)
- **レスポンス**: `{ status, text, segments, language, sample_rate, backend }`

### POST `/api/s2t/transcribe-video`

DB 登録済みの動画/音声ファイルを文字起こし。結果は annotation に保存。

- **Body**: `{ file_id: int, language?: string }`
- **レスポンス**: `{ status, text, segments, language, backend }`
- **Annotation**: `source="s2t"`, keys: `transcript`, `transcript_segments`, `transcript_backend`

### POST `/api/s2t/batch-transcribe`

複数ファイルのバッチ文字起こし (バックグラウンド実行)。

3 つの入力方式から **1 つを選択** (排他的):

#### 方式 1: ファイル ID リスト (従来方式)

```json
{
  "file_ids": [123, 456, 789],
  "language": "ja"
}
```

#### 方式 2: ディレクトリ指定

指定ディレクトリ内の動画/音声ファイルを自動検出し、DB 登録済みのもののみ処理。

```json
{
  "directory": "/path/to/videos/",
  "recursive": true,
  "language": "en"
}
```

- `recursive` (デフォルト: `true`): サブディレクトリも再帰探索するか
- 対象拡張子: `.webm`, `.mp4`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv`, `.mp3`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.flac`

#### 方式 3: テキスト/CSV リスト

ファイルパスを列挙したテキストファイルまたは CSV を指定。

```json
{
  "list_file": "/path/to/targets.txt",
  "language": "ja"
}
```

**テキストファイル形式** (`.txt` 等):
```
# コメント行 (# で始まる行は無視)
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```

**CSV 形式** (`.csv`):
```csv
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```
1 列目がファイルパスとして使用される。`#` で始まる行はスキップ。

#### 共通オプション

| パラメータ | 型 | デフォルト | 説明 |
|-----------|---|-----------|------|
| `language` | string | 設定値 (通常 `ja`) | 言語コード (下記参照) |
| `recursive` | bool | `true` | directory 方式のみ: サブディレクトリ再帰探索 |

#### 上限・制約

- 対象ファイル数上限: **500 件**
- DB に登録済み (`files` テーブルに存在) のファイルのみ処理対象
- 削除済み (`is_deleted=1`) は除外

#### レスポンス例

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

- **SSE イベント**: `s2t.batch_start`, `s2t.batch_progress`, `s2t.batch_complete`

### GET `/api/s2t/transcript/<file_id>`

保存済みの文字起こし結果を取得。`source="s2t"` と `source="hailo:s2t"` の両方を参照 (後方互換)。

### GET `/api/s2t/status`

バックエンド状態と利用可能なバックエンド一覧。

---

## MCP ツール

| ツール名 | 説明 |
|---------|------|
| `s2t_status` | バックエンド状態取得 |
| `s2t_transcribe_video` | 動画ファイルの文字起こし (単体) |
| `s2t_batch_transcribe` | バッチ文字起こし開始 (file_ids / directory / list_file) |
| `s2t_get_transcript` | 保存済み文字起こし取得 |

### `s2t_batch_transcribe` パラメータ

| パラメータ | 型 | 必須 | 説明 |
|-----------|---|------|------|
| `file_ids` | list[int] | ※1 | ファイル ID リスト (最大 500) |
| `directory` | string | ※1 | ディレクトリパス (動画/音声を自動検出) |
| `list_file` | string | ※1 | テキスト/CSV ファイルパス |
| `recursive` | bool | | directory 使用時のみ。サブディレクトリ再帰 (デフォルト true) |
| `language` | string | | 言語コード。空 = 設定デフォルト |
| `expected_count` | int | | file_ids のトランケーション検出用 |

※1: `file_ids`, `directory`, `list_file` のいずれか 1 つを指定 (排他的)

---

## ファイル構成

```
extensions/builtin_speech_to_text/
  extension.json                      # マニフェスト
  speech_to_text_ext.py               # エントリポイント (Blueprint)
  s2t_routes.py                       # 単体 API ルート
  s2t_batch_routes.py                 # バッチ API ルート
  core_impl/
    base.py                           # S2TBackend 抽象基底
    backend_hailo.py                  # Hailo-10H NPU
    backend_faster_whisper.py         # faster-whisper (CUDA/CPU)
    backend_torch_whisper.py          # PyTorch transformers (ROCm/CUDA/CPU)
    backend_whisper_cpp.py            # whisper.cpp (CPU)
    backend_registry.py               # 自動検出 + シングルトン管理
  templates/speech_to_text/
    s2t.html                          # UI ページ
mcp_server/
  s2t_tools.py                        # MCP ツール定義
```

---

## 対応言語コード

Whisper が対応する主な言語コード (BCP-47):

| コード | 言語 | コード | 言語 |
|--------|------|--------|------|
| `ja` | 日本語 | `en` | English |
| `zh` | 中国語 | `ko` | 韓国語 |
| `de` | ドイツ語 | `fr` | フランス語 |
| `es` | スペイン語 | `it` | イタリア語 |
| `pt` | ポルトガル語 | `ru` | ロシア語 |
| `ar` | アラビア語 | `hi` | ヒンディー語 |
| `th` | タイ語 | `vi` | ベトナム語 |
| `nl` | オランダ語 | `tr` | トルコ語 |
| `pl` | ポーランド語 | `uk` | ウクライナ語 |
| `id` | インドネシア語 | `sv` | スウェーデン語 |

上記以外の Whisper 対応言語も指定可能。空文字列の場合は自動検出。
デフォルト言語は Extension 設定の `default_language` で変更可能 (初期値: `ja`)。

---

## 既知の制約

- **初回ロードの遅延**: transformers / faster-whisper はモデルを HuggingFace Hub からダウンロードする (base: ~150MB)。初回のみ数分かかる場合がある
- **Hailo HEF モデル**: GenAI Extension 経由でのダウンロードが必要。S2T Extension 単体ではダウンロード機能を持たない
- **メモリ**: RPi 5 (8GB) で medium モデルはメモリ不足になる可能性がある。base 推奨
- **同時実行**: バックエンドはシングルトン管理。バッチ処理中に別のリクエストが来た場合は同じインスタンスを共有
- **入力形式**: WAV (PCM s16le, mono, 16kHz) を前提。動画の場合は ffmpeg で自動変換
- **バッチ入力**: directory / list_file 方式では DB 登録済みファイルのみ対象。未スキャンのファイルは先に `start_scan` で DB に登録する必要がある

---

## リアルタイムストリーミング文字起こし

ネットラジオ・RTSP ストリーム・動画ファイルの音声をリアルタイムでテキスト化し、WebUI に字幕表示する機能。

### 2つのモード

- **Chunk モード** (デフォルト): RMS ベースの無音検出でチャンク分割。全バックエンド (Hailo/CUDA/CPU) 対応。発話終了後に結果を表示する。
- **Live モード**: faster-whisper の Silero VAD で逐次転写。発話中にも中間結果 (interim) を表示する。ONNX/faster-whisper バックエンドが必要。

### 対応入力ソース

- HTTP/HTTPS ストリーム（ネットラジオ等）
- RTSP カメラ
- RTMP ストリーム

### API エンドポイント

| エンドポイント | メソッド | 機能 |
|---|---|---|
| `/api/s2t/stream/start` | POST | ストリーミング開始 (`source_url`, `language`, `mode`) |
| `/api/s2t/stream/stop` | POST | ストリーミング停止 |
| `/api/s2t/stream/status` | GET | 状態取得 |
| `/api/s2t/stream/transcript` | GET | 全文取得 |
| `/api/s2t/stream/export/txt` | GET | テキストエクスポート |
| `/api/s2t/stream/export/srt` | GET | SRT 字幕エクスポート |

### SSE イベント

| イベント | 説明 |
|---|---|
| `s2t.stream_chunk` | 確定テキスト |
| `s2t.stream_interim` | 中間テキスト (Live モードのみ) |
| `s2t.stream_complete` | ストリーミング完了 |

### MCP ツール

| ツール名 | 説明 |
|---|---|
| `s2t_stream_start(source_url, language)` | ストリーミング開始 |
| `s2t_stream_stop()` | ストリーミング停止 |
| `s2t_stream_status()` | 状態取得 |
| `s2t_stream_transcript()` | 全文取得 |

### ストリーミング設定

`extension.json` で設定可能な項目:

| 項目 | 説明 | デフォルト |
|---|---|---|
| `stream_chunk_min_sec` | Chunk モードの最小チャンク長 (秒) | — |
| `stream_chunk_max_sec` | Chunk モードの最大チャンク長 (秒) | — |
| `stream_silence_threshold` | 無音検出の RMS 閾値 | — |
| `stream_silence_ms` | 無音判定時間 (ミリ秒) | — |
| `live_interval_sec` | Live モードの転写間隔 (秒) | — |

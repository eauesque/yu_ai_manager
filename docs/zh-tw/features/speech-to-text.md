# Speech-to-Text 擴充功能

**狀態**：已實作（v3.28.0）
**目標**：`extensions/builtin_speech_to_text/`
**目的**：自動偵測後端，轉錄影片和音訊檔案

---

## 概述

此擴充功能從影片和音訊檔案中擷取音訊，使用 Whisper 模型進行轉錄。
根據可用硬體自動選擇最佳後端，即使沒有 Hailo NPU 也可在 GPU 或 CPU 上執行。

---

## 後端優先順序

| 優先順序 | 後端 | 函式庫 | 目標硬體 |
|--------|-------------|-----------|-----------------|
| P100 | `hailo` | `hailo_platform.genai` | Hailo-10H NPU |
| P70 | `torch-whisper-rocm` | `torch` (ROCm) + `transformers` | AMD GPU (ROCm/HIP) |
| P50 | `faster-whisper-cuda` | `faster-whisper` (CTranslate2) | NVIDIA GPU (CUDA) |
| P40 | `torch-whisper-cuda` | `torch` (CUDA) + `transformers` | NVIDIA GPU (CUDA) |
| P20 | `torch-whisper-cpu` | `torch` + `transformers` | CPU |
| P50 | `faster-whisper-cpu` | `faster-whisper` (CTranslate2) | CPU |
| P10 | `whisper-cpp` | `pywhispercpp` | CPU（最輕量） |

在 `auto` 模式下，會選擇 `is_available() == True` 中優先順序最高的後端。

---

## 各環境設定

### 共通需求

- Python 3.11+
- ffmpeg（從影片擷取音訊所需）

### Hailo-10H NPU（Raspberry Pi AI HAT 2）

不需要額外套件（`hailo_platform` 必須已安裝）。
模型（`whisper-base` 等）必須透過 GenAI Extension 預先下載。

```bash
# 若模型尚未存在，從 GenAI Extension UI 下載
```

### NVIDIA GPU (CUDA)

```bash
# 建議：faster-whisper（輕量，不需要 PyTorch）
pip install faster-whisper

# 偵測到 CUDA 時自動使用 GPU（float16）
# 沒有 CUDA 時自動退回 CPU（int8）
```

### AMD GPU (ROCm)

```bash
# 1. 安裝 PyTorch ROCm 版本
#    官方：https://pytorch.org/get-started/locally/
#    範例（ROCm 6.x）：
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2

# 2. 安裝 HuggingFace transformers
pip install transformers

# 3. 在設定中設定後端（auto 模式下自動偵測）
#    在擴充功能設定中：backend: "rocm" 或 "auto"
```

**ROCm 偵測機制**：PyTorch 透過 HIP 將 ROCm 公開為 CUDA。
當 `torch.version.hip` 不為 `None` 時，系統識別為 ROCm。

**記憶體需求**（ROCm）：

| 模型 | VRAM 估計 |
|--------|----------|
| tiny | ~150 MB |
| base | ~300 MB |
| small | ~500 MB |
| medium | ~1.5 GB |

### 純 CPU

```bash
# 選項 1：faster-whisper（建議，int8 量化速度快）
pip install faster-whisper

# 選項 2：whisper.cpp（最輕量，不需要 PyTorch）
pip install pywhispercpp

# 選項 3：torch + transformers（通用但較重）
pip install torch transformers
```

**CPU 效能估計**（base 模型，1 分鐘音訊）：

| 後端 | RPi 5 | x86（4 核心） |
|---|---|---|
| faster-whisper (int8) | ~30 秒 | ~5 秒 |
| whisper.cpp | ~40 秒 | ~8 秒 |
| torch (float32) | ~90 秒 | ~15 秒 |

---

## 設定

透過擴充功能設定頁面（`/ext/speech-to-text/`）或 config.json 進行設定：

| 項目 | 選項 | 預設值 | 說明 |
|------|--------|-----------|------|
| `backend` | auto / hailo / cuda / rocm / cpu | auto | 推論後端 |
| `model_size` | tiny / base / small / medium | base | Whisper 模型大小 |
| `default_language` | BCP-47 代碼（ja、en 等） | ja | 預設語言 |

---

## API 端點

所有端點位於 `/ext/speech-to-text` 前綴之下。

### POST `/api/s2t/transcribe`

轉錄上傳的 WAV 音訊。

- **Content-Type**：`multipart/form-data`
- **參數**：`audio`（檔案）、`language`（選用）
- **回應**：`{ status, text, segments, language, sample_rate, backend }`

### POST `/api/s2t/transcribe-video`

轉錄 DB 中註冊的影片/音訊檔案。結果儲存為註解。

- **Body**：`{ file_id: int, language?: string }`
- **回應**：`{ status, text, segments, language, backend }`
- **註解**：`source="s2t"`，鍵值：`transcript`、`transcript_segments`、`transcript_backend`

### POST `/api/s2t/batch-transcribe`

批次轉錄多個檔案（在背景執行）。

從以下三種輸入方式中選擇**一種**（互斥）：

#### 方法 1：檔案 ID 清單（舊版）

```json
{
  "file_ids": [123, 456, 789],
  "language": "ja"
}
```

#### 方法 2：目錄

自動偵測指定目錄中的影片/音訊檔案，僅處理已在 DB 中註冊的檔案。

```json
{
  "directory": "/path/to/videos/",
  "recursive": true,
  "language": "en"
}
```

- `recursive`（預設：`true`）：遞迴搜尋子目錄
- 目標副檔名：`.webm`、`.mp4`、`.avi`、`.mov`、`.mkv`、`.m4v`、`.ogv`、`.mp3`、`.wav`、`.ogg`、`.opus`、`.m4a`、`.aac`、`.flac`

#### 方法 3：文字/CSV 清單

指定列出檔案路徑的文字檔或 CSV。

```json
{
  "list_file": "/path/to/targets.txt",
  "language": "ja"
}
```

**文字檔格式**（`.txt` 等）：
```
# 註解行（以 # 開頭的行會被忽略）
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```

**CSV 格式**（`.csv`）：
```csv
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```
第一欄用作檔案路徑。以 `#` 開頭的行會被跳過。

#### 共通選項

| 參數 | 類型 | 預設值 | 說明 |
|-----------|---|-----------|------|
| `language` | string | 設定值（通常為 `ja`） | 語言代碼（見下方） |
| `recursive` | bool | `true` | 僅限目錄方法：遞迴搜尋子目錄 |

#### 限制與約束

- 最大目標檔案數：**500**
- 僅處理已在 DB 中註冊的檔案（`files` 資料表）
- 已刪除的檔案（`is_deleted=1`）會被排除

#### 回應範例

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

- **SSE 事件**：`s2t.batch_start`、`s2t.batch_progress`、`s2t.batch_complete`

### GET `/api/s2t/transcript/<file_id>`

取得已儲存的轉錄結果。為向後相容，同時檢查 `source="s2t"` 和 `source="hailo:s2t"`。

### GET `/api/s2t/status`

回傳後端狀態和可用後端清單。

---

## MCP 工具

| 工具名稱 | 說明 |
|---------|------|
| `s2t_status` | 取得後端狀態 |
| `s2t_transcribe_video` | 轉錄單一影片檔案 |
| `s2t_batch_transcribe` | 啟動批次轉錄（file_ids / directory / list_file） |
| `s2t_get_transcript` | 取得已儲存的轉錄 |

### `s2t_batch_transcribe` 參數

| 參數 | 類型 | 必要 | 說明 |
|-----------|---|------|------|
| `file_ids` | list[int] | *1 | 檔案 ID 清單（最多 500） |
| `directory` | string | *1 | 目錄路徑（自動偵測影片/音訊） |
| `list_file` | string | *1 | 文字/CSV 檔案路徑 |
| `recursive` | bool | | 僅限目錄方法。遞迴搜尋子目錄（預設 true） |
| `language` | string | | 語言代碼。空值 = 設定預設值 |
| `expected_count` | int | | 用於偵測 file_ids 截斷 |

*1：從 `file_ids`、`directory` 或 `list_file` 中指定剛好一個（互斥）

---

## 檔案結構

```
extensions/builtin_speech_to_text/
  extension.json                      # 清單
  speech_to_text_ext.py               # 進入點（Blueprint）
  s2t_routes.py                       # 單檔 API 路由
  s2t_batch_routes.py                 # 批次 API 路由
  core_impl/
    base.py                           # S2TBackend 抽象基底類別
    backend_hailo.py                  # Hailo-10H NPU
    backend_faster_whisper.py         # faster-whisper（CUDA/CPU）
    backend_torch_whisper.py          # PyTorch transformers（ROCm/CUDA/CPU）
    backend_whisper_cpp.py            # whisper.cpp（CPU）
    backend_registry.py               # 自動偵測 + 單例管理
  templates/speech_to_text/
    s2t.html                          # UI 頁面
mcp_server/
  s2t_tools.py                        # MCP 工具定義
```

---

## 支援的語言代碼

Whisper 支援的主要語言代碼（BCP-47）：

| 代碼 | 語言 | 代碼 | 語言 |
|--------|------|--------|------|
| `ja` | 日語 | `en` | 英語 |
| `zh` | 中文 | `ko` | 韓語 |
| `de` | 德語 | `fr` | 法語 |
| `es` | 西班牙語 | `it` | 義大利語 |
| `pt` | 葡萄牙語 | `ru` | 俄語 |
| `ar` | 阿拉伯語 | `hi` | 印地語 |
| `th` | 泰語 | `vi` | 越南語 |
| `nl` | 荷蘭語 | `tr` | 土耳其語 |
| `pl` | 波蘭語 | `uk` | 烏克蘭語 |
| `id` | 印尼語 | `sv` | 瑞典語 |

其他 Whisper 支援的語言也可以指定。空字串觸發自動偵測。
預設語言可透過擴充功能設定 `default_language` 變更（初始值：`ja`）。

---

## 已知限制

- **首次載入延遲**：transformers / faster-whisper 從 HuggingFace Hub 下載模型（base：~150MB）。首次執行可能需要數分鐘
- **Hailo HEF 模型**：必須透過 GenAI Extension 下載。S2T 擴充功能本身沒有下載功能
- **記憶體**：medium 模型可能在 RPi 5（8GB）上導致記憶體不足錯誤。建議使用 base 模型
- **並行處理**：後端以單例管理。批次處理期間到達的請求共享同一實例
- **輸入格式**：假定 WAV（PCM s16le、mono、16kHz）。影片檔案透過 ffmpeg 自動轉換
- **批次輸入**：目錄 / list_file 方法僅處理已在 DB 中註冊的檔案。未掃描的檔案必須先透過 `start_scan` 註冊

---

## 即時串流轉錄

將網路廣播、RTSP 串流、影片檔案的音訊即時轉為文字，並在 WebUI 上顯示字幕。

### 兩種模式

- **Chunk 模式**（預設）：使用基於 RMS 的靜音偵測進行分塊。支援所有後端（Hailo/CUDA/CPU）。在發話結束後顯示結果。
- **Live 模式**：使用 faster-whisper 的 Silero VAD 進行逐步轉錄。在發話過程中也會顯示中間結果（interim）。需要 ONNX/faster-whisper 後端。

### 支援的輸入來源

- HTTP/HTTPS 串流（網路廣播等）
- RTSP 攝影機
- RTMP 串流

### API 端點

| 端點 | 方法 | 功能 |
|---|---|---|
| `/api/s2t/stream/start` | POST | 開始串流（`source_url`、`language`、`mode`） |
| `/api/s2t/stream/stop` | POST | 停止串流 |
| `/api/s2t/stream/status` | GET | 取得狀態 |
| `/api/s2t/stream/transcript` | GET | 取得全文 |
| `/api/s2t/stream/export/txt` | GET | 匯出文字 |
| `/api/s2t/stream/export/srt` | GET | 匯出 SRT 字幕 |

### SSE 事件

| 事件 | 說明 |
|---|---|
| `s2t.stream_chunk` | 確定文字 |
| `s2t.stream_interim` | 中間文字（僅 Live 模式） |
| `s2t.stream_complete` | 串流完成 |

### MCP 工具

| 工具名稱 | 說明 |
|---|---|
| `s2t_stream_start(source_url, language)` | 開始串流 |
| `s2t_stream_stop()` | 停止串流 |
| `s2t_stream_status()` | 取得狀態 |
| `s2t_stream_transcript()` | 取得全文 |

### 串流設定

在 `extension.json` 中可設定的項目：

| 項目 | 說明 | 預設值 |
|---|---|---|
| `stream_chunk_min_sec` | Chunk 模式最小分塊長度（秒） | — |
| `stream_chunk_max_sec` | Chunk 模式最大分塊長度（秒） | — |
| `stream_silence_threshold` | 靜音偵測的 RMS 閾值 | — |
| `stream_silence_ms` | 靜音判定時間（毫秒） | — |
| `live_interval_sec` | Live 模式的轉錄間隔（秒） | — |

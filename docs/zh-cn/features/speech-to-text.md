# 语音转文字扩展

**状态**：已实现（v3.28.0）
**目标**：`extensions/builtin_speech_to_text/`
**目的**：自动检测后端，转录视频和音频文件

---

## 概述

本扩展从视频和音频文件中提取音频并使用 Whisper 模型进行转录。
它根据可用硬件自动选择最优后端，即使没有 Hailo NPU 也可在 GPU 或 CPU 上运行。

---

## 后端优先级

| 优先级 | 后端 | 库 | 目标硬件 |
|--------|-------------|-----------|-----------------|
| P100 | `hailo` | `hailo_platform.genai` | Hailo-10H NPU |
| P70 | `torch-whisper-rocm` | `torch` (ROCm) + `transformers` | AMD GPU (ROCm/HIP) |
| P50 | `faster-whisper-cuda` | `faster-whisper` (CTranslate2) | NVIDIA GPU (CUDA) |
| P40 | `torch-whisper-cuda` | `torch` (CUDA) + `transformers` | NVIDIA GPU (CUDA) |
| P20 | `torch-whisper-cpu` | `torch` + `transformers` | CPU |
| P50 | `faster-whisper-cpu` | `faster-whisper` (CTranslate2) | CPU |
| P10 | `whisper-cpp` | `pywhispercpp` | CPU（最轻量） |

在 `auto` 模式下，会选择返回 `is_available() == True` 的后端中优先级最高的。

---

## 各环境配置

### 通用要求

- Python 3.11+
- ffmpeg（从视频中提取音频时需要）

### Hailo-10H NPU（Raspberry Pi AI HAT 2）

无需额外包（`hailo_platform` 必须已安装）。
模型（`whisper-base` 等）必须已通过 GenAI 扩展下载。

```bash
# 如果尚未存在，请从 GenAI 扩展 UI 下载模型
```

### NVIDIA GPU (CUDA)

```bash
# 推荐：faster-whisper（轻量，无需 PyTorch）
pip install faster-whisper

# 检测到 CUDA 时自动使用 GPU（float16）
# CUDA 不存在时自动回退到 CPU（int8）
```

### AMD GPU (ROCm)

```bash
# 1. 安装 PyTorch ROCm 版本
#    官方：https://pytorch.org/get-started/locally/
#    示例（ROCm 6.x）：
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2

# 2. 安装 HuggingFace transformers
pip install transformers

# 3. 在配置中设置后端（"auto" 模式下自动检测）
#    在扩展设置中：backend: "rocm" 或 "auto"
```

**ROCm 检测机制**：PyTorch 通过 HIP 将 ROCm 暴露为 CUDA。
当 `torch.version.hip` 不为 `None` 时，系统识别为 ROCm。

**内存要求**（ROCm）：

| 模型 | VRAM 估算 |
|--------|----------|
| tiny | 约 150 MB |
| base | 约 300 MB |
| small | 约 500 MB |
| medium | 约 1.5 GB |

### 仅 CPU

```bash
# 选项 1：faster-whisper（推荐，int8 量化速度快）
pip install faster-whisper

# 选项 2：whisper.cpp（最轻量，无需 PyTorch）
pip install pywhispercpp

# 选项 3：torch + transformers（通用但较重）
pip install torch transformers
```

**CPU 性能估算**（base 模型，1 分钟音频）：

| 后端 | RPi 5 | x86（4 核） |
|---|---|---|
| faster-whisper (int8) | 约 30 秒 | 约 5 秒 |
| whisper.cpp | 约 40 秒 | 约 8 秒 |
| torch (float32) | 约 90 秒 | 约 15 秒 |

---

## 配置

通过扩展设置页面（`/ext/speech-to-text/`）或 config.json 进行配置：

| 项目 | 选项 | 默认值 | 说明 |
|------|--------|-----------|------|
| `backend` | auto / hailo / cuda / rocm / cpu | auto | 推理后端 |
| `model_size` | tiny / base / small / medium | base | Whisper 模型大小 |
| `default_language` | BCP-47 代码（ja、en 等） | ja | 默认语言 |

---

## API 端点

所有端点位于 `/ext/speech-to-text` 前缀下。

### POST `/api/s2t/transcribe`

转录上传的 WAV 音频。

- **Content-Type**：`multipart/form-data`
- **参数**：`audio`（文件）、`language`（可选）
- **响应**：`{ status, text, segments, language, sample_rate, backend }`

### POST `/api/s2t/transcribe-video`

转录在 DB 中注册的视频/音频文件。结果保存为注解。

- **请求体**：`{ file_id: int, language?: string }`
- **响应**：`{ status, text, segments, language, backend }`
- **注解**：`source="s2t"`，键：`transcript`、`transcript_segments`、`transcript_backend`

### POST `/api/s2t/batch-transcribe`

批量转录多个文件（后台运行）。

从以下三种输入方式中选择**一种**（互斥）：

#### 方式 1：文件 ID 列表（旧版）

```json
{
  "file_ids": [123, 456, 789],
  "language": "ja"
}
```

#### 方式 2：目录

自动检测指定目录中的视频/音频文件，仅处理在 DB 中注册的文件。

```json
{
  "directory": "/path/to/videos/",
  "recursive": true,
  "language": "en"
}
```

- `recursive`（默认：`true`）：递归搜索子目录
- 目标扩展名：`.webm`、`.mp4`、`.avi`、`.mov`、`.mkv`、`.m4v`、`.ogv`、`.mp3`、`.wav`、`.ogg`、`.opus`、`.m4a`、`.aac`、`.flac`

#### 方式 3：文本/CSV 列表

指定包含文件路径的文本文件或 CSV。

```json
{
  "list_file": "/path/to/targets.txt",
  "language": "ja"
}
```

**文本文件格式**（`.txt` 等）：
```
# 注释行（以 # 开头的行将被忽略）
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
第一列用作文件路径。以 `#` 开头的行将被跳过。

#### 通用选项

| 参数 | 类型 | 默认值 | 说明 |
|-----------|---|-----------|------|
| `language` | string | 配置值（通常为 `ja`） | 语言代码（见下文） |
| `recursive` | bool | `true` | 仅目录方式：递归搜索子目录 |

#### 限制与约束

- 最大目标文件数：**500**
- 仅处理在 DB 中注册的文件（`files` 表）
- 已删除的文件（`is_deleted=1`）将被排除

#### 响应示例

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

获取已保存的转录结果。为向后兼容，会同时检查 `source="s2t"` 和 `source="hailo:s2t"`。

### GET `/api/s2t/status`

返回后端状态和可用后端列表。

---

## MCP 工具

| 工具名 | 说明 |
|---------|------|
| `s2t_status` | 获取后端状态 |
| `s2t_transcribe_video` | 转录单个视频文件 |
| `s2t_batch_transcribe` | 启动批量转录（file_ids / directory / list_file） |
| `s2t_get_transcript` | 获取已保存的转录 |

### `s2t_batch_transcribe` 参数

| 参数 | 类型 | 必需 | 说明 |
|-----------|---|------|------|
| `file_ids` | list[int] | *1 | 文件 ID 列表（最多 500） |
| `directory` | string | *1 | 目录路径（自动检测视频/音频） |
| `list_file` | string | *1 | 文本/CSV 文件路径 |
| `recursive` | bool | | 仅目录方式。递归搜索子目录（默认 true） |
| `language` | string | | 语言代码。为空则使用配置默认值 |
| `expected_count` | int | | 用于检测 file_ids 截断 |

*1：`file_ids`、`directory`、`list_file` 三者中恰好指定一个（互斥）

---

## 文件结构

```
extensions/builtin_speech_to_text/
  extension.json                      # 清单
  speech_to_text_ext.py               # 入口点（Blueprint）
  s2t_routes.py                       # 单文件 API 路由
  s2t_batch_routes.py                 # 批处理 API 路由
  core_impl/
    base.py                           # S2TBackend 抽象基类
    backend_hailo.py                  # Hailo-10H NPU
    backend_faster_whisper.py         # faster-whisper（CUDA/CPU）
    backend_torch_whisper.py          # PyTorch transformers（ROCm/CUDA/CPU）
    backend_whisper_cpp.py            # whisper.cpp（CPU）
    backend_registry.py               # 自动检测 + 单例管理
  templates/speech_to_text/
    s2t.html                          # UI 页面
mcp_server/
  s2t_tools.py                        # MCP 工具定义
```

---

## 支持的语言代码

Whisper 支持的主要语言代码（BCP-47）：

| 代码 | 语言 | 代码 | 语言 |
|--------|------|--------|------|
| `ja` | 日语 | `en` | 英语 |
| `zh` | 中文 | `ko` | 韩语 |
| `de` | 德语 | `fr` | 法语 |
| `es` | 西班牙语 | `it` | 意大利语 |
| `pt` | 葡萄牙语 | `ru` | 俄语 |
| `ar` | 阿拉伯语 | `hi` | 印地语 |
| `th` | 泰语 | `vi` | 越南语 |
| `nl` | 荷兰语 | `tr` | 土耳其语 |
| `pl` | 波兰语 | `uk` | 乌克兰语 |
| `id` | 印尼语 | `sv` | 瑞典语 |

也可以指定其他 Whisper 支持的语言。空字符串触发自动检测。
默认语言可通过扩展设置 `default_language` 更改（初始值：`ja`）。

---

## 已知限制

- **首次加载延迟**：transformers / faster-whisper 从 HuggingFace Hub 下载模型（base：约 150MB）。首次运行可能需要数分钟
- **Hailo HEF 模型**：必须通过 GenAI 扩展下载。S2T 扩展本身没有下载功能
- **内存**：medium 模型可能在 RPi 5（8GB）上导致内存不足。推荐使用 base 模型
- **并发**：后端以单例方式管理。批处理期间到达的请求共享同一实例
- **输入格式**：假定为 WAV（PCM s16le、单声道、16kHz）。视频文件通过 ffmpeg 自动转换
- **批处理输入**：目录 / list_file 方式仅处理已在 DB 中注册的文件。未扫描的文件需先通过 `start_scan` 注册

---

## 实时流式转录

将网络广播、RTSP 流、视频文件的音频实时转为文字，并在 WebUI 上显示字幕。

### 两种模式

- **Chunk 模式**（默认）：使用基于 RMS 的静音检测进行分块。支持所有后端（Hailo/CUDA/CPU）。在发话结束后显示结果。
- **Live 模式**：使用 faster-whisper 的 Silero VAD 进行逐步转录。在发话过程中也会显示中间结果（interim）。需要 ONNX/faster-whisper 后端。

### 支持的输入源

- HTTP/HTTPS 流（网络广播等）
- RTSP 摄像头
- RTMP 流

### API 端点

| 端点 | 方法 | 功能 |
|---|---|---|
| `/api/s2t/stream/start` | POST | 开始流式转录（`source_url`、`language`、`mode`） |
| `/api/s2t/stream/stop` | POST | 停止流式转录 |
| `/api/s2t/stream/status` | GET | 获取状态 |
| `/api/s2t/stream/transcript` | GET | 获取全文 |
| `/api/s2t/stream/export/txt` | GET | 导出文本 |
| `/api/s2t/stream/export/srt` | GET | 导出 SRT 字幕 |

### SSE 事件

| 事件 | 说明 |
|---|---|
| `s2t.stream_chunk` | 确定文本 |
| `s2t.stream_interim` | 中间文本（仅 Live 模式） |
| `s2t.stream_complete` | 流式转录完成 |

### MCP 工具

| 工具名 | 说明 |
|---|---|
| `s2t_stream_start(source_url, language)` | 开始流式转录 |
| `s2t_stream_stop()` | 停止流式转录 |
| `s2t_stream_status()` | 获取状态 |
| `s2t_stream_transcript()` | 获取全文 |

### 流式转录配置

在 `extension.json` 中可配置的项目：

| 项目 | 说明 | 默认值 |
|---|---|---|
| `stream_chunk_min_sec` | Chunk 模式最小分块长度（秒） | — |
| `stream_chunk_max_sec` | Chunk 模式最大分块长度（秒） | — |
| `stream_silence_threshold` | 静音检测的 RMS 阈值 | — |
| `stream_silence_ms` | 静音判定时间（毫秒） | — |
| `live_interval_sec` | Live 模式的转录间隔（秒） | — |

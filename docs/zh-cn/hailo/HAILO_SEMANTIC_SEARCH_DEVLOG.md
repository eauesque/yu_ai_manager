# Hailo-10H Semantic Search — 开发日志

**项目**：YU AI Manager — Hailo-10H CLIP 语义图片搜索
**目标**：在 Raspberry Pi 5 + AI HAT 2 (Hailo-10H) 上实现基于 CLIP 的自然语言图片搜索
**开始日期**：2026-03-01
**状态**：Phase 1-8 完成、Phase 9-12（VLM 字幕联动、视频 S2T、LLM 多轮对话、OpenAI 兼容 API）完成

---

## 为什么这个项目很重要

Hailo-10H (AI HAT 2) 是 2025 年底发布的较新的边缘 AI 加速器，
安装在 Raspberry Pi 5 的 M.2 插槽上使用。拥有 40 TOPS 的推理性能，但
**实际应用程序中的使用案例几乎尚未公开**。

本项目使用 Hailo-10H 对 20 万张规模的图片库进行
语义搜索（以自然语言搜索图片），可能是首个实用软件。

---

## Phase 1：可行性确认 (2026-03-01)

### 环境信息

| 项目 | 值 |
|------|-----|
| 硬件 | Raspberry Pi 5 (8GB) + AI HAT 2 (Hailo-10H) |
| OS | Raspberry Pi OS Trixie (Linux 6.12.62+rpt-rpi-2712) |
| Python | 3.13.5 |
| HailoRT 驱动程序 | 5.2.0 (hailort-pcie-driver) |
| HailoRT 库 | 5.2.0 (hailort deb) |
| HailoRT Python | 5.2.0 (**从源码构建**) |

### Step 1-1：设备识别 — OK

```bash
$ hailortcli fw-control identify
Firmware Version: 5.2.0 (release,app)
Device Architecture: HAILO10H
```

设备顺利被识别。PCIe 连接与驱动程序加载均正常。

### Step 1-2：HEF 下载 — OK

可从 Hailo Model Zoo v5.2.0 的 S3 存储桶直接下载（无需认证）。

```
~/hailo_models/clip_vit_b_16_image_encoder.hef  (76 MB)
~/hailo_models/clip_vit_b_16_text_encoder.hef   (77 MB)
```

URL 模式：
```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

### Step 1-3：Python 绑定 — 需从源码构建

#### 问题：包版本不一致

Raspberry Pi OS 的包仓库中存在以下 2 个系统：

| 包系统 | 版本 | 备注 |
|---------------|-----------|------|
| `hailort` + `hailort-pcie-driver` | 5.2.0 | Hailo 官方 deb。不含 Python 绑定 |
| `h10-hailort` + `python3-h10-hailort` | 5.1.1 | Raspberry Pi 团队提供。含 Python |

**问题**：两个系统设有 `Conflicts`，无法共存。安装 `h10-hailort` (5.1.1) 后
驱动程序也会变成 5.1.1，但 hailo-ollama 需要 5.2.0。

#### 解决方案：从源码构建 hailort 5.2.0 的 Python wheel

**PyPI 上没有 wheel**。Hailo Developer Zone 的下载页面上
**也不存在 aarch64 版 wheel**（仅有 x86_64）。

从 GitHub 仓库以源码构建解决：

```bash
git clone --depth 1 --branch v5.2.0 https://github.com/hailo-ai/hailort.git ~/hailort

# ビルド依存
sudo apt install -y swig build-essential
pip install pybind11 setuptools wheel

# ビルド (約2分)
cd ~/hailort/hailort/libhailort/bindings/python/platform
HAILORT_INCLUDE_DIR=/usr/include/hailo \
LIBHAILORT_PATH=/usr/lib/libhailort.so.5.2.0 \
PYBIND11_PYTHON_VERSION=3.13 \
python3 setup.py bdist_wheel --plat-name linux_aarch64

# インストール
pip install dist/hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

**注意事项**：
- `--plat-name linux_aarch64` 为必须。省略时 `LIBHAILORT_PATH` 的目录名称解析会
  发生 `ValueError: not enough values to unpack`（setup.py 第 163 行的 bug）
- `hailort` deb（C 库）需预先安装
- `h10-hailort` 和 `hailort` 设有 `Conflicts` 无法共存，
  需先删除 `h10-hailort` 再安装 `hailort` 5.2.0

### Step 1-4：推理测试 — 成功（API 有变更）

#### 重大发现：Hailo-10H 不支持旧版 VStreams API

规格书中记载的 `InferVStreams` + `ConfigureParams.create_from_hef()` 代码
**在 Hailo-10H 上无法运行**。`VDevice.configure()` 会返回 `HAILO_NOT_IMPLEMENTED (error 7)`。

这是 **Hailo-8/8L 与 Hailo-10H 之间根本性的 API 差异**，
官方文档中也未明确记载的重要事实。

#### 正确的 API：InferModel

Hailo-10H 使用 `VDevice.create_infer_model()`：

```python
from hailo_platform import VDevice
import numpy as np

hef_path = "~/.hailo_models/clip_vit_b_16_image_encoder.hef"

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(hef_path)

    # inputs/outputs 是属性（不是可调用的）
    inp_info = infer_model.inputs[0]   # NOT inputs()
    out_info = infer_model.outputs[0]

    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # 输入：uint8 图片
    dummy = np.random.randint(0, 255, inp_info.shape, dtype=np.uint8)
    bindings.input().set_buffer(dummy)

    # 输出：明确分配 uint8 缓冲区
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    configured.run([bindings], timeout=10000)

    vec = output_buf.flatten()  # (512,) uint8
```

#### 卡住的问题与解决方案

| 问题 | 错误 | 解决 |
|------|--------|------|
| `infer_model.inputs()` 出现 TypeError | `'list' object is not callable` | 是属性所以用 `inputs[0]`（不加括号）|
| 输出缓冲区未设置 | `not configured as view` | 用 `bindings.output().set_buffer(buf)` 明确分配 |
| 以 float32 分配输出缓冲区 | `buffer size 2048 != expected 512` | 必须用 **uint8** 分配（512 bytes）。float32 会变成 2048 bytes |
| VDevice 结束时错误 | `Lost communication with server` | VDevice 清理顺序的问题。**对推理结果无影响** |

### 推理性能

| 项目 | 值 |
|------|-----|
| 模型 | CLIP ViT-B/16 Image Encoder |
| 输入 | (224, 224, 3) uint8 |
| 输出 | (1, 1, 512) uint8 (已量化) |
| 推理时间 | **~20 ms** |
| 理论吞吐量 | **~50 images/sec** |

20 万张的索引构建：仅推理约 67 分钟。加上预处理也可在数小时内完成。

### Phase 1 判定

| 基准 | 结果 |
|------|------|
| 512 维向量输出 | **OK**（uint8 量化，需反量化）|
| 推理速度 | **优秀**（20ms/image）|
| API 兼容性 | 使用 InferModel API（规格书的 VStreams API 不可用）|
| 判定 | **进入 Phase 2** |

### 交接给下一阶段的事项

1. **反量化**：需将 uint8 输出转换为 float32。
   HEF 中应包含量化参数 (scale/zero_point)。
   `hailo_platform.pyhailort._pyhailort.dequantize_output_buffer` 可能可用。
2. **文本编码器**：HEF 存在但尚未测试。需确认是否可用相同的 InferModel API。
   按照规格书的方针以 CPU (sentence-transformers) 实现可能更安全。
3. **与 hailo-ollama 共存**：VDevice 会排他性地使用设备。
   构建索引时需停止 hailo-ollama。
4. **VDevice 清理**：结束时的错误消息无害，
   但在长时间运行的服务器进程中需注意资源泄漏。

---

## Phase 2：DB 结构扩展 (2026-03-01)

### 实现内容

作为 Migration 25 新增 `file_vectors` 数据表。

```sql
CREATE TABLE file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip_vit_b_16',
    vector      BLOB NOT NULL,        -- float32 numpy array tobytes() (512*4=2048 bytes)
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX idx_file_vectors_model ON file_vectors(model);
```

**设计决策**：
- `vector` 存储反量化后的 float32 BLOB。若以 uint8 存储会导致精度劣化
- `file_id` 为 PRIMARY KEY（1 个文件 1 个向量）。未来支持多模型时需改为 UNIQUE(file_id, model)
- `ON DELETE CASCADE` 在 files 删除时自动删除

**测试**：在内存 DB 中应用 migration → 确认数据表/索引存在 → OK

### 文件

- `core/schema_core/schema_migrate_steps_25.py`（新增）
- `core/schema_core/schema_migrate.py`（import + `if current_version < 25` 新增）
- `core/schema_core/schema_constants.py`（`CURRENT_SCHEMA_VERSION = 25`）
- `core/hailo_clip_core/vector_store.py`（新增 - DB 向量 CRUD）*(现已移至 `extensions/builtin_hailo_semantic_search/core_impl/`)*

---

## Phase 3：Hailo 推理核心 (2026-03-01)

### 实现内容

新建 `core/hailo_clip_core/` 包 *(现已移至 `extensions/builtin_hailo_semantic_search/core_impl/`)*：

| 文件 | 职责 |
|---------|------|
| `hailo_inference.py` | HailoClipEncoder 单例模式。InferModel API 包装器 |
| `image_preprocess.py` | 以 cv2 进行 224x224 缩放 + BGR→RGB 转换 |
| `dequantize.py` | uint8→float32 反量化 + L2 归一化 + quant_params 提取 |
| `text_encoder.py` | CPU CLIP 文本编码器 (`openai/clip-vit-base-patch16`) |

**设计决策**：
- 图片预处理保持 uint8 直接传给 Hailo（HEF 内部会进行归一化）
- 文本编码器使用 `transformers` 的 CLIPModel（而非 `sentence-transformers`）。
  原因：`openai/clip-vit-base-patch16` 与 Hailo HEF 的 CLIP ViT-B/16 为相同模型，
  向量空间一致
- 反量化参数尝试从 `infer_model.outputs[0].quant_infos[0]` 获取，
  失败时回退为 scale=1.0, zero_point=0.0

**依赖包**：`opencv-python-headless`, `numpy`（必须），`transformers`, `torch`（文本搜索用）

---

## Phase 4：索引器 + Extension (2026-03-01)

### 实现内容

| 文件 | 职责 |
|---------|------|
| `core/hailo_clip_core/indexer.py` *(现已移至 `extensions/builtin_clip_search/core_impl/`)* | 在后台线程中批量构建索引 |
| `core/hailo_clip_core/event_handler.py` *(现已移至 `extensions/builtin_clip_search/core_impl/`)* | scan.complete 事件触发自动索引 |
| `extensions/builtin_hailo_semantic_search/extension.json` | Extension 清单 |
| `extensions/builtin_hailo_semantic_search/hailo_semantic_search.py` | Blueprint 5 个 API |

**API 端点**：
- `GET /ext/hailo-semantic/api/status` — 设备与索引状态
- `POST /ext/hailo-semantic/api/index/start` — 开始构建索引
- `GET /ext/hailo-semantic/api/index/status` — 进度
- `POST /ext/hailo-semantic/api/index/stop` — 中断
- `GET /ext/hailo-semantic/api/search` — 语义搜索
- `POST /ext/hailo-semantic/api/index/clear` — 清除索引

**事件**：在 event_bus 中新增 `semantic_index.start/progress/complete`

---

## Phase 5：语义搜索引擎 (2026-03-01)

### 实现内容

`core/hailo_clip_core/search.py` *(现已移至 `extensions/builtin_clip_search/core_impl/search.py`)* — 带内存缓存的余弦相似度搜索

**算法**：
1. 从 DB 一次加载所有向量 → 内存缓存
2. 预先对向量进行 L2 归一化
3. 查询文本 → CLIP 文本编码器 → 512 维向量
4. 矩阵乘法（dot product）批量计算余弦相似度
5. 筛选 threshold 以上 → 排序 → 返回结果

**内存估计**：200K x 512 x 4 bytes = ~400 MB（Pi5 8GB RAM 可承受）

**响应格式**：
```json
{
    "status": "ok",
    "total": 25,
    "results": [{"file_id": 123, "score": 0.82, "path": "..."}],
    "query": "blue sky",
    "indexed_count": 200000,
    "threshold": 0.2,
    "timing": {"encode_ms": 150.3, "search_ms": 12.5}
}
```

---

## Phase 6：UI 集成 (2026-03-01)

### 搜索页面

- 在搜索栏旁新增语义搜索切换按钮（脑图标 `regex-pill` 样式）
- 仅在 Hailo 可用且索引构建完成时显示
- 切换 ON 时：拦截搜索表单提交 → 语义搜索 API → 在现有网格中显示结果
- 将占位文字替换为英文示例

### Tools 页面

- 在 Search & Analysis 选项卡中新增语义搜索区块
- 显示设备状态/索引状况
- 批量大小滑块 + 自动索引复选框
- Build Index / Stop / Clear 按钮 + 进度条（2 秒轮询）

---

## 技术笔记

### Hailo-10H vs Hailo-8/8L 的主要差异（开发者视角）

| 项目 | Hailo-8/8L | Hailo-10H |
|------|-----------|-----------|
| VStreams API | 支持 | **不支持**（NOT_IMPLEMENTED）|
| InferModel API | 支持 | 支持 |
| ConfigureParams | create_from_hef(hef, interface) | 不需要（create_infer_model 替代）|
| 输出格式 | 可选 float32 或 uint8 | uint8 固定（需反量化）|
| Python 包 | PyPI 有 wheel | **没有**（需从源码构建）|
| APT 包 | `hailort` 统合 | `h10-hailort` 另一系统（仅 5.1.1）|

### 已构建 wheel 的保管位置

```
~/hailort/hailort/libhailort/bindings/python/platform/dist/
  hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

部署到其他 Pi5 环境时可复制此 wheel 进行安装
（但需要 libhailort.so.5.2.0 和 hailort-pcie-driver 5.2.0）。

---

## Phase 2-6 实现后的错误修复日志 (2026-03-01)

### 1. 文本编码器的 `get_text_features` 兼容性问题

**问题**：`CLIPModel.get_text_features(**inputs)` 在新版 transformers 中
不再返回 `torch.Tensor`，而是返回 `BaseModelOutputWithPooling` 对象。
因此调用 `.squeeze()` 时发生 `AttributeError`，语义搜索显示 `Search failed` 错误。

**症状**：`curl /ext/hailo-semantic/api/search?q=girl` → `{"message":"Search failed","status":"error"}`

**原因**：`_model.get_text_features()` 的返回值取决于 transformers 版本。
新版本返回整个模型输出对象，需自行取出 `.pooler_output` 等。

**修复**：在 `text_encoder.py` 中改为明确以 `text_model()` → `text_projection()` 两阶段处理：

```python
# Before (broken)
text_features = _model.get_text_features(**inputs)
vec = text_features.squeeze().numpy()

# After (fixed)
text_out = _model.text_model(**inputs)
text_features = _model.text_projection(text_out.pooler_output)
vec = text_features.squeeze().numpy()
```

**性能**：
- 首次查询（含模型加载）：~6 秒
- 第二次以后：~100-170ms（仅 CPU 推理）
- 向量搜索：<1ms（51 条，内存缓存）

### 2. 索引构建时的无限重试循环

**问题**：未将解码失败的文件（非图片文件、损坏文件等）追踪为 `failed_ids`，
`get_unindexed_file_ids()` 每次都返回相同的失败文件，错误计数超过 300 万。

**修复**：在 `indexer.py` 中新增 `failed_ids: set`。记录失败的 file_id，下次批量时排除。

### 3. 压缩包内的图片读取失败

**问题**：`cv2.imread('test.7z!image.png')` 无法理解压缩包成员路径。

**修复**：在 `image_preprocess.py` 中使用 `is_archive_member()` 检测压缩包路径，
切换为 `read_bytes_from_zip` / `read_bytes_from_7z` + `cv2.imdecode()` 模式。

### 4. SSE 实时进度更新

**问题**：2 秒轮询的进度更新不流畅，体验差。

**修复**：切换为 `EventSource` SSE 连接。通过 `semantic_index.progress` 事件实时更新。
`visibilitychange` 在标签页隐藏时断开 SSE，恢复时重新连接。

---

## Phase 7：YOLO 目标检测 (2026-03-02)

### 概述

继 CLIP 语义搜索之后，在同一台 Hailo-10H 上实现 YOLO 目标检测。
对图片与视频进行 80 类别 COCO 目标检测，并将结果存储至 `file_annotations` 数据表。

### 架构设计

#### VDevice 共享问题

Hailo-10H 单一进程只能使用一个 VDevice，InferModel 也是排他的。
CLIP 和 YOLO 无法同时运行。

**解决方案**：新建 `core/hailo_device_core/device_manager.py`。
- `acquire_device(owner, hef_path)` — 若其他 owner 持有中则自动释放并切换
- 相同 owner + 相同 HEF 时复用（避免重新初始化）
- 以 `threading.Lock` 确保线程安全
- 重构 CLIP 的 `hailo_inference.py`，委托给 device_manager

#### YOLO 输出张量的处理

CLIP 只有一个输出张量，但 YOLO 有多个输出张量（对应各 stride 的 head）。
`device_manager` 收集所有输出的 quantization parameters 并返回。

#### 后处理流水线

YOLO 后处理包含以下步骤：
1. uint8 → float32 反量化（使用各 output 的 scale/zero_point）
2. grid cell → 像素坐标解码（sigmoid + grid offset + stride）
3. confidence 过滤
4. 各类别的 NMS（pure numpy）
5. letterbox 坐标 → 原图的归一化坐标 (0-1) 转换

#### 视频支持

以 ffmpeg 提取帧 → 各帧独立检测 → 按类别汇总。
保持各类别的最大 confidence + 出现帧数。

### 新模块结构

| 模块 | 职责 |
|---|---|
| `core/hailo_device_core/device_manager.py` | 共享 VDevice 生命周期管理 |
| `core/hailo_yolo_core/hailo_yolo_inference.py` | YOLODetector 单例模式 |
| `core/hailo_yolo_core/yolo_postprocess.py` | NMS、box decode、dequantize |
| `core/hailo_yolo_core/yolo_labels.py` | COCO 80 类别标签 |
| `core/hailo_yolo_core/yolo_preprocess.py` | 640x640 letterbox 缩放 |
| `core/hailo_yolo_core/yolo_video.py` | 视频帧提取 + 汇总 |
| `core/hailo_yolo_core/yolo_indexer.py` | 后台批量检测 |
| `core/hailo_yolo_core/model_download.py` | HEF 下载 |
| `core/hailo_yolo_core/event_handler.py` | scan.complete 处理器 |
| `extensions/builtin_hailo_yolo_detect/` | Extension + Blueprint API + UI |

### 技术笔记

- **多输出张量**：YOLO HEF 有多个输出张量（对应各 stride 的 head）。
  需遍历 `infer_model.outputs` 收集所有的 shape/quant_params
- **输出缓冲区**：为各输出张量单独分配 uint8 缓冲区，
  以 `bindings.output(out.name).set_buffer(buf)` 指定名称绑定
- **张量布局**：形状通常为 `(1, H, W, C)`。C 中包含 bbox (4) + class scores (80)
- **HEF 下载**：从 Hailo Model Zoo v5.2.0 直接下载。不设置 User-Agent 会
  被 Cloudflare 阻挡，因此设置 `_USER_AGENT`
- **检测结果的存储**：以 JSON 数组存储在 `file_annotations` 数据表的 `source='hailo:<model>'`, `key='detections'` 中。
  直接复用现有的 annotation CRUD API

---

## Phase 8：GenAI (LLM / VLM / Speech2Text) 集成 (2026-03-02)

### 目标

将 Hailo-10H 的 `hailo_platform.genai` 模块（LLM、VLM、Speech2Text）
集成到 device_manager，从 WebUI 使用文本生成、图片理解、语音转文字。

### device_manager 扩展

- **问题**：现有的 device_manager 仅支持 InferModel API（CLIP/YOLO）。
  GenAI 类不使用 InferModel，而是直接接收 VDevice 的另一种模式
- **解决方案**：以 `_mode` 变量（`"infer"` | `"genai"`）区分模式。
  新增 `acquire_genai(owner, model_path, genai_factory)`，
  以 factory 模式生成 LLM/VLM/S2T 的实例
- **释放处理的差异**：
  - InferModel：`del configured` → `del infer_model` → `del vdevice`
  - GenAI：`instance.release()` → `vdevice.release()`（明确的 release 方法）

### GenAI API 的发现事项

- **消息格式**：OpenAI 兼容的 role/content 结构。content 为数组，`{"type": "text", "text": "..."}` 格式
- **VLM 图片输入**：336x336 RGB uint8 numpy 数组。以 `frames=[image]` 列表传递。
  在提示中放置 `{"type": "image"}` 占位符
- **S2T 输入**：little-endian float32 (`<f4`)，单声道，16kHz。int16→float32 归一化为必须
- **S2T 段落**：`generate_all_segments()` 返回 `SegmentInfo` 对象的列表。
  具有 `.text`, `.start`, `.end` 属性
- **上下文管理**：LLM/VLM 以 `get_context_usage_size()`, `max_context_capacity()`,
  `clear_context()` 管理上下文窗口
- **流式输出**：`generate()` 返回迭代器，逐 token yield

### 模型 HEF 下载 URL

- 模式：`https://dev-public.hailo.ai/v{hailort_version}/blob/{ModelName}.hef`
- HailoRT 5.2.0 → `v5.2.0`
- 模型名称为 CamelCase（例：`Qwen2.5-1.5B-Instruct.hef`, `Whisper-Base.hef`）
- 可在 `hailo-apps-infra` 的 `download_resources.py` 的 `gen-ai-mz` source type 中确认

### 新增文件

| 文件 | 说明 |
|----------|------|
| `core/hailo_genai_core/__init__.py` | 包 init |
| `core/hailo_genai_core/genai_types.py` | GenAIModelType enum + GenAIModelInfo dataclass |
| `core/hailo_genai_core/model_download.py` | 7 个模型 HEF 下载管理 |
| `core/hailo_genai_core/llm_inference.py` | HailoLLM 包装器（singleton, streaming）|
| `core/hailo_genai_core/vlm_inference.py` | HailoVLM 包装器（singleton, 图片预处理）|
| `core/hailo_genai_core/s2t_inference.py` | HailoS2T 包装器（singleton, 段落支持）|
| `extensions/builtin_hailo_genai/extension.json` | Extension 清单 |
| `extensions/builtin_hailo_genai/hailo_genai_ext.py` | Blueprint 8 个 API（SSE streaming）|
| `extensions/.../templates/hailo_genai/_genai_ui.html` | Tools 页面 UI（4 面板）|

### 技术笔记

- **VDevice.create_params()**：GenAI 模式以 `VDevice.create_params()` 创建参数，
  以 `VDevice(params)` 实例化。与 InferModel 模式的 `VDevice()`（无参数）不同
- **SSE 流式输出**：Flask 的 `Response(generator(), mimetype='text/event-stream')`
  逐 token 发送 `data: {"token": "..."}\n\n`。完成时发送 `data: {"done": true}\n\n`
- **VLM 的 FormData 发送**：因需同时发送图片文件 + 文本提示，
  VLM API 使用 `multipart/form-data` 而非 JSON
- **S2T 的 WAV 读取**：服务器端以 `wave` 模块 + `io.BytesIO`
  从上传的 WAV 字节流直接读取

---

## Phase 9：语义搜索 + VLM 字幕联动 (2026-03-03)

### 目标

对 CLIP 搜索结果的图片以 VLM（Qwen2-VL）批量生成字幕，
存储到 `file_annotations`。

### 实现

- **`core/hailo_clip_core/caption_runner.py`** *(现已移至 `extensions/builtin_hailo_semantic_search/core_impl/caption_runner.py`)*（~150 行）：在后台线程中批量执行 VLM 字幕生成。沿用 `indexer.py` 的 `_state_lock` + `_stop_requested` + `_progress` 模式。SSE 事件 `vlm_caption.start/progress/complete`
- **Blueprint 扩展**：在 `hailo_semantic_search.py` 中新增 `/api/caption/start`, `/api/caption/status`, `/api/caption/stop` 共 3 个端点
- **UI**：在 Tools 页面的 Semantic Search 区块中新增「VLM Caption Generation」面板。提示输入、SSE 进度条、搜索结果 file_ids 自动联动

### VDevice 互斥控制

- 以 `acquire_genai("vlm", ...)` 获取 VLM。若 CLIP 索引器正在运行，device_manager 的现有行为会自动释放
- 字幕完成后 VLM 持续持有设备，CLIP 索引的重启需要卸载模型

### Annotation 存储规范

- `source="hailo:vlm"`, `key="caption"`, `value=<字幕文本>`

---

## Phase 10：视频音频转文字 — S2T 流水线 (2026-03-03)

### 目标

从视频文件以 ffmpeg 提取音频 → 以 Whisper (S2T) 转文字 → 存储到 `file_annotations`。

### 实现

- **`core/files_core/video_audio.py`**（~80 行）：`extract_audio_wav()` 以 ffmpeg 提取音频（mono PCM s16le 16kHz）。从视频的 duration 动态计算超时时间（最大 120 秒）。`check_ffmpeg()` 从 `media_video.py` 复用
- **Blueprint 扩展**：在 `hailo_genai_ext.py` 中新增 3 个端点：
  - `POST /api/s2t/transcribe-video`：单个视频的转文字（file_id, language）
  - `POST /api/s2t/batch-transcribe`：多个视频的批量转文字（file_ids, language），后台线程 + SSE 进度（`video_s2t.*`）
  - `GET /api/s2t/transcript/<file_id>`：获取已存储的转文字
- **UI**：在 S2T 面板中新增「Video Transcription」子区块。file_id 输入、语言选择（ja/en）、获取已存储按钮

### Annotation 存储规范

- `source="hailo:s2t"`, `key="transcript"`, `value=<全文文本>`
- `source="hailo:s2t"`, `key="transcript_segments"`, `value=<JSON [{text, start, end}, ...]>`

### 注意事项

- 临时 WAV 以 `tempfile.NamedTemporaryFile` 创建，在 finally 中必定删除
- S2T 与 LLM/VLM 设备互斥（无法同时使用）

---

## Phase 11：LLM 多轮对话 UI 改善 (2026-03-03)

### 目标

将单次提示扩展为支持对话历史。上下文延续、重置、气泡型 UI。

### 实现

- **API 修改**：`api_llm_generate()` 可接收 `messages` 数组。向后兼容：仅有 `prompt` 时按照既有方式转换为 system + user 消息。`generate_stream()` 已支持多轮对话（通过 `_normalise_prompt()`）
- **气泡型聊天 UI**：`hg-chat-container` + `hg-bubble`（user=右对齐紫色，AI=左对齐灰色）。CSS 类：`hg-bubble-user`, `hg-bubble-ai`, `hg-bubble-label`
- **对话历史管理**：JS 端以 `_chatHistory = []` 数组累积 `{role, content}`。API 发送时传 `messages: [systemMsg, ..._chatHistory]`。`hgLlmClear()` 重置数组 + 清除 HailoRT 上下文
- **流式输出**：先将 AI 气泡插入 DOM，SSE token 逐次追加

### 错误修复：多轮对话的 system role 错误 (2026-03-03)

通过 MCP 调试查询 + hailort 日志发现。第 2 轮以后的 `generate()` 调用发生以下错误：

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_OPERATION(6)
```

**原因**：UI 模板每次都以 `[systemMsg].concat(_chatHistory)` 将 system role 放在开头发送。HailoRT 的 LLM API 在上下文存在的状态下（第 2 轮以后）不接受 system role。

**修复**：
1. 在 `llm_inference.py` 中新增 `_prepare_prompt()` 方法：`get_context_usage_size() > 0` 时自动排除 system role 消息
2. UI 模板（`_genai_ui.html`）：仅在 `_chatHistory.length <= 1`（仅首次用户消息）时附加 system

**技术笔记**：HailoRT 的限制是 `LLM.generate()` 仅在首次调用时处理 system role。这与 OpenAI API 的行为不同，在实现多轮对话时需要注意

---

## WD-Tagger VLM x Hailo-10H 实机测试 (2026-03-03)

### 测试环境
- Raspberry Pi 5 + Hailo AI HAT 2 (Hailo-10H)
- HailoRT FW 5.2.0, hailo_platform Python 5.2.0
- hailo-ollama v0.5.1（构建版）
- Qwen2-VL-2B-Instruct.hef (3.0 GB)

### 重要发现：hailo-ollama 不支持 VLM

hailo-ollama 的官方文档 (USAGE.rst) 中明确记载：
> "The Hailo-Ollama API is currently limited to language models (LLMs) and cannot be used for VLMs."

MODELS 表格中 `Qwen2-VL-2B-Instruct` 的 Inference API 栏位也仅有 "C++, Python"，不含 "Hailo-Ollama"。

`/hailo/v1/list` 返回的模型列表：
```
deepseek_r1:1.5b, llama3.2:1b, qwen2.5-coder:1.5b, qwen2.5:1.5b, qwen2:1.5b
```
不含 `qwen2-vl`。

### hailo-ollama 测试结果

**config 的注意事项**：构建版二进制文件使用 `NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE` 宏，config JSON 中 `limits` 键为必须。官方 config 模板中未包含，需新增以下内容：
```json
"limits": {"max_in_flight": 4, "max_queue": 10, "retry_after_sec": 1}
```

- **LLM 文本生成 (qwen2.5:1.5b)**：OpenAI + Ollama native 两者 OK，6.5 TPS
- **OpenAI API vision 请求**：500 错误 (`Node is NOT a STRING`)
- **Ollama native API + images**：被接受但 LLM 无法处理图片
- **VlmWdTaggerEngine 回退**：OpenAI 500 → Ollama native 自动切换 OK
- **response_format: json_object**：被接受但 JSON 输出不会被强制

### Hailo Python SDK VLM 直接测试结果

VLM 需在消息格式中包含 `{"type": "image"}`：
```python
messages = [
    {"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": "Tag this image."}
    ]}
]
vlm.generate_all(messages, frames=[frame_336x336_rgb_uint8])
```

- **模型加载**：33 秒（首次冷启动。与公称 6.2 秒的差距主要由磁盘 I/O 支配）
- **推理速度**：~5.1 TPS（128 token / 20 秒）。与公称 6.73 TPS 的差距因包含 TTFT
- **图片识别精度**：正确理解图片内容（准确描述「雪景中牵手的两位女性」）
- **JSON 输出质量**：低。2B 模型的结构化 JSON 生成精度不稳定（逗号缺失、markdown 代码围栏混入）

### 发现的 Bug

1. **`engines_hailo_vlm.py` 提示格式**：对 VLM 发送了纯文本消息 → 修改为包含 `{"type": "image"}` 的列表格式
2. **`vlm_inference.py` frames 参数**：VLM 的 `generate_all()` 需要 `frames`，但声明为 Optional → 改为必须

### 技术笔记

- **VDevice 排他限制**：hailo-ollama 启动中无法获取 `hailo_platform.VDevice()`。VLM 直接推理时需停止 hailo-ollama
- **VLM.generate_all() frames 为必须**：纯文本推理会产生 `HAILO_INVALID_OPERATION` 错误。LLM 和 VLM 的 API 前提条件不同
- **Qwen2-VL 的 prompt template**：以 Jinja2 模板插入 `<|vision_start|><|image_pad|><|vision_end|>`。在消息格式中包含 `{"type": "image"}` 后 SDK 会自动处理

---

## Phase 12：OpenAI 兼容 API + 设备切换 Bug 修复 (2026-03-14)

### 目标

1. 提供 OpenAI 兼容 API，让 OpenAI SDK / LiteLLM / Continue.dev / Open WebUI 等外部工具可直接使用 Hailo GenAI
2. 修复 Quart async 的不完善之处
3. MCP 工具的 SSE 端点支持

### 实现：OpenAI 兼容 API (`hailo_openai_routes.py`)

新建 `extensions/builtin_hailo_genai/hailo_openai_routes.py`。实现以下 4 个端点：

| 端点 | 功能 | 对应模型 |
|---|---|---|
| `GET /v1/models` | 可用模型一览 | 全模型 + CLIP |
| `POST /v1/chat/completions` | 文本/图片聊天（支持 stream）| LLM + VLM |
| `POST /v1/audio/transcriptions` | 语音转文字 | Whisper |
| `POST /v1/embeddings` | 文本→CLIP 向量 | CLIP ViT-B/16 |

#### 设计上的决策

- **Vision 支持**：直接接受 OpenAI Vision API 格式（`image_url` with `data:` base64）。另外支持 `file_id:123` 格式直接引用 YU 图库的图片
- **HTTP URL 不支持**：为防止 SSRF，`image_url` 不接受 `http://` / `https://`
- **模型别名**：`whisper-1` → `whisper-base`、`clip` → `clip-vit-b-16` 等 OpenAI 兼容别名
- **非 WAV 音频**：以 ffmpeg 自动转换（16kHz mono PCM16）
- **Usage 字段**：Hailo SDK 不返回 token 数，因此固定为 `0`。未来有改善空间

#### MCP 工具

- `hailo_genai_openai_info`：返回端点一览与使用方法的辅助工具（不调用 API，在本地生成）

### 修复：Quart async SSE 生成器

所有路由文件的 SSE 生成器均有 async 支持的不完善：

| 文件 | 问题 | 修复 |
|---|---|---|
| `hailo_llm_routes.py` | `def generate_sse()` 为同步函数 | 改为 `async def`，`get_llm()` 和 `next(it)` 以 `asyncio.to_thread` 执行 |
| `hailo_vlm_routes.py` | 同上 + DB 引用为同步 | 同上 + 以 `run_db_sync` 包装 |
| `hailo_s2t_routes.py` | transcribe 为同步执行 + DB 为同步 | 以 `asyncio.to_thread` + `run_db_sync` 包装 |
| `hailo_chat_routes.py` | 同上（LLM/VLM 两者）| 将所有阻塞调用改为 async 化 |

Quart (ASGI) 中若生成器不是 `async def`，会阻塞事件循环，SSE 传送中其他请求无法处理。

### 发现的 Bug：设备切换时的 Singleton 不一致

#### 症状

VLM 使用后调用 LLM 时发生 `'NoneType' object has no attribute 'get_context_usage_size'` 错误。反方向（LLM→VLM→LLM）也必定发生。

#### 原因分析

Hailo-10H 只能保持一个 VDevice，因此由 `device_manager.py` 进行排他管理。模型切换时的流程：

1. VLM 的 `get_vlm()` → `acquire_genai("vlm", ...)` → 内部 `_release_internal()` 释放 LLM 的 VDevice
2. VLM 使用完成
3. LLM 的 `get_llm()` → `_instance` 仍存在 + `model_name` 也一致 → **复用现有实例**
4. `_instance._llm` 背后的 VDevice 已被释放 → `get_context_usage_size()` 在 `None` 上被调用而崩溃

问题的根本：即使 Singleton 的 `_instance` 仍存在，其内部的 Hailo SDK 对象 (`self._llm`) 所指向的 VDevice 已被 `device_manager` 的 `_release_internal()` 调用 `.release()`。Python 的引用计数下 `_instance._llm` 仍然存活，但 Hailo SDK 原生端的资源已被释放。

#### 修复

在 `get_llm()` / `get_vlm()` / `get_s2t()` 的 Singleton 复用检查中新增 `device_manager.get_current_owner()` 确认：

```python
def get_llm(model_name="qwen2.5-1.5b-chat"):
    global _instance
    with _lock:
        if _instance is not None and _instance.model_name == model_name:
            from core.hailo_device_core.device_manager import get_current_owner
            if get_current_owner() == "llm":
                return _instance  # デバイスを保持中 → 再利用 OK
            # デバイスが他のモデルに奪われている → 再作成
            _instance = None
        ...
```

对 LLM / VLM / S2T 三个 Singleton 全部应用相同修复。

#### 验证

LLM → VLM → LLM → VLM 连续 4 次切换全部正常运行已确认。

### 其他修复

- **MCP `post_sse` 方法**：在 `mcp_server/client.py` 中新增消费 SSE 流并以 JSON 返回最终文本的 `post_sse()` 方法。`hailo_llm_generate` 和 `hailo_vlm_generate` 工具使用此方法
- **MCP `yolo_search` 参数**：`labels` → `class_name` 重命名（与 API 端参数名称一致）
- **Circuit Breaker**：新增 `_READ_SUFFIXES`（`_status`, `_info`, `_list`, `_stats`）。half_open 状态下 `hailo_genai_status` 等状态系工具得以被允许
- **Semantic Search async**：以 `run_db_sync` 包装 `get_encoder_info()` 和 `semantic_search()`（防止 Quart 事件循环阻塞）

### 技术笔记

- **VDevice 的排他限制在 SDK 层级**：即使 Python 端持有对象的引用，Hailo SDK 原生端的资源被释放后就无法使用。使用 Singleton 模式时，需另外检查原生资源的有效性
- **Quart + 同步生成器**：将同步生成器传给 Quart 的 SSE 响应虽然可运行，但 `yield` 之间的处理会阻塞事件循环。如 Hailo 推理等重度处理，务必以 `asyncio.to_thread` 移到其他线程
- **OpenAI Vision API 与 VLM 的联动**：OpenAI Vision API 以 `image_url` 字段接收图片，但 Hailo VLM 以 `frames`（numpy array）接收。在转换层进行 base64 解码 → OpenCV 解码 → 336x336 RGB 缩放

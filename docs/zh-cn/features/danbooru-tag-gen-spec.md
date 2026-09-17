# Danbooru 自动标签 — 实现规格

**状态**：已实现（Phase 1-5：v2.77.0）
**目标**：YU AI Manager
**目的**：使用双层方案为 AI 图片自动分配 Danbooru 标签：WD-Tagger ONNX（CPU）+ VLM（兼容 OpenAI 的 API）
**实现**：`extensions/builtin_wd_tagger/core_impl/`（12 个文件），`routes/wd_tagger.py`（11 个 API）

---

## 实现状态

| 阶段 | 状态 | 位置 |
|---|---|---|
| Phase 1：WD-Tagger ONNX | **完成** | `extensions/builtin_wd_tagger/core_impl/engine_onnx.py` |
| Phase 2：VLM 引擎（兼容 OpenAI） | **完成**（v2.77.0） | `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` + `engine_composite.py` |
| Phase 3：标签后处理 | **完成**（v2.77.0） | `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` |
| Phase 4：批处理 API | **完成** | `extensions/builtin_wd_tagger/core_impl/batch_ops.py` + `routes/wd_tagger.py` |
| Phase 5：UI | **完成** | 工具页面 + 详情弹窗 WD 标签徽章 + XMP 查看器 |

### Phase 2/3 实现概述（v2.77.0-v2.77.1）

- **VLM 引擎**（`engine_vlm.py`）：自动回退于兼容 OpenAI 的 API 和 Ollama 原生 API 之间
- **复合引擎**（`engine_composite.py`）：双层 ONNX + VLM 管线（模式 B）
- **标签后处理**（`tag_postprocess.py`）：规范化（小写、下划线、无效字符删除、去重）+ NSFW 过滤（约 30 个标签）
- **引擎工厂**：按 `engine_type` 路由（"onnx" / "vlm" / "both"）
- **UI**：引擎类型选择、VLM URL/模型/超时设置、连接测试、NSFW 过滤器
- **API**：`GET /api/wd-tagger/vlm/test`，`GET /api/wd-tagger/vlm/models`
- **MCP**：`wd_tagger_vlm_test`、`wd_tagger_vlm_models` 工具
- **测试**：已确认使用 Ollama qwen2.5vl:7b 对真实图片进行标签标注，23 个单元测试通过

---

## 先行研究

### DeepDanbooru（KichangKim）
- **方案**：图像分类模型（TensorFlow），直接预测标签
- **优点**：快速，标签专用，可转换为 ONNX
- **缺点**：固定标签集，无法适应新标签
- **参考**：已集成到 A1111

### WD-Tagger（SmilingWolf） — Phase 1 采用
- **方案**：DeepDanbooru 的后继。四种架构：SwinV2/ViT/ConvNeXt/EVA02
- **优点**：比 DeepDanbooru 精度更高，包含分类（general/character/copyright/rating）
- **ONNX**：HuggingFace 上分发官方 ONNX 模型 + `selected_tags.csv`
- **输入**：448x448 RGB（保持宽高比 + 白色填充）

### DanTagGen / DTG（KohakuBlueleaf）
- **方案**：基于 LLaMA 的 LLM（400M），用于标签生成和补全
- **优点**：上下文感知的标签补全
- **缺点**：LLM 推理导致速度较慢
- **HuggingFace**：`KBlueLeaf/DanTagGen-beta`

### 设计理由
系统同时支持 WD-Tagger ONNX（快速、可靠）和通过 hailo-ollama 的 Qwen2-VL（灵活、上下文感知），让用户根据需要选择合适的工具。

---

## 架构

```
[图片输入]
    |
[引擎选择]  (engine_factory.py)
    |-- WD-Tagger ONNX（快速，固定标签集约 10,000 个标签）  [Phase 1：已实现]
    |       | 置信度分数 + 分类标签列表
    |-- Qwen2-VL via hailo-ollama（较慢，灵活，上下文感知）   [Phase 2]
    |       | JSON 数组 -> 标签解析
    |-- 双层：ONNX -> Qwen2-VL 补充                    [Phase 2 选项]
    |       | 将 ONNX 标签放入提示词，让 LLM 生成额外标签
    |
[后处理：标签规范化、NSFW 过滤]  [Phase 3]
    |
[DB：保存到 file_wd_tags 表]  (store.py)
[XMP：嵌入文件（可选）]  (xmp_write.py)
```

---

## Phase 1：WD-Tagger ONNX 引擎 — 已实现

**模型**：SmilingWolf/wd-swinv2-tagger-v3（推荐）、ViT v3、ConvNeXt v3、EVA02-Large v3

**实现文件**（`extensions/builtin_wd_tagger/core_impl/`）：
| 文件 | 行数 | 职责 |
|---|---|---|
| `types.py` | 约 60 | TagPrediction、WdTagResult、WdTaggerEngine ABC |
| `tag_csv.py` | 约 70 | selected_tags.csv 解析、分类映射 |
| `model_download.py` | 约 120 | HuggingFace HTTP 下载 |
| `engine_onnx.py` | 约 150 | ONNX 推理（448x448、BGR、阈值过滤） |
| `engine_factory.py` | 约 50 | 引擎缓存 + 创建 |
| `store.py` | 约 130 | DB CRUD（file_wd_tags 表） |
| `xmp_xml.py` | 约 60 | XMP 数据包构建 |
| `xmp_read.py` | 约 90 | XMP 读取 |
| `xmp_write.py` | 约 160 | XMP 写入 PNG/JPEG/WebP |
| `config_ops.py` | 约 70 | config.json 读写 |
| `single_ops.py` | 约 80 | 单张图片标签管线 |
| `batch_ops.py` | 约 120 | 批处理（JobManager 集成） |

**DB**：`file_wd_tags` 表（schema v14）
```sql
CREATE TABLE file_wd_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    model      TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name, model)
);
```

**API**：`routes/wd_tagger.py` — 11 个端点

---

## Phase 2：VLM 引擎（兼容 OpenAI 的 API） — 已实现（v2.77.0）

**目的**：用 ONNX 无法捕获的详细描述和上下文标签补充 WD-Tagger ONNX
**实现**：`extensions/builtin_wd_tagger/core_impl/engine_vlm.py`（通用的兼容 OpenAI 的 VLM 引擎）
**说明**：原始规格计划使用 Hailo 专用的 `engine_hailo.py`，但实际实现使用了通用引擎 `engine_vlm.py`，统一处理 Ollama、hailo-ollama 和其他兼容 OpenAI 的服务器。支持在兼容 OpenAI 的 API（`/v1/chat/completions`）和 Ollama 原生 API（`/api/chat`）之间自动回退。

### 硬件配置

| 项目 | 规格 |
|---|---|
| **设备** | Raspberry Pi 5 + Hailo-10H AI 加速器 |
| **内存** | 8GB RAM |
| **VLM 模型** | **Qwen2-VL-2B-Instruct**（Hailo Model Zoo 中唯一的 VLM） |
| **推理框架** | hailo-ollama（兼容 OpenAI 的 API） |
| **端点** | `http://<pi-ip>:8000/v1/chat/completions` |

### 模型特性

- **Qwen2-VL-2B-Instruct**：Qwen 家族的视觉语言模型（20 亿参数）
- 属于 Qwen 家族，而非 llava 家族。图像理解精度通常高于基于 llava 的模型
- 20 亿参数，可在 Hailo-10H 8GB RAM 中轻松运行
- 纯文本 Qwen2（1.5B）已确认可在 hailo-ollama 上运行
- **注意**：截至 2026-02，这是 Hailo-10H 上唯一可用的 VLM

### 提示词设计

```python
SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
Analyze the image and output ONLY Danbooru-style tags as a JSON array.
Rules:
- Use underscores instead of spaces (e.g., long_hair, blue_eyes)
- Output ONLY the JSON array, no other text
- Include tags for: character count, gender, hair, eyes, clothing, pose, background, art style
- Do NOT include copyright or character name tags unless clearly identifiable
- Maximum 40 tags
Example output: ["1girl", "solo", "long_hair", "blue_eyes", "smile"]"""

USER_PROMPT = "Tag this image with Danbooru tags."
```

### 实现设计（`extensions/builtin_wd_tagger/core_impl/engine_hailo.py` — 约 100 行）

```python
import base64
import json
import logging
import urllib.request
from pathlib import Path

from .types import TagPrediction, WdTagResult, WdTaggerEngine

logger = logging.getLogger(__name__)

_USER_AGENT = "YU-AI-Manager/2.0 (WD-Tagger Qwen2-VL)"

class HailoQwen2VLEngine(WdTaggerEngine):
    """Qwen2-VL-2B-Instruct via hailo-ollama (OpenAI-compatible API)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "qwen2-vl:2b",
        timeout: int = 60,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def tag_image(self, image_path: str) -> WdTagResult:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        # MIME type inference
        suffix = Path(image_path).suffix.lower()
        mime = {"png": "image/png", "webp": "image/webp"}.get(
            suffix.lstrip("."), "image/jpeg"
        )

        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime};base64,{image_b64}"
                        }},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 512,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )

        resp = urllib.request.urlopen(req, timeout=self._timeout)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        raw_tags = json.loads(content)

        # Response format: list or {"tags": [...]}
        if isinstance(raw_tags, dict) and "tags" in raw_tags:
            raw_tags = raw_tags["tags"]
        if not isinstance(raw_tags, list):
            raw_tags = []

        tags = []
        for t in raw_tags:
            name = str(t).strip().lower().replace(" ", "_")
            if name:
                tags.append(TagPrediction(
                    tag=name,
                    confidence=0.5,  # LLMs do not return confidence scores
                    category="general",
                ))

        return WdTagResult(tags=tags, model=self._model)

    def get_name(self) -> str:
        return f"Qwen2-VL ({self._model})"

    def is_available(self) -> bool:
        """Check connectivity to the hailo-ollama server."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/models",
                headers={"User-Agent": _USER_AGENT},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status == 200
        except Exception:
            return False
```

### 运行模式

**模式 A：Qwen2-VL 独立运行**
```
图片 -> Qwen2-VL -> JSON 标签数组 -> 规范化 -> DB 保存
```
- LLM 直接分析图片并生成标签
- 无置信度分数（统一设为 0.5）
- 无固定标签集的灵活标注
- 速度：每张图片约 3-10 秒（Hailo-10H 上的估计值）

**模式 B：WD-Tagger ONNX -> Qwen2-VL 补充（双层）**
```
图片 -> WD-Tagger ONNX -> 高置信度标签 (>=0.7)
                              |
                              v
    Qwen2-VL："这些标签描述了这张图片。请建议额外的标签。"
                              |
                              v
    ONNX 标签 + LLM 补充标签 -> 合并 -> 规范化 -> DB 保存
```
- 将可靠的 ONNX 标签与 LLM 的上下文理解相结合
- 在提示词中包含 ONNX 标签应能提高 LLM 精度
- 速度：ONNX（约 0.5 秒）+ LLM（约 3-10 秒）= 每张图片约 4-11 秒

**模式 B 提示词**：
```python
补完_SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
The image already has these tags from automated classification: {existing_tags}
Analyze the image and suggest ADDITIONAL Danbooru-style tags not in the list above.
Output ONLY a JSON array of new tags. Use underscores instead of spaces.
Focus on: composition, mood, background details, specific clothing items, art style.
Maximum 20 additional tags.
Example: ["looking_at_viewer", "outdoors", "cloudy_sky", "pleated_skirt"]"""
```

### engine_factory.py 的修改

```python
# Addition to get_engine() in engine_factory.py

engine_type = config.get("engine_type", "onnx")  # "onnx" | "hailo" | "both"

if engine_type == "hailo":
    from .engine_hailo import HailoQwen2VLEngine
    engine = HailoQwen2VLEngine(
        base_url=config.get("hailo_url", "http://localhost:8000"),
        model=config.get("hailo_model", "qwen2-vl:2b"),
        timeout=config.get("hailo_timeout", 60),
    )
elif engine_type == "both":
    # Two-tier: ONNX -> Hailo complement (Phase 2 option)
    ...
```

### config.json 条目

```json
{
  "wd_tagger": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "general_threshold": 0.35,
    "character_threshold": 0.85,
    "write_xmp": true,
    "auto_download": true,
    "engine_type": "onnx",
    "hailo_url": "http://localhost:8000",
    "hailo_model": "qwen2-vl:2b",
    "hailo_timeout": 60
  }
}
```

### 预实现验证（Pi 硬件测试）

1. **确认 Qwen2-VL-2B-Instruct 在 hailo-ollama 上可以启动**
   ```bash
   # 在 Pi 上
   hailo-ollama run qwen2-vl:2b
   ```

2. **确认视觉请求可以通过兼容 OpenAI 的 API 工作**
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen2-vl:2b",
       "messages": [{"role": "user", "content": [
         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}},
         {"type": "text", "text": "What is in this image?"}
       ]}],
       "max_tokens": 256
     }'
   ```

3. **确认 Danbooru 格式的 JSON 输出是否稳定**
   - 检查 hailo-ollama 是否支持 `response_format: json_object`
   - 如果不支持，需要基于正则表达式从文本输出中提取 JSON 的回退方案

4. **测量实际推理速度** — 每张图片的秒数（用于批处理大小计算）

---

## Phase 3：标签后处理 — 已实现（v2.77.0）

**实现**：`extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`
**集成**：在 `single_ops.py` / `batch_ops.py` 中推理后自动应用

```python
class TagPostProcessor:
    INVALID_CHARS = set('[](){}"\'/\\')
    MAX_TAG_LEN = 100

    def normalize(self, tags: list[str]) -> list[str]:
        result = []
        for tag in tags:
            tag = tag.strip().lower()
            tag = tag.replace(" ", "_")
            # Remove invalid characters
            tag = "".join(c for c in tag if c not in self.INVALID_CHARS)
            if 1 <= len(tag) <= self.MAX_TAG_LEN:
                result.append(tag)
        # Deduplicate and sort
        return sorted(set(result))

    def filter_nsfw(self, tags: list[str], allow_nsfw: bool) -> list[str]:
        # NSFW tag list (managed in a separate file)
        if allow_nsfw:
            return tags
        return [t for t in tags if t not in NSFW_TAG_SET]
```

**与 Phase 1 的集成**：
- WD-Tagger ONNX 已通过类别 9（rating）分离评级标签
- NSFW 过滤器使用评级标签（`explicit`、`questionable`）加上额外的 NSFW 列表
- 已实现：`extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`（约 80 行）

---

## Phase 4：批处理 API — 已实现

**API**（`routes/wd_tagger.py`）：

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/wd-tagger/batch` | 启动批处理（file_ids、limit、force） |
| POST | `/api/wd-tagger/tag/<file_id>` | 标注单张图片 |
| GET | `/api/wd-tagger/tags/<file_id>` | 获取标签 |
| DELETE | `/api/wd-tagger/tags/<file_id>` | 删除标签 |
| GET | `/api/wd-tagger/stats` | 统计信息 |
| GET | `/api/wd-tagger/untagged` | 列出未标注文件 |
| GET/POST | `/api/wd-tagger/config` | 设置 CRUD |
| POST | `/api/wd-tagger/model/download` | 模型下载 |
| GET | `/api/wd-tagger/model/status` | 模型状态 |
| GET | `/api/wd-tagger/xmp/<file_id>` | XMP 读取 |

**处理流程**（`batch_ops.py`）：
1. 按顺序处理 `file_ids` 中的文件（未指定时默认处理 `meta_source=unknown` 的未标注文件）
2. 通过引擎运行推理
3. UPSERT 到 `file_wd_tags` 表（通过 model 列识别引擎）
4. 将 XMP 嵌入文件（可选）
5. 通过 JobManager 跟踪进度并支持取消

---

## Phase 5：UI — 已实现

**工具页面**（`templates/tools/content/primary/_wd_tagger.html`）：
- 模型选择（4 种模型），阈值滑块（general/character）
- XMP 写入开关，模型下载按钮
- 批处理执行按钮 + 进度条
- 统计信息显示（标签数量、按分类统计、未标注数量）

**详情弹窗**：
- WD 标签徽章（general=蓝色、character=绿色、copyright=橙色、rating=红色）
- XMP 查看器按钮（dc:subject + wdtag 命名空间 + 原始 XML）
- 点击标签触发搜索

---

## 文件结构（当前）

```
extensions/builtin_wd_tagger/core_impl/
├── __init__.py              # 模块初始化
├── types.py                 # TagPrediction、WdTagResult、WdTaggerEngine ABC
├── tag_csv.py               # selected_tags.csv 解析
├── model_download.py        # HuggingFace 模型下载
├── engine_onnx.py           # WD-Tagger ONNX 推理 [Phase 1]
├── engine_vlm.py            # VLM 引擎（兼容 OpenAI）[Phase 2：已完成]
├── engine_composite.py      # ONNX + VLM 双层方案 [Phase 2：已完成]
├── engine_factory.py        # 引擎创建 + 缓存
├── store.py                 # DB CRUD（file_wd_tags）
├── xmp_xml.py               # XMP 数据包构建
├── xmp_read.py              # XMP 读取
├── xmp_write.py             # XMP 写入（PNG/JPEG/WebP）
├── config_ops.py            # config.json 读写
├── single_ops.py            # 单张图片标签管线
├── batch_ops.py             # 批处理（JobManager）
├── batch_processors.py      # 批处理内部逻辑
└── tag_postprocess.py       # 标签规范化、NSFW 过滤 [Phase 3：已完成]

routes/wd_tagger.py          # API 端点（共 11 个）

src/ts/tools-page/wd-tagger/
├── core.ts                  # 设置 CRUD、批处理、模型下载
└── render.ts                # DOM 渲染

src/ts/runtime-tools-ui/tools/
└── wd-tags.ts               # 详情弹窗 WD 标签 + XMP 查看器
```

---

## 实现优先级（已更新）

```
Phase 1（WD-Tagger ONNX）        -> 完成
Phase 4（批处理 API）              -> 完成
Phase 5（UI）                     -> 完成
Phase 3（后处理/NSFW）             -> 下一步（约增加 80 行）
Phase 2（Qwen2-VL hailo-ollama）  -> Pi 硬件测试后（约增加 100 行 + 工厂修改）
```

---

## 参考文献

- WD-Tagger (SmilingWolf): https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
- DeepDanbooru: https://github.com/KichangKim/DeepDanbooru
- DanTagGen: https://huggingface.co/KBlueLeaf/DanTagGen-beta
- Hailo Model Zoo VLM: Qwen2-VL-2B-Instruct (hailo.ai Model Explorer)
- hailo-ollama API 规格：请参考修改后的 fork 源码

---

*创建日期：2026-02-27 / 更新日期：2026-02-27（Phase 1 实现完成，Phase 2 修订为基于 Qwen2-VL）*

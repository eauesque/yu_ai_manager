# Hailo 语义搜索扩展 — 实现规格

**状态**：已实现 — Hailo 专用版本已被 CLIP ONNX（v2.95.0）取代
**目标**：YU AI Manager 扩展
**目的**：使用 CLIP/SigLIP 在 Hailo-10H（AI HAT 2）上实现语义图片搜索
**实现**：`extensions/builtin_clip_search/core_impl/`（共享层）+ `extensions/builtin_clip_onnx/core_impl/`（ONNX 实现）
**说明**：本规格描述了最初的 Hailo 专用设计。当前实现使用统一的 ONNX 多后端架构

---

## 概述

本扩展添加了使用自然语言文本搜索图片的功能。
例如："蓝天和海洋"、"微笑的女孩"、"夜晚城市风景" — 都会返回视觉上相似的图片。

它需要与现有的 FTS5 标签搜索和 pHash 相似度搜索**并行工作**。
在没有 Hailo 设备的环境中，扩展会自动禁用自身。

---

## 架构

```
[图片扫描时]
图片文件 -> CLIP 图像编码器（Hailo HEF） -> 512 维向量 -> DB 存储

[搜索时]
文本输入 -> CLIP 文本编码器（CPU / Hailo HEF） -> 512 维向量
           -> 余弦相似度搜索 -> file_id 列表 -> 与现有搜索结果合并
```

**同时支持 CLIP 和 SigLIP**，可通过配置切换。
SigLIP 精度更高，但 CLIP 有更强的实绩和更多社区资源。
推荐方案是先使用 CLIP，之后再添加 SigLIP。

---

## 阶段划分

### Phase 1：可行性验证（最先执行）

迁移到 Pi5 环境后，让 Claude Code **从上到下按顺序**执行以下步骤。
在任何步骤失败时停止，先解决问题再继续。

#### 步骤 1-1：验证 HailoRT 运行时

```bash
# 检查设备识别
hailortcli fw-control identify

# 检查 Python 绑定
python3 -c "import hailo_platform; print('HailoRT version:', hailo_platform.__version__)"
```

- **设备不可见**：使用 `dmesg | grep hailo` 检查驱动状态。验证 AI HAT 2 PCIe 连接
- **导入失败**：通过 `pip install hailort` 安装，或从 Hailo APT 仓库安装（`python3-hailort`）

#### 步骤 1-2：下载 CLIP HEF 文件

```bash
mkdir -p ~/hailo_models && cd ~/hailo_models

# 图像编码器
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef

# 文本编码器
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_text_encoder.hef
```

- **403 / 拒绝访问**：需要在 Hailo Developer Zone（https://hailo.ai/developer-zone/）注册。
  注册后，尝试通过 Model Zoo CLI（`hailo_model_zoo`）下载
- **大小检查**：每个文件应为数十到约 100 MB。异常小的文件表示下载失败

#### 步骤 1-3：安装 Python 依赖

```bash
# 图像预处理所需（Phase 1 使用）
pip install opencv-python-headless numpy

# 验证
python3 -c "import cv2; import numpy; print('cv2:', cv2.__version__, 'numpy:', numpy.__version__)"
```

#### 步骤 1-4：最小推理测试

```python
from hailo_platform import HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams
import numpy as np

hef_path = "/home/<user>/hailo_models/clip_vit_b_16_image_encoder.hef"
hef = HEF(hef_path)

# 检查 HEF 输入/输出层信息（层名因模型而异）
print("Input layers:", [l.name for l in hef.get_input_vstream_infos()])
print("Output layers:", [l.name for l in hef.get_output_vstream_infos()])

with VDevice() as target:
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = target.configure(hef, configure_params)
    network_group = network_groups[0]

    input_info = hef.get_input_vstream_infos()[0]
    input_name = input_info.name
    input_shape = input_info.shape  # 预期：(224, 224, 3) 等
    print(f"Input: name={input_name}, shape={input_shape}")

    # 使用虚拟图片进行推理测试
    dummy = np.random.randint(0, 255, (1, *input_shape), dtype=np.uint8)
    with InferVStreams(network_group, {}) as pipeline:
        result = pipeline.infer({input_name: dummy})
        for name, data in result.items():
            print(f"Output: name={name}, shape={data.shape}, dtype={data.dtype}")
            # 如果输出 512 维向量则成功
```

- **VDevice 错误（`not enough free devices`）**：hailo-ollama 可能正在运行。使用 `systemctl stop hailo-ollama` 停止后重试
- **推理成功但输出非 512 维**：验证 HEF 版本和模型变体

#### 步骤 1-5：决策标准

| 结果 | 下一步行动 |
|------|----------------|
| 输出 512 维向量 | 继续 Phase 2 及之后的阶段 |
| HEF 加载成功但输出维度不同 | 尝试不同的模型变体（clip_resnet_50 等） |
| 无法下载 HEF | 在 Developer Zone 注册 -> 通过 Model Zoo CLI 下载 |
| 无法导入 hailo_platform | 重新安装 HailoRT。如未解决则回退到 CPU CLIP |
| 设备未识别 | 硬件连接/驱动问题。暂停本扩展开发 |

Phase 1 成功后继续完整实现。如果失败则考虑 CPU CLIP 作为替代方案。

---

### Phase 2：DB 模式扩展

添加到现有的 DB 迁移中：

```sql
-- migration 14: semantic search vectors
CREATE TABLE IF NOT EXISTS file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip',   -- 'clip' | 'siglip'
    vector      BLOB NOT NULL,                  -- float32 numpy array -> bytes
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model);
```

存储：`numpy.ndarray.tobytes()` -> BLOB
加载：`numpy.frombuffer(blob, dtype=numpy.float32)`

**说明**：SQLite 没有 ANN（近似最近邻）索引，因此所有 200,000 条记录需要完整的余弦相似度计算。使用 numpy 的批量计算应能在 Pi5 上保持在可接受的范围内（需要实测）。如果记录数显著增长，考虑使用 `sqlite-vec` 扩展。

---

### Phase 3：Hailo 推理核心

**文件结构**：
```
extensions/hailo_semantic_search/
├── __init__.py
├── extension.py          # 扩展入口点
├── core/
│   ├── hailo_clip.py     # Hailo CLIP 推理封装
│   ├── cpu_clip.py       # 非 Hailo 环境的 CPU 回退（可选）
│   └── vector_store.py   # DB 向量 CRUD
├── routes/
│   └── semantic_search.py  # API 端点
└── templates/
    └── _semantic_search_ui.html
```

**`hailo_clip.py` 的职责**：
- HEF 加载和 VDevice 初始化（单例，启动时一次）
- 图片 -> 预处理（224x224 缩放、规范化） -> HEF 推理 -> 512 维向量
- 文本 -> 分词 -> HEF 推理 -> 512 维向量
  * 如果 Hailo-10H 有可用的文本编码器 HEF 则使用；否则使用 CPU（transformers 库）

**预处理**：
```python
import cv2
import numpy as np

def preprocess_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (224, 224))
    img = img.astype(np.float32) / 255.0
    mean = np.array([0.48145466, 0.4578275, 0.40821073])
    std  = np.array([0.26862954, 0.26130258, 0.27577711])
    img = (img - mean) / std
    return img[np.newaxis, ...]  # (1, 224, 224, 3)
```

---

### Phase 4：索引构建 API

**端点**：
```
POST /api/extensions/hailo-semantic/index
```
- 在后台线程中按顺序处理未索引的图片
- 通过 SSE 以 `semantic_index.progress` 事件发送进度
- 可选择挂钩到现有的 `scan.complete` 事件以自动执行

**批大小**：每批 32 张图片（平衡内存和速度）

```
GET /api/extensions/hailo-semantic/index/status
-> { "total": 200000, "indexed": 12500, "running": true }
```

---

### Phase 5：语义搜索 API

```
GET /api/extensions/hailo-semantic/search?q=blue sky&limit=50&threshold=0.25
```

**处理流程**：
1. 将文本 `q` 转换为向量
2. 从 `file_vectors` 加载所有向量（numpy）
3. 批量计算余弦相似度
4. 将高于 `threshold` 的结果按相似度降序排列
5. 以现有 `/api/search` 格式返回 `file_id` 列表

**余弦相似度计算**：
```python
def cosine_similarity_batch(query_vec: np.ndarray, stored_vecs: np.ndarray) -> np.ndarray:
    # query_vec: (512,), stored_vecs: (N, 512)
    query_norm = query_vec / np.linalg.norm(query_vec)
    stored_norm = stored_vecs / np.linalg.norm(stored_vecs, axis=1, keepdims=True)
    return stored_norm @ query_norm  # (N,)
```

**性能目标**：200,000 条记录在 1 秒以内（使用 numpy 批量计算可实现，即使在 Pi5 上）

---

### Phase 6：UI 集成

在现有搜索 UI 中添加"语义搜索"标签页。
可以是独立于现有条件构建器的独立 UI（集成留待将来）。

```html
<!-- 在搜索栏旁边添加切换按钮 -->
<button id="semantic-search-toggle" class="btn-secondary">
  🔍 语义搜索 (Hailo)
</button>
```

- 未检测到 Hailo 设备时隐藏或灰显按钮
- 搜索结果复用现有网格
- 没有索引时显示构建索引的提示

---

## 配置（config.json 新增项）

```json
{
  "hailo_semantic_search": {
    "enabled": true,
    "model": "clip",           // "clip" | "siglip"
    "device": "auto",          // "auto" | "hailo" | "cpu"
    "batch_size": 32,
    "similarity_threshold": 0.25,
    "auto_index_on_scan": false,
    "hef_dir": "~/.local/share/hailo-ollama/models"
  }
}
```

---

## 已验证事实（截至 2026-02-27）

以下信息已通过前期调研确认。在执行 Phase 1 时作为参考使用。

### CLIP HEF 可用性

Hailo Model Zoo v5.2.0 包含 Hailo-10H 的 CLIP/SigLIP 变体的**图像和文本编码器** HEF：

| 模型 | 图像编码器 HEF | 文本编码器 HEF |
|--------|-------------------|-------------------|
| clip_vit_b_16 | 可用 | 可用 |
| clip_vit_b_32 | 可用 | 可用 |
| clip_vit_l_14 | 可用 | 可用 |
| clip_resnet_50 | 可用 | 可用 |
| siglip_b_16 | 可用 | 可用 |
| siglip_l_16_256 | 可用 | 可用 |
| siglip2_b_32_256 | 可用 | 可用 |
| TinyCLIP 变体 | 可用 | 可用 |

S3 URL 模式：`https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef`

### 文本编码器状态

- 官方 `hailo-CLIP` 应用**在 CPU 上运行文本编码器（PyTorch）**
- Model Zoo 中存在 Hailo-10H 的文本编码器 HEF，但**没有已发布的应用使用它们**
- 推荐方案：**在 CPU 上实现文本编码器（`sentence-transformers`）**。每次搜索查询只运行一次，所以速度不是问题
- 图像编码器才是 Hailo 加速真正发挥价值的地方（200K 图片的批量索引）

### 与 hailo-ollama 的共存

- 通过 `SHARED_VDEVICE_GROUP_ID` 实现设备共享是官方支持的
- 但是，**hailo-ollama 二进制文件不参与此共享**（它独占设备）
- 社区示例：有人构建了自定义设备管理器来同时运行 6 个服务
- **实际方案**：在索引构建期间停止 hailo-ollama，分时共享设备
  - `systemctl stop hailo-ollama` -> 构建索引 -> `systemctl start hailo-ollama`

### 200,000 条记录的向量搜索估算

- 200K x 512 float32 = 约 400MB — 在 Pi5（8GB）RAM 中可容纳
- numpy 批量余弦相似度在 Pi5 Cortex-A76 上应在 1 秒内完成

### 大规模向量搜索的 FAISS 加速（v3.26.0）

v3.26.0 中添加了 FAISS（Facebook AI Similarity Search）支持。系统在安装 `faiss-cpu` 时自动检测，使用近似最近邻搜索替代 NumPy 暴力搜索。

| 规模 | NumPy (O(N)) | FAISS IndexFlatIP | FAISS IndexIVFFlat |
|------|-------------|-------------------|-------------------|
| 10K | 约 10ms | 约 2ms | - |
| 100K | 约 100ms | 约 20ms | 约 5ms |
| 500K | 约 500ms | 约 100ms | 约 10ms |
| 1.5M | 约 1.5s | 约 300ms | 约 20ms |

- **< 50K**：自动选择 IndexFlatIP（精确内积搜索）
- **>= 50K**：自动选择 IndexIVFFlat（IVF 聚类），nprobe = nlist/10
- 未安装 FAISS 时回退到 NumPy（无影响）

**安装**：
```bash
source venv/bin/activate
uv pip install faiss-cpu  # x86_64 上直接 pip 安装即可
# 在 aarch64（RPi）上：conda install -c conda-forge faiss-cpu 或从源码构建
```

启动日志在激活时显示 `FAISS x.x.x detected — using accelerated vector search`。

### 关于 hailo-CLIP 应用的说明

- `hailo-ai/hailo-CLIP` 针对 **Hailo-8/8L**。不支持 Hailo-10H
- 它设计用于实时零样本分类，而非图片搜索管线
- 可作为参考材料，但无法直接使用。必须使用 HailoRT API 构建自定义管线

---

## 替代方案（Hailo 不可用时）

`sentence-transformers` 配合 `clip-ViT-B-32` 提供仅 CPU 的 CLIP 支持。
速度较慢，但允许相同的扩展在没有 Hailo 的环境中运行。

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('clip-ViT-B-32')
image_embedding = model.encode(Image.open(path))
text_embedding  = model.encode("blue sky")
```

在扩展配置中设置 `"device": "cpu"` 可启用 CPU 模式。这种双架构方案最大化了可移植性。

---

## 实现优先级

```
Phase 1（验证）       -> 必需，最先执行
Phase 2（DB）         -> Phase 1 成功后
Phase 3（推理核心）    -> Phase 2 之后
Phase 4（索引构建）    -> Phase 3 之后
Phase 5（搜索 API）   -> Phase 4 之后
Phase 6（UI）         -> Phase 5 之后，最后执行
```

如果 Phase 1 失败，则将整个方案切换到 CPU CLIP。

---

## 参考仓库

- `hailo-ai/hailo-apps`：CLIP 零样本分类示例
- `hailo-ai/hailort`：pyHailoRT API 参考
- `hailo-ai/Hailo-Application-Code-Examples`：Python 推理示例
- `hailo-ai/hailo_model_zoo`：CLIP/SigLIP HEF 下载源

---

*创建日期：2026-02-27*
*调研附录：2026-02-27 — Phase 1 流程详情、HEF 可用性确认、hailo-ollama 共存分析*

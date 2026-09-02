# LoRA 训练指南

使用 YU AI Manager + MCP + kohya_ss 进行自然语言 LoRA 训练的完整指南

---

## 前言

本指南说明如何通过 YU AI Manager 的 MCP 服务器与 kohya_ss 集成，仅凭自然语言指令即可完成 LoRA 制作流程。

传统 LoRA 制作的大部分工时花费在"数据集手动准备"上：图片筛选、标签审查与排除、caption 文件整理、文件夹结构整理——这些全由人工完成。

YU AI Manager 的 MCP 集成改变了这个流程。只需一句"请为○○制作 LoRA，排除△△标签"，从素材收集、标记、数据集生成到启动 kohya_ss 训练，整个流程一贯作业。

---

## 整体流程

LoRA 制作分为以下五个阶段：

| 阶段 | 作业内容 | 负责方 |
|------|---------|--------|
| 1. 素材准备 | 收集并配置训练用图片 | 人工 / AI 代理 |
| 2. 标记 | 通过 WD-Tagger 自动标记 | MCP（自动） |
| 3. 数据集生成 | 创建项目、设定排除标签、导出 | MCP（自动） |
| 4. 执行训练 | 调用 kohya_ss 进行训练 | MCP（自动） |
| 5. 验证 | 在 SD 中使用 LoRA 确认结果 | 人工 |

人工介入仅限于决定"要训练什么"与最终结果确认。

---

## 前置条件

### 必要软件

- YU AI Manager — 含 MCP 服务器功能
- Claude Desktop 或 Claude Code — MCP 客户端
- kohya_ss — 需包含 sd-scripts
- Stable Diffusion WebUI（A1111 / ComfyUI / Forge）— 结果验证用

### GPU 需求

| GPU VRAM | 支持模型 | 必要设置 |
|---------|---------|---------|
| 8GB | 仅 SD 1.5 实用 | `--gradient_checkpointing` 必要 |
| 12GB | SDXL 可运行（有限制） | `--gradient_checkpointing` + `--cache_latents_to_disk` |
| 16GB | SDXL 流畅 | 默认设置即可运行 |
| 24GB+ | SDXL 与 FLUX 均支持 | 几乎无限制 |

> **注意**：RTX 3060 12GB 可进行 SDXL LoRA 训练，但因需使用 gradient_checkpointing，24,000 步骤约需 10 小时。RTX 5060 Ti 16GB 预计可缩短至 3〜5 小时。

### kohya_ss 目录结构

kohya_ss 的顶层目录与实际脚本目录通常是分离的：

```
O:\webui\kohya_ss\              ← 设置为 kohya_path 的顶层目录
O:\webui\kohya_ss\venv\         ← Python 虚拟环境（自动检测）
O:\webui\kohya_ss\sd-scripts\   ← 存放训练脚本的目录
```

> ⚠️ **注意**：将顶层目录指定为 `kohya_path`，YU AI Manager 会自动检测 `sd-scripts` 子文件夹与 venv。请勿直接指定 sd-scripts 路径。

---

## YU AI Manager 设置

### Extension 设置

在 LoRA Dataset Manager 的设置标签页中输入以下内容：

| 设置项目 | 说明 | 示例 |
|---------|------|------|
| `kohya_path` | kohya_ss 顶层目录 | `O:\webui\kohya_ss` |
| `output_base_dir` | 数据集输出基础目录 | `C:\lora_datasets` |
| `checkpoint_dir` | 基础模型所在目录 | `O:\webui\models\Stable-diffusion` |
| `default_base_model` | 默认模型类型 | `sdxl` |

### WD-Tagger 设置

LoRA 数据集用途不建议搭配 VLM（llava 等）。VLM 会产生大量自由格式标签，降低 caption 质量。

```
engine_type: "onnx"  ← 仅使用 ONNX
```

> ⚠️ **注意**：将 `engine_type` 设为 `"both"` 会产生 VLM 衍生的复合标签（如 `wooden_bear_and_fish_sculpture`）。这些标签无法作为 kohya_ss 的 caption，会妨碍训练。

---

## 通过 MCP 创建 LoRA 的步骤

### Step 1：准备素材图片

将训练用图片配置到 YU AI Manager 的 scan root 并执行扫描。

- 在 YU AI Manager 的 Scan Root 设置中添加训练文件夹
- 扫描完成后，目标图片会登录至 DB
- 最少 20〜30 张，建议 50〜200 张

> **注意**：图片质量是训练结果的最大决定因素。选择分辨率 512px 以上、主体清晰的图片。

### Step 2：使用 WD-Tagger 标记

从 MCP 执行批量标记：

```python
# 获取目标文件 ID 列表并批量标记
wd_tagger_batch(file_ids=[...], expected_count=N)
wait_for_batch(job_id="wd_tagger")
```

若已有现有标签，请先删除再重新执行：

```python
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
```

### Step 3：创建项目

```python
create_lora_project(
    name="carved_bear",
    concept="carved_bear",   # 用作 kohya_ss 文件夹名称
    base_model="sdxl",
    repeat=20
)
```

### Step 4：设置文件与标签

将文件 ID 设置至项目并确认标签统计：

```python
update_lora_project(project_id=N, file_ids=[...])
get_lora_project_tags(project_id=N)
```

查看标签统计后决定要排除的标签。

#### 排除标签的设计思路

这是决定 LoRA "要学习什么"的核心。

**保留的标签**：要学习的概念固有特征（造形、风格、固有元素）

**排除的标签**：基础模型已知的通用标签（`no_humans`、`realistic`、`animal`、`solo`、背景相关等）

示例——木雕熊 LoRA：

- 保留：`bear`、`fish`、`statue`、`sculpture`、`standing`、`full_body`、`open_mouth`
- 排除：`no_humans`、`animal_focus`、`animal`、`realistic`、`simple_background`、`solo`、`indoors`、`shadow`...

> ⚠️ **注意**：若无法精确切出概念，训练会分散。若想保留 `bear` 或 `wood`，WD-Tagger ONNX 可能不一定会附加这些标签。请通过 caption 预览确认实际输出。

```python
update_lora_project(
    project_id=N,
    tag_exclude=["no_humans", "animal_focus", "animal", "realistic", ...]
)
```

### Step 5：预览 Caption

```python
preview_lora_caption(project_id=N, file_id=<任意文件ID>)
```

输出示例：

```
"fish, full_body, open_mouth, standing"
```

确认输出为没有 VLM 噪声的简洁标签列表。若有许多空白 caption，请重新检视排除标签设置。

### Model Scope

Each project has a `model_scope` setting that controls which WD-Tagger model is used for captions, preview, and export.

- `active` (default for new projects): Use tags from the active WD model only. If no active model is set, it falls back to all models.
- `all` (default for existing projects): Mix tags from all models.
- `<model_id>` (for example, `wd-eva02-large-tagger-v3`): Use tags from the explicitly selected model only.

For files tagged by multiple models, `active` is usually sufficient. When you need an explicit model for comparison or validation, use the same model_id shown in the WD-Tagger profile dropdown on the Tools page.

### Step 6：导出数据集

```python
export_lora_dataset(project_id=N)
```

输出文件夹结构：

```
{output_base_dir}/{project_name}/{repeat}_{concept}/
    image001.jpeg
    image001.txt   ← caption
    image002.jpeg
    image002.txt
```

### Step 7：执行训练

先用 dry_run 确认命令：

```python
preview_lora_train_command(
    project_id=N,
    checkpoint="完整路径\checkpoint.safetensors"
)
```

确认无误后启动训练：

```python
start_lora_training(
    project_id=N,
    checkpoint="完整路径\checkpoint.safetensors",
    extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
)
```

确认进度：

```python
get_lora_train_status(project_id=N, tail=20)
```

---

## 默认训练参数

| 参数 | 默认值 | 说明 |
|-----|--------|------|
| `network_dim` | 32 | LoRA 的 rank。越大表现力越高，但文件也越大 |
| `network_alpha` | 16 | 通常设为 dim 的一半 |
| `learning_rate` | 1e-4 | 学习率 |
| `max_train_epochs` | 10 | Epoch 数 |
| `save_every_n_epochs` | 2 | 中间保存间隔 |
| `mixed_precision` | fp16 | 精度。某些情况下 bf16 可节省更多 VRAM |
| `resolution` | 1024,1024（SDXL） | 训练分辨率。SD1.5 使用 512,512 |

> **注意**：这些参数可在 Settings 标签页或通过 `set_extension_config` 修改。额外参数可通过 `start_lora_training` 的 `extra_args` 添加。

---

## 各 GPU 推荐设置

| GPU VRAM | 推荐 extra_args |
|---------|---------------|
| 8GB | `--gradient_checkpointing --xformers --cache_latents_to_disk --optimizer_type=AdamW8bit` |
| 12GB | `--gradient_checkpointing --xformers --cache_latents_to_disk` |
| 16GB | （默认即可运行） |
| 24GB+ | （默认即可运行；可提高 batch_size） |

> ⚠️ **注意**：在 12GB GPU 上使用 gradient_checkpointing 时，SDXL 24,000 步骤约需 10〜12 小时。16GB 以上不受此限制，速度大幅提升。

---

## Repeat 数与 Epoch 数的参考标准

**总训练步骤数 = 图片数量 × repeat 数 × epoch 数**

| 概念复杂度 | 建议步骤数 | 示例（50 张图片） |
|----------|----------|----------------|
| 简单物件或风格 | 1,000〜3,000 | repeat=10, epoch=5 |
| 角色或造形物 | 3,000〜8,000 | repeat=20, epoch=5 |
| 复杂风格或人物 | 5,000〜15,000 | repeat=20, epoch=10 |

> **注意**：以 120 张 × 20 repeat × 10 epoch = 24,000 步骤训练可获得良好质量。但 5〜6 epoch 也可能达到相同结果，建议先尝试较少的 epoch 数。

---

## 故障排除

### ModuleNotFoundError: No module named 'torch'

**原因**：YU AI Manager 尝试在自己的 venv 中执行 kohya_ss 脚本。

**处理方式**：将 `kohya_path` 设置为顶层目录（sd-scripts 的上层目录）。YU AI Manager 会自动检测 `kohya_path/venv/Scripts/python.exe`。

---

### AssertionError: resolution is required

**原因**：未指定 `--resolution`。

**处理方式**：最新版 YU AI Manager 会自动附加此参数（SDXL：1024,1024；SD1.5：512,512）。

---

### AssertionError: network for Text Encoder cannot be trained with caching

**原因**：`--cache_text_encoder_outputs` 与 `--network_train_unet_only` 未配对使用。

**处理方式**：最新版 YU AI Manager 在 SDXL 模式下会自动附加 `--network_train_unet_only`。

---

### torch.OutOfMemoryError: CUDA out of memory

**原因**：VRAM 不足。

**处理方式**：在 `extra_args` 中添加以下参数：

```python
extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
```

---

### VLM 噪声标签混入

**原因**：`engine_type` 设为 `"both"`，导致 VLM（llava 等）产生自由格式标签。

**处理方式**：在 WD-Tagger 设置中改为 `engine_type="onnx"`，删除所有标签后重新标记。

```python
wd_tagger_save_config({"engine_type": "onnx"})
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
wd_tagger_batch(file_ids=[...], expected_count=N)
```

---

### checkpoint must be inside checkpoint_dir（403 错误）

**原因**：checkpoint 路径指向 `checkpoint_dir` 以外的位置。

**处理方式**：确认 Extension 设置中的 `checkpoint_dir` 是否指向正确目录。

---

### output_base_dir not configured（400 错误）

**原因**：Extension 设置中的 `output_base_dir` 未设置或未保存。

**处理方式**：在 UI 设置标签页中重新保存，或从 MCP 通过 `set_extension_config` 设置。

---

## 生成时的提示词

### 基本提示词结构

```
{concept_token}, {特征标签}, <lora:{lora_name}:{strength}>
```

木雕熊 LoRA 示例：

```
carved_bear, wooden sculpture, bear statue, wood texture, brown,
full_body, standing, open_mouth, fish, simple_background,
<lora:carved_bear:0.7>
```

负面提示词：

```
blurry, lowres, bad anatomy, worst quality, flat color, monochrome
```

### 调整 LoRA 强度

| 强度 | 特性 |
|-----|------|
| 0.5〜0.6 | 基础模型影响较强；颜色与风格偏向基础模型 |
| 0.7〜0.8 | 推荐范围；LoRA 特征与基础模型平衡良好 |
| 0.9〜1.0 | LoRA 影响较强；造形明确但颜色易偏白/奶油色 |

> **注意**：若颜色偏白，请降低强度，或在提示词中加入 `brown wood, warm tone` 来引导颜色。

---

## 未来扩展

### 素材收集自动化

目前素材图片仍需人工手动准备。使用 Claude in Chrome 等浏览器代理，可通过"请从网络收集○○的图片放入文件夹"的指令自动化素材收集。

将 YU AI Manager 自身的生成图片作为素材也是有效的方向——由 SD/ComfyUI/NAI 生成的图片可直接作为 LoRA 训练素材再利用。

### LoRA 量产流程

搭配 MCP + Claude Desktop，可实现如下完全自动化：

1. 从网络收集素材图片（Claude in Chrome）
2. 在 YU AI Manager 中扫描与标记（MCP）
3. 创建项目、设定排除标签、导出（MCP）
4. 启动 kohya_ss 训练（MCP）
5. 睡前下达指令 → 隔天早上 LoRA 完成

### 选择基础模型

waiSHUFFLENOOB 等 Illustrious 系基础模型针对动漫风格生成优化。使用实拍素材（木雕熊等）训练时容易产生白/奶油色调。

追求接近实拍质感时，请选择 realisticPhoto 系基础模型。LoRA 必须与训练时使用的基础模型相同才能使用。

---

## 总结

YU AI Manager + MCP + kohya_ss 的流程大幅降低了 LoRA 制作所需的工时。

- 从素材图片到完整 epoch 训练，仅需 MCP 指令即可完成
- 整个流程通过自然语言指令运作
- 生成图片中清晰呈现训练对象的造形

唯一剩余的人工步骤是素材收集，与浏览器代理结合后即可实现完全自动化。

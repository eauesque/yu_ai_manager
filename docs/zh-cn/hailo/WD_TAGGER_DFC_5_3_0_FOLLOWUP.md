# DFC 转换续报:WD-Tagger 模型在 DFC v5.3.0 上的重新验证

**日期**: 2026-04-06
**DFC 版本**: 5.3.0
**前次报告**: [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md) (2026-03-06)
**环境**: WSL2 (Ubuntu 24.04)、x86_64

---

## 背景

2026 年 3 月,我曾报告 WD-Tagger 的三个变体 (SwinV2、ViT、ConvNeXt) 在 Hailo Dataflow Compiler v5.2.0 的 parser 阶段全部失败,根本无法到达量化步骤。原始报告保存在 [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md)。

我已在 DFC v5.3.0 下重新测试所有三个模型。这份文档是后续报告。

---

## 结果摘要

| 模型 | 大小 | DFC 5.2.0 错误 | DFC 5.3.0 错误 | 变化 |
|---|---|---|---|---|
| `wd-swinv2-tagger-v3` | 446 MB | `_convert_axes_to_nhwc` 中的 `IndexError` | 相同 | **无** |
| `wd-vit-tagger-v3` | 362 MB | 同上 | 相同 (onnxsim 重试后) | 增加了重试流程 |
| `wd-convnext-tagger-v3` | 377 MB | `UnsupportedShuffleLayerError` | 相同 + 额外的 `UnsupportedModelError` | **错误增加** |

**三个模型仍然全部在 parser 阶段失败。** 量化步骤 (为此准备了 500 张标定图像) 与 v5.2.0 运行一样仍然无法到达。

---

## DFC v5.3.0 中的改变

虽然失败依然存在,但与 v5.2.0 相比可以看到以下改进:

### 1. `_create_layer_normalization_layer` 方法新增

这个方法在 v5.2.0 中根本不存在。DFC v5.3.0 现在尝试通过专用的代码路径明确处理 `LayerNormalization` 算子。这是持续开发努力的明确信号。

不过,**内部实现仍不完整**:方法被调用了,但其内部对 `_convert_axes_to_nhwc` 的调用仍然在 v5.2.0 失败过的相同张量形状上抛出 `IndexError: list index out of range`。

### 2. onnxsim 简化 + 重试流程新增

对于 ViT 和 ConvNeXt,DFC v5.3.0 现在会自动使用 `onnxsim` 简化输入的 ONNX 模型并重新尝试解析。简化后的模型会保存为输入旁边的 `model.sim.onnx`。对于有冗余或复杂 ONNX 图的模型来说,这是有用的新安全网。

但对于这些具体的模型,重试**在完全相同的位置失败**,因为根本原因在于 `_convert_axes_to_nhwc`,而非 ONNX 图结构。

### 3. End node 推荐

对于 ConvNeXt,DFC v5.3.0 现在会在 parser 放弃时产生针对 end node 的具体建议,并提示用户用这些 node pin 住后重试。这是体贴的用户体验改进。

用建议的 end node 重试也同样失败,再次确认根本原因在于 LayerNormalization / Transpose 处理,而非 end node 选择问题。

---

## 根本原因 (与 3 月相同)

DFC ONNX parser 仍然无法在 `LayerNormalization` 算子的输入张量不符合预期的 NCHW 格式时正确进行轴转换。相关的调用链现在是:

```
_create_layer_normalization_layer
  → get_layer_normalization_info
    → _convert_axes_to_nhwc
      → IndexError: list index out of range
```

对于 ConvNeXt 特别是,在多个 `Transpose` 节点 (`token_5` 至 `token_34`) 上额外发生的 `UnsupportedShuffleLayerError` 表明,该架构所使用的 channels-last 模式的 Transpose 算子处理也仍然不完整。

简而言之:**新的代码路径存在,但它还无法处理原本失败的情况。**

---

## 请求 (与 3 月相同)

3 月帖子中的两项请求仍然完全有效:

### 1. 修正 `_convert_axes_to_nhwc` 以支持多维 `LayerNormalization`

该方法现在可以被调用到了 (良好),但轴映射逻辑本身在非 NCHW 输入张量时失败。SwinV2、ViT、ConvNeXt 等现代 Transformer 架构全部依赖这个正确运作。

### 2. Hailo-10H 用的 ONNX Runtime Execution Provider

这会使完整的 DFC 转换成为可选项,并能结构性地解决这类问题。许多社群用户会受益于能在 Hailo-10H 上直接执行未经修改的 ONNX 模型的能力,即使吞吐量低于完全量化的 HEF。

---

## 关于 "ONNX Runtime Hailo Pipeline" 组件的说明

DFC v5.3.0 的发行说明中提到了一个 "ONNX Runtime Hailo Pipeline" 组件。如果这个组件能让 WD-Tagger 推理在 Hailo-10H 上**不需要完整 DFC 转换**就能执行 (即作为 ONNX Runtime execution provider 将支持的子图委派给 NPU),我会非常感激能获得关于正确方法的官方指导。

具体而言:

- 这个组件是否被定位为 DFC 目前无法解析的模型的前进路径?
- 是否需要部分 HEF (将可解析的子图编译成 HEF,其余通过 ORT 在 CPU 上执行)?
- 是否有针对 Transformer 类 ONNX 模型使用此组件的示例代码或教程?

---

## 重现步骤

重现这些结果的确切步骤:

```bash
# 1. 在干净的 Python venv 中设置 DFC v5.3.0
python3.11 -m venv venv
source venv/bin/activate
pip install hailo_dataflow_compiler-5.3.0-py3-none-linux_x86_64.whl

# 2. 下载三个 WD-Tagger ONNX 模型
for variant in swinv2 vit convnext; do
  huggingface-cli download \
    "SmilingWolf/wd-${variant}-tagger-v3" \
    model.onnx --local-dir "./wd-${variant}-tagger-v3"
done

# 3. 尝试解析每个模型
for variant in swinv2 vit convnext; do
  hailo parser onnx "./wd-${variant}-tagger-v3/model.onnx" \
    --hw-arch hailo10h \
    --tensor-shapes input_1:1,448,448,3 2>&1 | tee "${variant}_5.3.0.log"
done
```

每次执行的完整错误日志可根据需求提供。

---

## 测试环境

| 项目 | 详情 |
|---|---|
| OS | Ubuntu 24.04 (WSL2) |
| CPU | AMD Ryzen 5 5600X |
| RAM | 151 GB |
| Python | 3.11 |
| DFC | 5.3.0 |
| 模型 | `SmilingWolf/wd-{swinv2,vit,convnext}-tagger-v3` (HuggingFace) |
| 标定数据 | 500 张 ComfyUI / SD 输出 (未使用 — 从未到达量化步骤) |

---

## 结语

DFC v5.3.0 中可见的开发努力 (`_create_layer_normalization_layer`、onnxsim 重试流程、end node 推荐) 确实令人鼓舞 — 这正是社群一直期待的那种进展。剩下的差距在于 `_convert_axes_to_nhwc` 的实际实现,它现在可以被到达,但对于这些模型还不正确。

我会在每个 DFC 版本发布后继续重新测试,并在情况改变时发布后续报告。如果有来自 Hailo 的人读到这篇文章并希望获得完整的错误日志、ONNX 模型 SHA-256 哈希值或最小重现器,我很乐意提供。

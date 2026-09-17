# Hailo-10H Ecosystem Assessment

**Created**: 2026-03-19
**Target**: Hailo-10H (AI HAT 2 for Raspberry Pi 5)
**HailoRT**: v5.2.0
**DFC**: v5.2.0
**Purpose**: Document the Hailo-10H development experience in this project, and organize the realistic constraints and future outlook

---

## Overall Assessment

**The hardware is excellent. The software ecosystem is critically lacking.**

The Hailo-10H is an NPU with 40 TOPS of inference performance, and the hardware potential is more than sufficient. However, because the software toolchain is closed and immature, developers **effectively cannot** freely bring in and run their own models.

In this project, we pursued multi-faceted use of the Hailo-10H across CLIP semantic search, YOLO object detection, LLM/VLM chat, Whisper speech recognition, and a distributed tagger server. Everything that runs stably uses **pre-compiled HEF files downloaded from Hailo's official Model Zoo**, and we have **never** successfully converted an ONNX model to HEF on our own.

---

## Implementation Status in This Project

### Working Features (All Using Official HEF Downloads)

| Feature | API Used | HEF Source |
|---------|----------|------------|
| CLIP Image Encoder | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| YOLO Object Detection | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| LLM Chat | `hailo_platform.genai.LLM` | Hailo GenAI Model Zoo |
| VLM Image+Text Inference | `hailo_platform.genai.VLM` | Hailo GenAI Model Zoo |
| Whisper Speech Recognition | `hailo_platform.genai.Speech2Text` | Hailo GenAI Model Zoo |

### Features That Could Not Be Made to Work (HEF Conversion Failure)

| Feature | What Was Attempted | Result |
|---------|--------------------|--------|
| WD-Tagger (SwinV2) | ONNX to HEF conversion | DFC failed to handle LayerNormalization |
| WD-Tagger (ViT) | ONNX to HEF conversion | Same as above |
| WD-Tagger (ConvNeXt) | ONNX to HEF conversion | DFC failed to handle Transpose operations |

### Notable Implementation Details

In this project, all features were implemented by **directly calling** the `hailo_platform` wheel's Python API. Neither hailo-ollama nor hailo-apps were used.

The following in particular were built in-house before Hailo officially provided equivalent functionality:

- **VDevice Exclusive-Access Device Manager** -- Automatic switching between CLIP/YOLO/LLM/VLM/S2T on a single VDevice. hailo-apps has no device sharing mechanism
- **Multi-Backend Fallback** -- Transparent automatic switching across Hailo, CoreML, and ONNX Runtime
- **uint8 Dequantization Pipeline** -- Restoring float32 values from `quant_info` scale/zero_point
- **LAN Distributed Inference Architecture** -- Work-stealing parallel tagging across multiple machines

This development was carried out with **virtually no API documentation**. The InferModel API's input/output specifications, buffer size requirements, and quantization parameter retrieval methods were all figured out from error messages and source code inference.

---

## Issues with the Hailo Dataflow Compiler (DFC)

### What Is DFC?

A compiler for converting ONNX / TensorFlow models into HEF (Hailo Executable Format) for the Hailo-10H. It runs on x86_64 Linux and converts models through the following pipeline:

```
model.onnx → HAR (float32) → Optimization → Quantization (INT8) → Compilation → model.hef
```

### The Reality

**DFC can only reliably convert architectures that Hailo has pre-validated for its own Model Zoo.**

Conversion attempts in this project (2026-03-06, DFC v5.2.0):

| Model | Size | Error | Stage Reached |
|-------|------|-------|---------------|
| wd-swinv2-tagger-v3 | 446 MB | `IndexError` in `_convert_axes_to_nhwc` | Before optimization |
| wd-vit-tagger-v3 | 362 MB | Same as above | Before optimization |
| wd-convnext-tagger-v3 | 377 MB | `UnsupportedShuffleLayerError` | Before optimization |

All 3 models failed at the parser level **before even reaching the optimization stage**. 500 calibration images were prepared but never even used.

### Root Cause

DFC's ONNX parser cannot handle the following operators:

- `LayerNormalization` (axis conversion on multi-dimensional tensors)
- `Transpose` (channels-last/first conversion patterns)

These are fundamental building blocks of Transformer-based architectures (SwinV2, ViT, ConvNeXt, etc.) and are used by the vast majority of mainstream models since 2022.

### DFC's Effective Coverage

| Architecture | DFC Support | Basis |
|-------------|-------------|-------|
| ResNet, MobileNet, and other CNN-based | Supported | Numerous entries in Model Zoo |
| YOLO v5/v8/v11 | Supported | HEF available in Model Zoo |
| CLIP ViT (Hailo version) | Supported | HEF available in Model Zoo (converted by Hailo) |
| SwinTransformer V2 | Not supported | LayerNorm conversion failure |
| Vision Transformer (generic) | Not supported | LayerNorm conversion failure |
| ConvNeXt | Not supported | Transpose conversion failure |

> **Note**: The reason CLIP ViT exists in the Model Zoo is likely because Hailo performed special handling internally (manual graph transformations or custom parsers). Even the same ViT architecture fails when a regular user attempts conversion with DFC.

---

## Issues with the HEF Format

- **Binary specification is not public** -- Hailo has not published documentation for the format
- **No generation method other than DFC** -- It is impossible to create HEF files with third-party tools
- **Reverse engineering is also impractical** -- Requires knowledge of the NPU's instruction set and dataflow architecture

In other words, models that DFC cannot convert **simply cannot be run on the Hailo-10H, period**. No alternative path exists.

---

## Development Toolchain Assessment

### hailo_platform (Python SDK)

| Item | Assessment |
|------|-----------|
| InferModel API | Works, but documentation is severely lacking |
| GenAI API (LLM/VLM/S2T) | Relatively easy to use, though many undocumented behaviors |
| Python wheel distribution | Not on PyPI. aarch64 wheel must be built from source |
| Error messages | Minimal. Difficult to identify the cause of buffer size mismatches |
| VDevice management | Exclusive access only. No simultaneous multi-model usage |

### Undocumented Behaviors Discovered During Development

1. **InferModel API is the correct one** -- The legacy VStreams API (`InferVStreams`, `ConfigureParams.create_from_hef`) returns `HAILO_NOT_IMPLEMENTED` on the Hailo-10H
2. **Output is uint8 quantized** -- Allocating the buffer as float32 causes `buffer size mismatch`. You must allocate as uint8 and dequantize afterward
3. **`input()`/`output()` are properties** -- Not methods (inconsistent with other Hailo APIs)
4. **Retrieving `quant_info`** -- scale/zero_point can be obtained via `infer_model.output().quant_info`, but no documentation explains this
5. **Mutual exclusion with hailo-ollama** -- hailo-ollama must be stopped while VDevice is in use. The error message makes the cause hard to identify

---

## Comparison with Competing Products

### Ryzen AI (XDNA) NPU

| Item | Hailo-10H | Ryzen AI (XDNA) |
|------|----------|-----------------|
| Performance | 40 TOPS | 16-50 TOPS (varies by generation) |
| Bringing your own models | Must convert via DFC; usually fails | **ONNX Runtime supports it directly** |
| Developer experience | Proprietary toolchain, lacking documentation | `pip install onnxruntime-directml` and you're done |
| Ecosystem | Closed, Model Zoo dependent | ONNX / DirectML / Microsoft collaboration |
| Installed base | Pi + AI HAT, USB dongle (planned) | **Already built into millions of laptops** |

Integration with Ryzen AI is as simple as:

```python
import onnxruntime as ort
session = ort.InferenceSession("model.onnx", providers=["DmlExecutionProvider"])
```

The same thing is impossible on the Hailo-10H. No ONNX Runtime Execution Provider exists.

### NVIDIA CUDA

| Item | Hailo-10H | NVIDIA CUDA |
|------|----------|-------------|
| Bringing your own models | Via DFC; mostly fails for non-Model Zoo models | ONNX / PyTorch / TensorFlow just work |
| Toolchain | Immature and semi-closed | Mature, open, extensively documented |
| Developer community | Extremely small | World's largest |
| Price range | Affordable (~$70) | Expensive ($200-$2000+) |

Hailo's only advantage is **price and power consumption**.

---

## Relationship with hailo-apps (October 2025)

### Overview of hailo-apps

An official application collection released by Hailo in October 2025. It includes over 20 sample applications:

- GenAI: voice_assistant, vlm_chat, agent_tools_example, whisper
- Pipeline: object detection, pose estimation, face recognition, CLIP classification, OCR
- Standalone: Python/C++ HailoRT learning demos

### Comparison with This Project

| Item | hailo-apps | This Project |
|------|-----------|--------------|
| VLM support | vlm_chat app | Direct implementation using `hailo_platform.genai.VLM` |
| CLIP | clip app | Integrated as a semantic search system |
| LLM | simple_llm_chat | Integrated as a GenAI Extension |
| Whisper | simple_whisper_chat | Integrated as a Speech-to-Text Extension |
| Device management | None (assumes single-app usage) | **Exclusive-access device manager (automatic CLIP/YOLO/LLM/VLM/S2T switching)** |
| Backend fallback | None | **Automatic Hailo, CoreML, ONNX switching** |
| Distributed inference | None | **LAN distributed work-stealing** |
| Integration level | Individual demo apps | Single integrated WebUI application |

This project had already built functionality equal to or exceeding hailo-apps using the low-level API from the `hailo_platform` wheel before hailo-apps was released.

---

## Future Outlook

### Short-Term (Realistic)

- **ONNX Runtime + LAN distribution is the only practical solution** -- Operating via the distributed tagger server's ONNX backend
- Limit Hailo-10H usage to purposes where official HEF files exist (YOLO, CLIP, LLM, Whisper)
- Give up on NPU execution of custom models

### Mid-Term (Hopeful)

- ASUS and others release USB dongles with Hailo-10H -- user base grows
- Growing user base may create pressure on Hailo to improve their tools
- Future DFC versions may add Transformer architecture support

### Long-Term (Structural Challenges)

- Unless Hailo provides an ONNX Runtime EP, they will lose to Ryzen AI (XDNA) in the developer ecosystem
- Even if hardware becomes widespread via USB dongles, without software flexibility it remains nothing more than "a dongle that runs fast YOLO"
- The 40 TOPS potential continues to be usable with only the few dozen models in the Model Zoo

---

## Conclusion

The Hailo-10H has excellent hardware performance at 40 TOPS, but due to the closed nature and immaturity of its software ecosystem, it is **effectively impossible** for developers to freely bring in and utilize their own models.

In this project, we built integrated software exceeding Hailo's official application collection (hailo-apps) while figuring out undocumented APIs through trial and error. Even so, NPU execution of a custom model (WD-Tagger) could not be achieved due to DFC limitations.

**"The tooling is so insufficient that development is effectively impossible"** -- this is the honest conclusion after months of Hailo-10H development.

---

## Related Documents

- [`HAILO_SEMANTIC_SEARCH_DEVLOG.md`](./HAILO_SEMANTIC_SEARCH_DEVLOG.md) -- CLIP semantic search development log (Phase 1-12+)
- [`ONNX_TO_HEF_CONVERSION_GUIDE.md`](./ONNX_TO_HEF_CONVERSION_GUIDE.md) -- DFC conversion guide (reference material)
- [`ONNX_TO_HEF_CONVERSION_REPORT.md`](./ONNX_TO_HEF_CONVERSION_REPORT.md) -- WD-Tagger conversion failure report
- [`CLIP_ONNX_DEVLOG.md`](./CLIP_ONNX_DEVLOG.md) -- CLIP ONNX fallback development log
- [`HAILO_DEVICE_CONTROL.md`](./HAILO_DEVICE_CONTROL.md) -- VDevice device management design
- [`../features/distributed-tagger-server.md`](../features/distributed-tagger-server.md) -- Distributed tagger server documentation

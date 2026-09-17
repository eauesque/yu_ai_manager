# DFC Conversion Follow-up: WD-Tagger Models on DFC v5.3.0

**Date**: 2026-04-06
**DFC Version**: 5.3.0
**Follow-up to**: [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md) (2026-03-06)
**Environment**: WSL2 (Ubuntu 24.04), x86_64

---

## Background

In March 2026 I reported that all three WD-Tagger variants
(SwinV2, ViT, ConvNeXt) failed at the parser stage under
Hailo Dataflow Compiler v5.2.0, before reaching the
quantization step. The original report is preserved at
[`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md).

I have now re-tested all three models under DFC v5.3.0.
This document is the follow-up.

---

## Results Summary

| Model | Size | DFC 5.2.0 Error | DFC 5.3.0 Error | Change |
|---|---|---|---|---|
| `wd-swinv2-tagger-v3` | 446 MB | `IndexError` in `_convert_axes_to_nhwc` | Same | **None** |
| `wd-vit-tagger-v3` | 362 MB | Same | Same (after onnxsim retry) | Retry flow added |
| `wd-convnext-tagger-v3` | 377 MB | `UnsupportedShuffleLayerError` | Same + additional `UnsupportedModelError` | **Errors increased** |

**All three models still fail at the parser stage.** The
quantization step (for which 500 calibration images were
prepared) remains unreachable, just as in the v5.2.0 run.

---

## What Changed in DFC v5.3.0

While the failures persist, the following improvements are
visible in DFC v5.3.0 compared to v5.2.0:

### 1. `_create_layer_normalization_layer` method added

This method did not exist in v5.2.0 at all. DFC v5.3.0 now
attempts to handle `LayerNormalization` operators explicitly
through a dedicated code path. This is a clear sign of
ongoing development effort.

However, the **internal implementation is incomplete**: the
method is called, but the call to `_convert_axes_to_nhwc`
inside it still raises `IndexError: list index out of range`
on the same tensor shapes that failed in v5.2.0.

### 2. onnxsim simplification + retry flow added

For ViT and ConvNeXt, DFC v5.3.0 now automatically simplifies
the input ONNX model using `onnxsim` and retries parsing.
The simplified model is saved as `model.sim.onnx` next to
the input. This is a useful new safety net for models with
redundant or convoluted ONNX graphs.

For these specific models, however, the retry **fails at
exactly the same point** as the original parse, because the
underlying issue is in `_convert_axes_to_nhwc`, not in the
ONNX graph structure.

### 3. End-node recommendation

For ConvNeXt, DFC v5.3.0 now produces a specific
recommendation for end nodes when the parser bails out, and
prompts the user to retry with those nodes pinned. This is
a thoughtful UX improvement.

The retry with the recommended end nodes also fails, again
because the root cause is in the LayerNormalization /
Transpose handling rather than in end-node selection.

---

## Root Cause (Unchanged from March)

The DFC ONNX parser still cannot correctly convert the axes
of `LayerNormalization` operators when the input tensor does
not follow the expected NCHW format. The relevant call chain
is now:

```
_create_layer_normalization_layer
  → get_layer_normalization_info
    → _convert_axes_to_nhwc
      → IndexError: list index out of range
```

For ConvNeXt specifically, the additional
`UnsupportedShuffleLayerError` on multiple `Transpose` nodes
(`token_5` through `token_34`) indicates that the Transpose
operator handling also remains incomplete for the
channels-last patterns this architecture uses.

In short: **the new code path exists, but it does not yet
handle the cases that originally failed.**

---

## Requests (Unchanged from March)

The two requests from the March post both still stand:

### 1. Fix `_convert_axes_to_nhwc` for multi-dimensional `LayerNormalization`

The method is now reachable (good), but the axis mapping
logic itself fails for non-NCHW input tensors. Modern
Transformer architectures (SwinV2, ViT, ConvNeXt) all
require this to work.

### 2. ONNX Runtime Execution Provider for Hailo-10H

This would make a full DFC conversion optional and resolve
this class of issue structurally. Many community users would
benefit from being able to run unmodified ONNX models
directly on Hailo-10H, even at lower throughput than a
fully-quantized HEF.

---

## Note on the "ONNX Runtime Hailo Pipeline" Component

The DFC v5.3.0 release notes mention an "ONNX Runtime Hailo
Pipeline" component. If this can be used to run WD-Tagger
inference on Hailo-10H **without** a full DFC conversion
(i.e., as an ONNX Runtime execution provider that delegates
supported subgraphs to the NPU), I would very much
appreciate official guidance on the correct approach.

Specifically:

- Is this component intended to be a path forward for models
  that DFC cannot currently parse?
- Does it require a partial HEF (i.e., the parseable
  subgraphs compiled to HEF and the rest run on CPU via
  ORT)?
- Is there sample code or a tutorial showing how to use it
  with a Transformer-style ONNX model?

---

## Reproduction

The exact steps to reproduce these results:

```bash
# 1. Set up DFC v5.3.0 in a clean Python venv
python3.11 -m venv venv
source venv/bin/activate
pip install hailo_dataflow_compiler-5.3.0-py3-none-linux_x86_64.whl

# 2. Download the three WD-Tagger ONNX models
for variant in swinv2 vit convnext; do
  huggingface-cli download \
    "SmilingWolf/wd-${variant}-tagger-v3" \
    model.onnx --local-dir "./wd-${variant}-tagger-v3"
done

# 3. Attempt parsing each model
for variant in swinv2 vit convnext; do
  hailo parser onnx "./wd-${variant}-tagger-v3/model.onnx" \
    --hw-arch hailo10h \
    --tensor-shapes input_1:1,448,448,3 2>&1 | tee "${variant}_5.3.0.log"
done
```

The full error logs from each run are available on request.

---

## Test Environment

| Item | Detail |
|---|---|
| OS | Ubuntu 24.04 (WSL2) |
| CPU | AMD Ryzen 5 5600X |
| RAM | 151 GB |
| Python | 3.11 |
| DFC | 5.3.0 |
| Models | `SmilingWolf/wd-{swinv2,vit,convnext}-tagger-v3` (HuggingFace) |
| Calibration data | 500 ComfyUI / SD outputs (unused — never reached quantization step) |

---

## Closing

The development effort visible in DFC v5.3.0
(`_create_layer_normalization_layer`, the onnxsim retry
flow, end-node recommendations) is genuinely encouraging —
this is exactly the kind of progress the community has been
hoping to see. The remaining gap is the actual implementation
inside `_convert_axes_to_nhwc`, which is now reachable but
not yet correct for these models.

I will continue to retest with each DFC release and post
follow-ups as the situation changes. If anyone from Hailo
reads this and would like the full error logs, ONNX model
SHA-256 hashes, or a minimal reproducer, I'm happy to
provide them.

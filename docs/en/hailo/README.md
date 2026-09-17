# Hailo-10H AI Hat+ Development Documentation

Implementation records for AI inference using Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H).

This documentation shares practical knowledge gained through real development in areas where official documentation is insufficient.

## Document Index

| File | Description |
|------|-------------|
| [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) | HailoRT 5.2.0 → 5.3.0 migration notes: API diff, device node rename (`/dev/h1x-0`), HEF compatibility, smoke-test script |
| [VDEVICE_SHARING_PATTERN.md](VDEVICE_SHARING_PATTERN.md) | Implementation pattern for a shared VDevice manager that lets multiple models (YOLO/CLIP/LLM/VLM/Whisper) coexist in a single process |
| [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) | Pi 5 CMA allocation limits under `numa=fake=8`. Why `cma=1G` silently fails, the verified ceiling and recommended value `cma-512` (`dtoverlay=cma,cma-512` in `config.txt`), Hailo GenAI memory requirements, `VDevice.release()` CMA non-return behavior |
| [HAILO_SEMANTIC_SEARCH_DEVLOG.md](HAILO_SEMANTIC_SEARCH_DEVLOG.md) | CLIP semantic search development log. Per-phase implementation records, problems encountered and solutions |
| [HAILO_DEVICE_CONTROL.md](HAILO_DEVICE_CONTROL.md) | Hailo device control methods, VDevice management, exclusive access control, model switching |
| [ONNX_TO_HEF_CONVERSION_GUIDE.md](ONNX_TO_HEF_CONVERSION_GUIDE.md) | ONNX to HEF conversion procedure. Dataflow Compiler, quantization, troubleshooting |
| [ONNX_TO_HEF_CONVERSION_REPORT.md](ONNX_TO_HEF_CONVERSION_REPORT.md) | Conversion verification report (DFC v5.2.0). Detailed failure analysis for the 3 WD-Tagger variants |
| [WD_TAGGER_DFC_5_3_0_FOLLOWUP.md](WD_TAGGER_DFC_5_3_0_FOLLOWUP.md) | DFC v5.3.0 follow-up. Re-test of the same 3 WD-Tagger models (still failing), plus the v5.3.0 improvements observed (new `_create_layer_normalization_layer`, onnxsim retry flow, end-node recommendation) |
| [CLIP_ONNX_DEVLOG.md](CLIP_ONNX_DEVLOG.md) | CLIP ONNX multi-backend development log. Fallback for environments without Hailo hardware |
| [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) | **Structural constraints and measurements of the CMA leak**. `VDevice.release()` does not reclaim it, there is a continuous leak during inference (~14 MB/min), and it is **not reclaimed by child-process kill, process exit, or module unload either** (independently measured twice in the Phase 0 PoC; only +8 MB recovered after SIGTERM + a 30-second wait). The only reliable recovery method is rebooting the Pi itself **(old conclusion. Corrected in [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 following a retest on HailoRT / driver 5.4.0)** |
| [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) | **Correction and retest of the CMA leak verdict above**. A/B comparison of the official vanilla build against a `FOLL_LONGTERM`-fixed build on HailoRT / driver 5.4.0, correcting the earlier verdict, which had been a misjudgment based solely on the absolute `CmaFree` recovery amount after the first HEF load. Includes the v5.3.0 → v5.4.0 source diff, pitfalls in the self-built procedure, and measured data |
| [HAILO_AUTO_REBOOT_PHASE05.md](HAILO_AUTO_REBOOT_PHASE05.md) | Operations guide for the automatic-reboot policy adopted in response to the above. Observation phase (records `would_fire` only, without rebooting), decision thresholds, and the rationale for the default `mode = "off"` |
| [HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md](HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md) | Runbook for the same phase in this environment. Procedures for starting, checking, and concluding the observation |
| [HAILO_LLM_SUBPROCESS_DEVLOG.md](HAILO_LLM_SUBPROCESS_DEVLOG.md) | Implementation log resolving the issue where the Quart event loop freezes on the GIL during cold_load (~71 seconds), by isolating LLM chat inference in a subprocess |
| [HAILO_10H_ECOSYSTEM_ASSESSMENT.md](HAILO_10H_ECOSYSTEM_ASSESSMENT.md) | Hailo-10H ecosystem assessment (as of 2026-03-19, HailoRT/DFC v5.2.0) |

## Important Known Issues

### Environment / Raspberry Pi 5

- **The CMA ceiling on Pi 5 (8 GB) is 512 MB, set in `config.txt`**: The default kernel applies `numa=fake=8`, splitting RAM into 8 × 1 GB NUMA nodes. CMA must fit within a single node boundary, so `cma-1024` and `cma-768` silently fail (`CmaTotal=0` with no kernel panic). **`cma-512` is the verified ceiling and the recommended value** (re-verified via overlay on 2026-05-16, `CmaTotal: 524288 kB`). Due to a 2026-05 firmware regression, use `dtoverlay=cma,cma-512` in `/boot/firmware/config.txt` rather than the `cma=` cmdline parameter. See [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) for details
- **Always verify CMA after reboot**: `grep CmaTotal /proc/meminfo` — a value of 0 means the setting was silently ignored
- **`VDevice.release()` does not return CMA**: CMA is retained for the lifetime of the OS session. Treat VDevice as a session-scoped singleton. **Not reclaimed even by a process restart** — it has been independently measured twice in the Phase 0 PoC that it is not reclaimed by child-process kill, process exit, or module unload (only +8 MB recovered after SIGTERM + a 30-second wait, versus an expected ≥250 MB). The only reliable recovery method is `sudo reboot` on the Pi itself (a PCIe power-cycle). See [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) for details and the adopted mitigation. **Correction**: This section is based on earlier measurements. The A/B retest on HailoRT / driver 5.4.0 did not reproduce a practical CMA leak, and this has been corrected in [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8
- **`numa=fake=8` affects Node.js installation**: The per-NUMA-node memory (1 GB) is misdetected as total RAM, causing npm/node installers to abort. Reported upstream as [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864)
- **Python wheel requires source build**: No aarch64 wheel is available on PyPI or the Hailo Developer Zone
- **Mutual exclusion with hailo-ollama**: hailo-ollama must be stopped while VDevice is in use
- **VDevice leak on process exit**: Check with `lsof /dev/hailo*` and resolve with `kill PID`

### VDevice / API

- **Use the InferModel API**: `VDevice.create_infer_model()` is the correct approach. The legacy VStreams API (`InferVStreams`, `ConfigureParams.create_from_hef`) returns `HAILO_NOT_IMPLEMENTED` on Hailo-10H
- **InferModel only supports simple models**: Single-input YOLO HEF works, but `configure()` returns `HAILO_INVALID_ARGUMENT` for 2-input 4-output Whisper HEF. Use GenAI SDK for complex models
- **VDevice maps to one physical device**: Creating two `VDevice()` instances simultaneously causes `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- **Fully release VDevice when switching models**: Simply setting Python references to `None` is insufficient. Explicitly release the physical device with `VDevice.release()` before creating a new VDevice
- **`set_format_type(FormatType.FLOAT32)` is unsupported in hailort 5.2.0**: The `format_type` attribute does not exist. Manually handle uint8 quantization/dequantization or use GenAI SDK
- **Output is uint8 quantized**: Allocating the output buffer as float32 causes `buffer size mismatch`. Allocate as uint8 and convert to float32 using dequantization parameters (scale, zero_point)

### GenAI (LLM / VLM / Speech2Text)

- **`temperature=0.0` is rejected in HailoRT 5.3.0**: `LLM.generate()` raises `HAILO_INVALID_ARGUMENT` with `temperature=0`. Clamp before calling: `temperature = max(temperature, 0.01)`. Affects any OpenAI-compatible client that sends `temperature=0` by default
- **GenAI × 2 concurrent loading is possible**: LLM + Whisper-tiny can be loaded on the same VDevice simultaneously (confirmed on HailoRT 5.3.0). CMA headroom with both loaded: ~10 MB out of 256 MB. Whisper-base or larger will likely overflow
- **LLM + Whisper-tiny CMA budget**: ~246 MB combined (measured). See [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) for full model CMA figures

### Whisper (Speech Recognition)

- **Use GenAI SDK**: `hailo_platform.genai.Speech2Text` provides the full pipeline. Runs encoder+decoder entirely on the NPU
- **HEF is decoder-only**: `Whisper-Base.hef` has 2 inputs (encoder_features + token_embeddings) and 4 outputs (vocab split into 4). Does not work with InferModel API
- **GenAI SDK input**: Little-endian float32 (`<f4`), PCM audio data normalized to [-1,1]
- **ONNX fallback**: When GenAI SDK is unavailable, use HuggingFace ONNX models to run encoder+decoder on CPU

### YOLO (Object Detection)

- **Works with InferModel API**: Single-input HEF works without issues
- **ONNX fallback**: When Hailo is unavailable, `yolo11n.onnx` is automatically downloaded. Output `(1,84,8400)` is compatible with yolov8n
- **Initialization failure cooldown**: After engine initialization failure, retries are suppressed for 60 seconds

### Distributed Inference

- **Health check required**: Use `filter_available()` to verify remote node status before starting distributed processing
- **On remote failure**: Remaining items fall back to local processing. Recovered nodes are automatically detected in the next batch
- **Workload distribution**: The speed gap between GPU and NPU is large, making even distribution inefficient. Dynamic allocation based on throughput measurement is a future task

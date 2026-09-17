# Hailo-10H AI Hat+ 开发文档

使用 Raspberry Pi 5 + Hailo AI Hat+（Hailo-10H）进行 AI 推理的实现记录。

本文档分享了在官方文档不充分的领域中通过实际开发获得的实践知识。

## 文档索引

| 文件 | 描述 |
|------|------|
| [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) | HailoRT 5.2.0 → 5.3.0 迁移说明：API 差异、设备节点重命名（`/dev/h1x-0`）、HEF 兼容性、烟雾测试脚本 |
| [VDEVICE_SHARING_PATTERN.md](VDEVICE_SHARING_PATTERN.md) | 共享 VDevice 管理器的实现模式，让多个模型（YOLO/CLIP/LLM/VLM/Whisper）在单一进程中共存 |
| [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) | Pi 5 在 `numa=fake=8` 下的 CMA 分配限制：为什么 `cma=1G` 会无声失败、已确认的上限且推荐值为 `cma-512`（`config.txt` 中的 `dtoverlay=cma,cma-512`）、Hailo GenAI 内存需求、`VDevice.release()` 不返回 CMA 的行为 |
| [HAILO_SEMANTIC_SEARCH_DEVLOG.md](HAILO_SEMANTIC_SEARCH_DEVLOG.md) | CLIP 语义搜索开发日志。各阶段实现记录、遇到的问题及解决方案 |
| [HAILO_DEVICE_CONTROL.md](HAILO_DEVICE_CONTROL.md) | Hailo 设备控制方法、VDevice 管理、独占访问控制、模型切换 |
| [ONNX_TO_HEF_CONVERSION_GUIDE.md](ONNX_TO_HEF_CONVERSION_GUIDE.md) | ONNX 至 HEF 转换流程。数据流编译器、量化、故障排除 |
| [ONNX_TO_HEF_CONVERSION_REPORT.md](ONNX_TO_HEF_CONVERSION_REPORT.md) | 转换验证报告（DFC v5.2.0）。3 个 WD-Tagger 变体的详细失败分析 |
| [WD_TAGGER_DFC_5_3_0_FOLLOWUP.md](WD_TAGGER_DFC_5_3_0_FOLLOWUP.md) | DFC v5.3.0 后续跟进。重新测试相同的 3 个 WD-Tagger 模型（仍然失败），加上观察到的 v5.3.0 改进（新的 `_create_layer_normalization_layer`、onnxsim 重试流程、终端节点建议） |
| [CLIP_ONNX_DEVLOG.md](CLIP_ONNX_DEVLOG.md) | CLIP ONNX 多后端开发日志。对没有 Hailo 硬件的环境的回退支持 |
| [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) | **CMA 泄漏的结构性限制与实测**。`VDevice.release()` 不会回收 CMA，推理过程中持续泄漏（约 14 MB/分钟），并且**无论子进程 kill、进程退出还是模块卸载均无法回收**（Phase 0 PoC 独立实测两次，SIGTERM + 等待 30 秒仅回收 +8 MB）。唯一确实的回收手段是重启 Pi 本体 **（旧结论。经 HailoRT / driver 5.4.0 再试验，已在 [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 中订正）** |
| [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) | **上述 CMA 泄漏判定的订正与再验证**。在 HailoRT / driver 5.4.0 上对官方 vanilla 与 `FOLL_LONGTERM` 修复版进行 A/B 比较，订正了旧判定——旧判定仅凭首次 HEF 加载后 `CmaFree` 的绝对回收量得出，属于误判定。附带 v5.3.0 → v5.4.0 源码差异、自行构建步骤中的陷阱、实测数据 |
| [HAILO_AUTO_REBOOT_PHASE05.md](HAILO_AUTO_REBOOT_PHASE05.md) | 基于上述内容采用的自动 reboot 方案运行指南。观察阶段（仅记录 `would_fire` 而不重启）、判定阈值、默认 `mode = "off"` 的原因 |
| [HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md](HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md) | 同一阶段针对本环境的运行手册。观察的启动、确认、终止步骤 |
| [HAILO_LLM_SUBPROCESS_DEVLOG.md](HAILO_LLM_SUBPROCESS_DEVLOG.md) | 通过将 LLM chat 推理隔离到子进程（subprocess），解决 cold_load（约 71 秒）期间 Quart event loop 因 GIL 卡死问题的实现日志 |
| [HAILO_10H_ECOSYSTEM_ASSESSMENT.md](HAILO_10H_ECOSYSTEM_ASSESSMENT.md) | Hailo-10H 生态系统评估（截至 2026-03-19，HailoRT/DFC v5.2.0） |

## 重要已知问题

### 环境 / Raspberry Pi 5

- **Pi 5（8 GB）上的 CMA 上限为 512 MB，设置位置在 `config.txt`**：默认内核应用 `numa=fake=8`，将 RAM 分成 8 × 1 GB 的 NUMA 节点。CMA 必须落在单一节点边界内，因此 `cma-1024` 和 `cma-768` 会无声失败（`CmaTotal=0`，无内核崩溃）。**`cma-512` 是已确认的上限且为推荐值**（2026-05-16 通过 overlay 重新验证，`CmaTotal: 524288 kB`）。由于 2026-05 的 firmware 回归问题，应使用 `/boot/firmware/config.txt` 中的 `dtoverlay=cma,cma-512`，而非 cmdline 的 `cma=`。详见 [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md)
- **重启后始终验证 CMA**：`grep CmaTotal /proc/meminfo` — 值为 0 表示设置被无声忽略
- **`VDevice.release()` 不会返回 CMA**：CMA 在整个 OS 会话期间被保留。应将 VDevice 视为会话范围内的单例。**即使进程重启也不会回收** —— 无论子进程 kill、进程退出还是模块卸载，均不会回收，这一点已在 Phase 0 PoC 中独立实测两次（SIGTERM + 等待 30 秒仅回收 +8 MB，预期值 ≥250 MB）。唯一确实的回收手段是 Pi 本体的 `sudo reboot`（PCIe power-cycle）。详情及采用的对策参见 [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md)。**订正**：本项基于旧测量。经 HailoRT / driver 5.4.0 的 A/B 再试验，未再现实用上的 CMA 泄漏，已在 [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 中订正
- **`numa=fake=8` 影响 Node.js 安装**：每个 NUMA 节点的内存（1 GB）被误检为总 RAM，导致 npm/node 安装程序中止。已向上游报告为 [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864)
- **Python wheel 需要源码构建**：PyPI 或 Hailo Developer Zone 上无 aarch64 wheel 可用
- **与 hailo-ollama 互斥**：使用 VDevice 时必须停止 hailo-ollama
- **进程退出时 VDevice 泄漏**：用 `lsof /dev/hailo*` 检查，用 `kill PID` 解决

### VDevice / API

- **使用 InferModel API**：`VDevice.create_infer_model()` 是正确的方法。遗留的 VStreams API（`InferVStreams`、`ConfigureParams.create_from_hef`）在 Hailo-10H 上返回 `HAILO_NOT_IMPLEMENTED`
- **InferModel 仅支持简单模型**：单输入 YOLO HEF 可用，但对于 2 输入 4 输出 Whisper HEF，`configure()` 返回 `HAILO_INVALID_ARGUMENT`。复杂模型请使用 GenAI SDK
- **VDevice 映射到一个物理设备**：同时创建两个 `VDevice()` 实例会导致 `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`
- **切换模型时完全释放 VDevice**：仅将 Python 引用设为 `None` 是不充分的。在创建新 VDevice 之前，用 `VDevice.release()` 显式释放物理设备
- **hailort 5.2.0 中不支持 `set_format_type(FormatType.FLOAT32)`**：`format_type` 属性不存在。手动处理 uint8 量化/反量化，或使用 GenAI SDK
- **输出为 uint8 量化**：将输出缓冲区分配为 float32 会导致 `buffer size mismatch`。分配为 uint8 并使用反量化参数（scale、zero_point）转换为 float32

### GenAI（LLM / VLM / Speech2Text）

- **HailoRT 5.3.0 中 `temperature=0.0` 被拒绝**：`LLM.generate()` 以 `temperature=0` 抛出 `HAILO_INVALID_ARGUMENT`。调用前夹紧：`temperature = max(temperature, 0.01)`。影响任何默认发送 `temperature=0` 的 OpenAI 兼容客户端
- **GenAI × 2 并发加载成为可能**：LLM + Whisper-tiny 可以同时在同一 VDevice 上加载（在 HailoRT 5.3.0 上确认）。两者都加载的 CMA 余量：256 MB 中约 10 MB。Whisper-base 或更大的模型可能会溢出
- **LLM + Whisper-tiny CMA 预算**：约 246 MB（已测量）。参见 [PI5_NUMA_CMA_CONSTRAINTS.md](PI5_NUMA_CMA_CONSTRAINTS.md) 获取完整模型 CMA 数据

### Whisper（语音识别）

- **使用 GenAI SDK**：`hailo_platform.genai.Speech2Text` 提供完整的流程。编码器+解码器完全在 NPU 上运行
- **HEF 仅为解码器**：`Whisper-Base.hef` 有 2 个输入（encoder_features + token_embeddings）和 4 个输出（vocab 分成 4 个）。不适用于 InferModel API
- **GenAI SDK 输入**：小端 float32（`<f4`），PCM 音频数据归一化到 [-1,1]
- **ONNX 回退**：GenAI SDK 不可用时，使用 HuggingFace ONNX 模型在 CPU 上运行编码器+解码器

### YOLO（目标检测）

- **适用于 InferModel API**：单输入 HEF 可无问题使用
- **ONNX 回退**：Hailo 不可用时，自动下载 `yolo11n.onnx`。输出 `(1,84,8400)` 与 yolov8n 兼容
- **初始化失败冷却**：引擎初始化失败后，重试被抑制 60 秒

### 分布式推理

- **需要健康检查**：使用 `filter_available()` 在启动分布式处理前验证远程节点状态
- **远程失败时**：剩余项目回退到本地处理。恢复的节点在下一批中自动检测
- **工作负载分配**：GPU 与 NPU 之间的速度差距很大，使得均匀分配效率低下。基于吞吐量测量的动态分配是未来的任务

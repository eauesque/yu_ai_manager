# HailoRT 5.3.0 的 CMA 内存泄漏 — 确定诊断与操作限制

> **订正说明**：本文档是基于旧测量所记录的 CMA 泄漏诊断，其旧结论——`release()` 后 CMA 无法回收、推理过程中以约 14 MB/分钟持续泄漏、唯一确实的恢复手段是重启 Pi 本体——已被撤回。经 HailoRT/driver 5.4.0 再试验得出的最终判定已在 [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 中订正。请勿将本文档的旧结论作为当前的实用判定参考。

**创建日期**: 2026-05-17（在 v4.214.11 中发现并记录）
**影响范围**: Raspberry Pi 5 + Hailo-10H + `hailort==5.3.0`（通过 `hailo_platform.genai` 路径）
**症状**: 一旦加载 LLM，即使调用 `VDevice.release()` / `LLM.release()`，CMA 也几乎无法被回收。此外，推理过程中 CMA 也会持续泄漏。除了重新启动 Pi 本体之外，没有其他恢复手段。
**状态**: 已确认为驱动程序端的结构性限制。正在研究规避方法。

---

## 1. 确定诊断的依据

使用 `v4.214.10` 中引入的 CMA 事件记录器（`logs/hailo_cma.log`、`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`），于 2026-05-17 实测了以下序列。

### 1-1. 观测日志（原始数据）

`logs/hailo_cma.log`:

```text
2026-05-17T14:05:13+0900 event=vdevice_create_pre  cma_free_mb=392 pid=3237
2026-05-17T14:05:14+0900 event=vdevice_create_post cma_free_mb=393 pid=3237
2026-05-17T14:05:14+0900 event=acquire_pre  cma_free_mb=393 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:06:25+0900 event=acquire_post cma_free_mb=108 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
        ↓ 6 分钟的聊天使用（大约 5〜10 条消息的推理）
2026-05-17T14:12:36+0900 event=release_pre  cma_free_mb=24  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:12:36+0900 event=release_post cma_free_mb=25  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
```

### 1-2. 解读

| 阶段 | CmaFree 差值 | 含义 |
|---|---|---|
| `vdevice_create_pre` → `vdevice_create_post` | **+1 MB（≈ 0）** | VDevice 创建本身几乎不消耗 CMA |
| `acquire_pre` → `acquire_post`（Qwen3-1.7B-Instruct 加载） | **−285 MB** | 1 个 LLM 消耗 285 MB |
| `acquire_post` → `release_pre`（6 分钟推理） | **−84 MB / 6 min ≒ −14 MB/min** | **推理中也持续泄漏** |
| `release_pre` → `release_post`（LLM 卸载） | **+1 MB** | **`release()` 实际上不归还 CMA** |

### 1-3. 与先前假设的比较

这是 2026-05-16 创建的 `SQLCIPHER_MMAP_CORRUPTION.md` §7 及旧文档初始假设「VDevice 保持策略（我们的 `_maybe_reset_vdevice` 为空）放大了泄漏」的部分反证观测结果。由于 VDevice 创建 0 MB / release 0 MB，**即使改变保持策略（= 将 `_maybe_reset_vdevice` 改为每次重置），也不会有效果**。

---

## 2. 结构性限制

根据实测结果，HailoRT 5.3.0（社区版本，`hailo_platform.genai` API）存在以下三个同时发生的问题：

1. **`VDevice.release()` / GenAI 模型的 `release()` 不回收主机 CMA**（实测确认）
   - 在单一进程内，PCIe 驱动程序（`hailo1x_pci`）持续持有 DMA 区域，不会发生相当于 `munmap` 的操作
2. **推理中持续的 CMA 泄漏（约 14 MB/分钟）**（实测确认）
   - 今日观测：使用 Qwen3-1.7B-Instruct 的 6 分钟内损失了 84 MB
   - 与加载/卸载无关的独立路径。即使不卸载也会耗尽
3. **除 Pi 本体重启外，没有确认过可靠回收 CMA 的方法**（实测 + 社区报告）
   - 即使重新启动服务器进程（相当于 `systemctl restart yu-ai-manager`），由于 `hailo1x_pci` 在 PCIe 电源循环之前持续持有 DMA，也无法完全恢复。完整恢复需要 Pi 本体的 `sudo reboot`（本仓库的实测）
   - Hailo 社区中也有多个独立报告：<https://community.hailo.ai/t/hailo-10h-on-rpi5-undocumented-api-findings-dfc-conversion-failures-with-transformer-based-models-swinv2-vit-convnext/18979> 和 <https://community.hailo.ai/t/hailo-10h-throughput-degrades-irreversibly-within-minutes-of-continuous-use-125-41-fps-only-host-reboot-recovers/19218>（明确指出 `VDevice.release()` / 进程退出 / 驱动程序重新加载无法恢复，只有主机重启才能恢复）
   - 这已在 `acquire_genai` 的预拒绝错误消息中告知用户（`core/hailo_device_core/device_manager_genai.py::acquire_genai`，"a full system reboot is required"）

### 2-1. 「终止子进程是否可以归还 CMA？」：**实测反证**（2026-05-17 Phase 0 PoC）

旧版本（rev1）从理论上断定「Linux 内核在 `mm_struct` teardown 时回收 DMA 页面，因此终止子进程可以完整回收 CMA」，但**使用 Phase 0 PoC（`tools/diag_hailo_cma_reclaim.py`）实测的结果，两次独立确认终止子进程几乎不回收 CMA**。

**测量结果（第 2 次，严格版本）**：

| 测量点 | CmaFree | Δ |
|---|---:|---:|
| 基准线（PoC 开始前） | 503 MB | — |
| VDevice 创建后 | 372 MB | **-131 MB**（冷启动子进程中 VDevice 构建时消耗） |
| LLM 加载后 | 372 MB | 0 MB（LLM 在 VDevice DMA pool 内完结，无新增消耗） |
| SIGTERM 发送 + join 后 | 378 MB | +6 MB |
| **等待 30 秒后** | **380 MB** | **仅回收累计 +8 MB** |

预期回收 ≥250 MB，实测值仅 +8 MB（第 1 次偶发测量为 +1 MB）。这只是系统抖动级别，**没有发生有意义的 CMA 回收**。

**确定诊断**：

- `hailo1x_pci` 驱动程序以**驱动程序内部全局状态**而非用户进程的 `mm_struct` 管理 DMA pool（推定）
- `process exit`、`kill`、`module unload` 都不会回收（与社区报告一致）
- **唯一确认的回收手段是 Pi 本体的 `sudo reboot`（= PCIe 电源循环）** ← §2 第 3 行记载的实测事实

详细报告：`docs/superpowers/specs/codex-reviews/2026-05-17-hailo-subprocess-isolation-phase0-poc-result.md`

基于这个结果，`docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md` 被标记为 **REJECTED**，通过子进程隔离进行缓解的路线废止。改采 §4 (D) 的自动重启路线作为替代方案。

---

## 3. 操作上的含义

### 3-1. 「每次 Pi 重启 1 个模型」实际上是上限

- Pi 5（CMA 上限 512 MB，Pi 规格无法增加）+ Qwen3 系 LLM（285 MB）的组合：
    - 重启后立即 CmaFree ≒ 480 MB
    - 加载 1 个 LLM → CmaFree ≒ 190 MB
    - 数十分钟推理后 → CmaFree ≒ 50 MB 以下
    - **第 2 个模型的加载永久不可能**（需要 250+ MB 但剩余不足，即使 release 也不会归还）

### 3-2. LLM + VLM / LLM + S2T 无法同时使用

- VLM（llava 系，约 300 MB）、S2T（whisper-small，约 175 MB）与 LLM 切换使用的场景，在上述限制下，除非采用**加载 → 重启 → 加载**的流程，否则无法实现。
- **「对话中附加图片切换到其他模型」「对对话音频进行语音转文字」等多模型 UX 在 HailoRT 5.3.0 中在设计上无法成立**。

### 3-3. 长时间持续推理困难

- 14 MB/分钟的泄漏意味着即使 CmaFree 为 200 MB 时，14 分钟后减半，30 分钟后几乎耗尽。
- 超过 30 分钟的聊天会话在不插入 Pi 重启的情况下无法保持稳定。

---

## 4. 可采取的对策

按优先级和工时列举：

| 方案 | 效果 | 工时 | 副作用・风险 |
|---|---|---|---|
| ~~(A) 将 Hailo 操作隔离到子进程，定期终止让内核回收 CMA~~ | ❌ **REJECTED**（Phase 0 PoC 反证，两次重现）。终止后的回收量仅累计 +8 MB，假设不成立 | — | 不采用 |
| **(B) 将 `_CMA_ESTIMATES_MB` 更新为实测值 + 余量** | 提高预拒绝的精确度（减少假阳性加载尝试） | ✅ 立即可用，1 行 | 以 250 MB 假设勉强运作的现有用户将被拒绝，但那原本就已在失败 |
| **(C) `CmaFree < 80 MB` 时显示 UI 横幅 / `< 30 MB` 时在 error.log 记录 WARN** | 用户可以了解状况，提示 Pi 重启 | 中 | 警告疲劳 / 过度通知的风险 |
| **(D) 检测到 `CmaFree < 30 MB` 时向 supervisor 发送 SIGTERM** | 自动恢复（但由于需要 Pi 全体重启，通过 `systemctl reboot`） | 中 | 需要 supervisor 权限 / 其他作业中的连接中断 |
| **(E) 等待 HailoRT 修正 + 明确记录限制** | 成本 0 | 0 | 取决于 Hailo 的发布周期（数个月〜） |
| **(F) 向 Hailo 的问题追踪器 / 论坛提交修正请求** | 可能加速修正时机 | 小 | 响应速度取决于支持合同和社区状况 |

短期方针（v4.214.11 中实施）：**适用 (B) + 本文件（E 和 F 的出发点）**。
中期方针（另行 spec）：按照 **(C) UI 警告 → (A) 子进程隔离**的顺序考虑。
长期：监控 HailoRT 的发布，修正后更新本文件并解除限制。

---

## 5. 相关文件 / 代码

- `core/hailo_device_core/device_manager_genai.py::acquire_genai` — 预先 CmaFree 检查 + 面向用户的错误消息已明示本限制
- `core/hailo_device_core/device_helpers.py::_CMA_ESTIMATES_MB` — 按模型别的 CMA 需求量估计（v4.214.11 中 qwen 从 250 → 300 提升）
- `core/hailo_device_core/device_helpers.py::log_hailo_cma_event` — v4.214.10 中引入的测量仪器。本文件的实测数据也来自这里
- `core/hailo_device_core/device_manager_state.py::_maybe_reset_vdevice` — 在进程生命周期内持有 VDevice 的设计（空函数）。本实测结果确认，即使改为重置，也不会有助于 CMA 回收
- `docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05.md` — Phase 0.5 观测阶段的运维人员指南。使用 `mode=lazy` + `dry_run=true` 仅收集 `would_fire` 日志的流程
- `docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md` — Pi5 整体的 CMA 上限及各驱动程序（camera / KMS / Hailo / HEVC）的基准消耗量
- `docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md` — 迁移到 HailoRT 5.3.0 的经过与已知差异

---

## 6. 重现步骤（供 Hailo 问题报告使用）

向外部提交错误报告时的最小重现步骤：

```bash
# 1. 确认 Pi 重启后立即的基准线
grep CmaFree /proc/meminfo
# CmaFree: 480000 kB 前后

# 2. 启动服务器 + 加载第 1 个 LLM（例如：通过 /tools 的 GenAI 发送 1 条消息）
# 向 /api/llm/generate 或 /api/chat/send 发送 1 个请求

# 3. 确认 CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (-280 MB)

# 4. 卸载模型
curl -X POST http://127.0.0.1:5000/ext/hailo-genai/api/model/unload -d '{"model":"llm"}'

# 5. 确认 CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB（不归还 ← bug）

# 6. 尝试重新加载相同模型 / 其他模型 → 因 CMA 不足而拒绝
```

预期行为：步骤 5 中，CmaFree 应恢复到接近步骤 1 基准线的值（>400 MB）。
实际行为：只归还约 +1 MB，无法重新加载。

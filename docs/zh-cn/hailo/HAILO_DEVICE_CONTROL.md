# Hailo-10H 设备控制

## 概述

Hailo-10H NPU 可以**同时执行多个模型**。
内置的 ROUND_ROBIN 调度器会自动在模型之间分时共享硬件访问。

yu_ai_manager 维护一个共享的 VDevice，使 CLIP、YOLO、LLM、VLM、Speech2Text
可同时加载并进行推理。通过 `group_id` 也可与外部进程 (hailo-ollama) 共享。

## 架构

```
┌─────────────────────────────────────────────┐
│              Shared VDevice                  │
│         (group_id = YU_SHARED)               │
│                                              │
│  ┌─────────┐ ┌─────────┐ ┌───────────────┐  │
│  │  CLIP   │ │  YOLO   │ │  LLM (GenAI)  │  │
│  │InferMdl │ │InferMdl │ │  VLM / S2T    │  │
│  └─────────┘ └─────────┘ └───────────────┘  │
│                                              │
│     HailoRT ROUND_ROBIN Scheduler            │
└─────────────────────────────────────────────┘
```

- InferModel API (CLIP, YOLO) 和 GenAI API (LLM, VLM, S2T) 在同一 VDevice 上共存
- 所有模型必须创建在**同一个 VDevice 实例**上（创建在不同实例上将无法工作）

## 两种模式比较

| | Python SDK (Hailo VLM) | hailo-ollama-vlm (OpenAI 兼容) |
|---|---|---|
| 设备管理 | yu 的 device_manager | 外部 C++ 服务器 |
| 与 CLIP 搜索共存 | 可（同时动作） | 可（group_id 共享，v5.3.0+） |
| 推理速度 | 相同 | 相同 |
| 额外开销 | ~15ms | ~200-400ms (base64+HTTP) |
| 多客户端 | 不可 | 可能 |
| Flask 线程 | 推理中阻塞 | 仅 HTTP 等待 |

## VDevice 共享 (group_id)

### 进程内共享

`device_manager.py` 自动管理。所有模型共享同一个 VDevice。

可通过环境变量更改 group_id：
```bash
export HAILO_VDEVICE_GROUP_ID=MY_GROUP
```

默认值：`YU_SHARED`

### 与 hailo-ollama 共存 (v5.3.0+)

hailo-ollama v5.3.0 以后支持 `HAILO_OLLAMA_VDEVICE_GROUP_ID` 环境变量。
设置与 yu_ai_manager 相同的 group_id，即可让两个进程共享设备：

```bash
# yu_ai_manager 端
export HAILO_VDEVICE_GROUP_ID=SHARED

# hailo-ollama 端
HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED hailo-ollama
```

**注意**：yu_ai_manager 需要 HailoRT 5.2.0 以上才能使 group_id 生效。
hailo-ollama 需要 v5.3.0 以上才能接受 group_id。

## device_manager API

### 获取模型

```python
from core.hailo_device_core.device_manager import acquire_device, acquire_genai

# InferModel (CLIP, YOLO)
infer_model, configured, quant_params = acquire_device("clip", "/path/to.hef")

# GenAI (LLM, VLM, S2T)
llm = acquire_genai("llm", "/path/to.hef", lambda vd, p: LLM(vd, p))
```

- 同一 owner + 同一 HEF -> 复用现有 session
- 同一 owner + 不同 HEF -> 释放旧模型并创建新模型
- 不同 owner -> **共存**（旧模型不会被释放）

### 释放模型

```python
from core.hailo_device_core.device_manager import release_device, shutdown_all

release_device("clip")   # 仅释放 CLIP，其他继续运行
shutdown_all()            # 释放所有模型 + VDevice（进程退出时）
```

### 状态确认

```python
from core.hailo_device_core.device_manager import (
    get_active_owners, is_model_active,
    is_hailo_available, is_genai_available,
)

get_active_owners()       # ["clip", "yolo", "llm"]
is_model_active("clip")   # True
```

## 故障排除

### VDevice 创建错误

**症状**：`HAILO_OUT_OF_PHYSICAL_DEVICES(74)` 或 `Failed to create VDevice`

**原因**：其他进程以不同的 group_id 占用了设备

**处理方式**：
1. 确认 hailo-ollama 是否正在运行：
   ```bash
   ps aux | grep hailo-ollama
   ```
2. 统一 group_id 或停止进程：
   ```bash
   sudo systemctl stop hailo-ollama
   ```

### 设备未被释放

**处理方式**：
1. 重新启动 yu 的进程
2. 确认是否有僵尸进程：
   ```bash
   sudo lsof /dev/hailo* 2>/dev/null
   kill <PID>
   ```
3. 重置 Hailo 驱动程序：
   ```bash
   sudo systemctl restart hailort.service
   ```

## API 使用指南

| 模型结构 | 推荐 API | 原因 |
|---|---|---|
| 简单（单输入，YOLO 等） | `InferModel` | `create_infer_model()` + `configure()` 即可运行 |
| 复杂（双输入+，Whisper 等） | `GenAI SDK` | InferModel 会返回 `INVALID_ARGUMENT` |
| CLIP 编码器 | `InferModel` | 单输入单输出，没有问题 |
| LLM（qwen2.5 等） | `GenAI SDK` | 需要自回归解码 |

## 历史记录

- **v4.61.0**：迁移至共享 VDevice 方式。废除排他 acquire/release，支持 CLIP + YOLO + LLM 同时运行。
- **v4.60.1**：统一所有消费者通过 device_manager（排他方式）。
- **v4.60.0 及更早**：各消费者各自调用 VDevice()，频繁发生冲突错误。

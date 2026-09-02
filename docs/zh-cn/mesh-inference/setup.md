# 分布式推理设置指南

> 目标版本：v4.67.0 及更高版本

## 什么是分布式推理?

多个 yu_ai_manager 节点协作来**并行分布**推理处理（例如标签、CLIP、YOLO 和语音识别）的功能。您可以在多台机器间共享大文件扫描，或将标签任务委托给搭载 Hailo NPU 的 Pi5。

```
┌──────────────┐   图像批处理   ┌──────────────┐
│    本地      │ ──────────────► │  Pi5 (Hailo) │  标签器 × 200 张
│   (扫描)     │ ──────────────► │  GPU 机器    │  标签器 × 300 张
│              │ ──────────────► │    本地      │  标签器 × 100 张
└──────────────┘   工作          └──────────────┘
                  盗取
```

---

## 前置条件

每个节点需要满足以下条件：

1. yu_ai_manager 正在运行
2. **LAN Cowork 扩展已启用** (`"extensions": {"builtin-lan-cowork": {"enabled": true}}`)
3. 节点已**互相配对** ([节点认证指南](../lan-cowork/peer-auth.md))
4. 要使用的推理引擎已在每个节点上配置 (ONNX / Hailo / Whisper 等)

---

## 设置步骤

### 步骤 1：在每个节点上启用 LAN Cowork

在所有节点的 `config.json` 中：

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

重启后，节点将通过 mDNS 自动相互发现。

### 步骤 2：完成配对

在所有节点对之间执行配对（双向）。
详情：[节点 PIN 认证和令牌配对](../lan-cowork/peer-auth.md)

### 步骤 3：验证分布式推理矩阵

在任意节点上打开 `/mesh-inference`。

已配对的节点显示为行，推理类型显示为列：

| 节点 | 标签器 | clip | yolo | whisper |
|---|---|---|---|---|
| 本地 | ☑ 启用 | ☑ 启用 | ☑ 启用 | ☑ 启用 |
| pi5-hailo | ☑ 启用 | ☑ 启用 | — 不可用 | — 不可用 |
| gpu-win | ☑ 启用 | ☑ 启用 | ☑ 启用 | ☑ 启用 |

- **☑ 启用**：使用此节点进行推理
- **☐ 禁用**：跳过（可手动切换）
- **—**：此节点没有目标推理引擎（无法操作）

### 步骤 4：验证操作

运行标签批处理，确认日志显示使用了多个节点：

```
[mesh-inference] dispatching tagger: 600 items to 3 peers
[mesh-inference] pi5-hailo: processed 200, errors 0
[mesh-inference] gpu-win:   processed 300, errors 0
[mesh-inference] local:     processed 100, errors 0
```

---

## 推理类型要求

| 类型 | 所需引擎 | 描述 |
|---|---|---|
| `tagger` | ONNX（WD14 等）或 Hailo NPU | 图像的 Danbooru 风格标签 |
| `clip` | ONNX CLIP 或 Hailo | 图像语义嵌入向量（用于语义搜索） |
| `yolo` | ONNX YOLO | 图像中的物体检测 |
| `whisper` | faster-whisper 或远程 | 音频/视频的语音转文字 |

没有配置引擎的节点将对该类型显示"—"，且不会为该类型路由。

---

## 角色设计示例

### 示例 1：将 Pi5 + Hailo NPU 专用于标签

仅为标签分配 Pi5，减少其他节点的负载。

矩阵配置：
- Pi5：标签器 ☑，其他 ☐
- 本地：clip ☑、yolo ☑、whisper ☑、标签器 ☐（委托给 Pi5）

### 示例 2：快速批量扫描

同时在 GPU 机器和本地机器上启用标签器，通过工作盗取自动共享文件。无需手动分割。

### 示例 3：仅本地模式（临时）

在 `/mesh-inference` 中点击"仅本地模式"按钮，一次性禁用所有远程节点。在网络断开时很有用。

---

## 故障排除

### 节点未出现在矩阵中

1. 使用 `/api/lan/peers` 检查节点是否被识别
2. 确认配对已完成 ([peer-auth.md](../lan-cowork/peer-auth.md))
3. 检查远程节点上 LAN Cowork 是否已启用

### 到特定节点的路由不工作

- 检查矩阵中该节点的目标类型是否显示 ☑
- 检查 `/api/lan/peers` 响应中该节点是否显示 `status: "online"`
- 检查是否收到远程节点的心跳（在日志中搜索 `heartbeat`）

### 所有处理都在本地进行

如果所有远程节点离线或禁用，将自动进行本地回退。
这是正常操作（不是错误）。

### `no_enabled_peers` 错误

该类型在所有节点上都被禁用。
在矩阵中至少为该类型启用 1 个节点。

---

## 相关文档

- [分布式推理架构](overview.md) — 工作盗取和 DisableAwareStrategy 的内部设计
- [分布式推理矩阵](toggle.md) — WebUI 操作详情
- [LAN Cowork 概览](../lan-cowork/README.md) — LAN Cowork 整体配置
- [节点 PIN 认证](../lan-cowork/peer-auth.md) — 配对过程

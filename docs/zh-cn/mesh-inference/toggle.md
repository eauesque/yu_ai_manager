# 分布式推理矩阵

**版本**: v4.67.0 及以上

## 概述

在 `/mesh-inference` 页面中，可以对参与 mesh inference 的每个节点按推理类型进行启用/禁用切换。对象为 tagger、clip、yolo、whisper 共 4 种类型。

借此功能，可以将 Pi5 的 Hailo NPU 专用于 tagger、将 GPU 主机用于处理 clip 等角色分配，无需修改配置文件。

## 使用方法

1. 从导航栏点击"🕸️ 分布式推理"
2. 点击矩阵表格中的各单元格切换启用/禁用
   - ☑ = 启用（在该节点使用该推理类型）
   - ☐ = 禁用（跳过该节点）
   - — = 该节点不提供该类型（不可操作）
3. 点击"仅本地模式"按钮可一键禁用所有远程节点
4. 状态会自动持久化到 `data/mesh_inference_state.json`

## 行为

- 离线节点的设置也会保留（重新连接时自动应用）
- "仅本地模式"仅在本地至少有一个启用的类型时可用
- 如果所有节点的 tagger 都被禁用时启动 tagger 批处理，会立即以 `no_enabled_peers` 错误失败
- mDNS 重新检测导致节点临时离开和恢复时，禁用状态仍然保持

## 与现有 YOLO 分布式推理复选框的关系

YOLO 检测页面的"分布式推理"复选框为向后兼容而保留，组合行为如下：

| yoloDistributed | 矩阵 yolo 列 | 实际行为 |
|---|---|---|
| ✅ ON | 所有节点启用 | 与以往相同，在所有节点分布式处理 |
| ✅ ON | 部分禁用 | 跳过被禁用的节点 |
| ❌ OFF | 忽略 | 仅本地（绕过 router） |

## 相关

- API 参考: [api/mesh-inference.md](../api/mesh-inference.md)
- LLM Router（不同层）: [../llm-router/](../llm-router/)

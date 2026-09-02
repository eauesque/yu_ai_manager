# LLM Router WebUI

通过 `/llm-router` 打开的管理仪表盘。可查看已注册后端的状态以及进行禁用/启用操作。

---

## 界面布局

```
┌─────────────────────────────────────┐
│  🤖 LLM Router          [Refresh All] │
├─────────┬─────────┬────────┬─────────┤
│Backends │ Enabled │ Models │ Aliases │  ← 汇总卡片
├─────────┴─────────┴────────┴─────────┤
│  Backends 表格                       │
├───────────────────────────────────────┤
│  Routing Aliases 表格                │
└───────────────────────────────────────┘
```

### 汇总卡片（4 个）

| 卡片 | 内容 |
|---|---|
| **Backends** | 已注册到 catalog 的后端总数 |
| **Enabled** | 未被禁用（disabled）的后端数量 |
| **Models** | 所有后端公开的模型总数 |
| **Routing aliases** | 配置文件中定义的别名数量 |

卡片的值在页面加载时通过获取 `/api/llm_router/status` 自动渲染。

---

## 后端列表表格

每行对应一个物理后端（Ollama 实例等）。

### 列说明

| 列 | 说明 |
|---|---|
| **Alias** | 后端的唯一标识短名称（例: `ollama-mac`, `mdns-pi5-hailo`）。作为路由配置和别名解析的键 |
| **Base URL** | 后端的 OpenAI 兼容端点的基础 URL（例: `http://192.168.1.10:11434`） |
| **Status** | 后端的连通状态。详见下文 |
| **SLO** | 后端的资源负载状态（`vision_idle` / `vision_active` / `unknown`）。用于 Hailo Vision 系后端 |
| **Models** | 最近一次探测获取的模型数量。某些实现中可点击展开详细列表 |
| **Last Seen** | 最后一次正常响应的确认时间（ISO 8601）。`null` 表示从未成功 |
| **Actions** | 操作按钮（详见下文） |

### Status 含义

| 值 | 含义 |
|---|---|
| `ready` | 上次探测成功，已获取模型列表 |
| `unreachable` | 连接超时或发生错误 |
| `unknown` | 尚未执行探测（如刚启动时） |
| `probing` | 正在执行探测（Refresh 期间 UI 可能短暂显示） |

> **提示**: `unreachable` 的后端会从路由目标中排除，但仍保留在 catalog 中。网络恢复后执行 Refresh All 或单独 Refresh 即可恢复为 `ready`。

### SLO 含义

| 值 | 含义 |
|---|---|
| `vision_idle` | Vision 任务空闲状态。LLM 负载较低 |
| `vision_active` | Vision 任务运行中。LLM Router 可能会优先使用其他后端 |
| `unknown` | 无法获取 SLO 信息（非 Hailo 后端或获取失败） |

---

## Refresh All 按钮

点击画面右上角的 **Refresh All**，将对所有后端强制执行探测，更新模型列表和状态。

- 执行期间按钮被禁用，完成后重新渲染
- 内部操作：调用 `POST /api/llm_router/refresh`（无请求体），执行所有后端的 `discover_all`
- 如果实现中有 Actions 列的 Refresh 按钮，可对单个后端执行刷新

---

## 单个后端的禁用 / 启用

### 操作步骤

1. 查看后端列表表格的 **Actions** 列
2. 在要禁用的后端行点击 **Disable** 按钮
3. 按钮变为 **Enable**，该行变为灰色
4. 要重新启用，点击 **Enable**

### 行为与持久化

- 操作立即反映到内存中的 catalog
- 同时原子写入 `data/llm_router_state.json`

  ```json
  {
    "version": 1,
    "disabled_aliases": ["ollama-slow", "mdns-pi5"]
  }
  ```

- 应用重启后禁用状态仍然保留
- 通过 mDNS 动态发现的后端如果在启动前已被禁用，发现后也会自动应用（`_pending_disabled` 机制）
- 写入失败时内存状态会回滚，不会与磁盘产生不一致

### 被禁用后端的行为

- 从 `/v1/chat/completions` 等 OpenAI 兼容端点的路由目标中排除
- 直接路由到已禁用的后端时返回 `503 Service Unavailable`
- 在 WebUI 表格中仍然显示（便于确认状态和重新启用）

---

## Routing Aliases 表格

显示配置文件中定义的逻辑模型名称与物理模型 ID 的映射。

| 列 | 说明 |
|---|---|
| **Alias** | 客户端在 `model` 参数中指定的逻辑名称（例: `default-llm`, `fast-chat`） |
| **Physical Model** | 实际处理请求的物理模型 ID（格式: `后端alias/模型名`，例: `ollama-mac/qwen2.5:7b`） |

### 别名的作用

使用别名可以在不修改客户端代码的情况下切换后端或使用的模型。

- 客户端以逻辑名称请求，如 `"model": "default-llm"`
- LLM Router 将其解析为 `default-llm → ollama-mac/qwen2.5:7b` 并代理
- 迁移后端到其他机器时只需更改别名指向即可

别名在配置文件中静态定义，WebUI 以只读方式显示。修改需要编辑配置文件并重启应用。

---

## 常见操作

### 后端显示为 unreachable 时

1. 确认后端服务（Ollama 等）是否已启动
2. 执行 **Refresh All** 或单独 Refresh
3. 如仍未解决，检查 `last_error` 列（或 API 响应）中的错误内容

### 想永久禁用通过 mDNS 自动发现的后端

1. 在目标后端的 Actions 列点击 **Disable**
2. alias 会保存到 `data/llm_router_state.json`，重新发现后也保持禁用状态

### 想临时停止向特定后端发送负载

**Disable** 立即排除 → 完成后 **Enable** 恢复。无需重启。

# MCP 集成指南 — 从 LLM 操作 YU AI Manager

YU AI Manager 内置了 **MCP (Model Context Protocol)** 服务器，让 LLM 应用可以使用自然语言操作图片库。

本应用没有内置聊天 UI。
要使用自然语言进行交互，请从您首选的 MCP 兼容客户端连接。

---

## 什么是 MCP？

MCP (Model Context Protocol) 是一种标准协议，使 LLM 应用能够访问外部工具和数据源。
YU AI Manager 充当 MCP 服务器，LLM 客户端（如 Claude Desktop）连接到它，将自然语言指令转换为 API 操作。

```
┌─────────────────┐      MCP (stdio)       ┌─────────────────────┐
│  LLM 客户端      │ <--------------------> │  YU AI Manager      │
│  (Claude Desktop │                        │  MCP 服务器          │
│   / Open WebUI   │                        │  (python -m         │
│   / Cline 等)    │                        │   mcp_server)       │
└─────────────────┘                        └────────┬────────────┘
                                                     │ HTTP API
                                                     v
                                           ┌─────────────────────┐
                                           │  YU AI Manager      │
                                           │  Web 服务器           │
                                           │  (localhost:5000)    │
                                           └─────────────────────┘
```

## 支持的 MCP 客户端

以下是代表性的 MCP 兼容客户端。所有客户端的配置步骤类似。

| 客户端 | 提供者 | 特点 |
|---|---|---|
| **Claude Desktop** | Anthropic | 直接访问 Claude。原生 MCP 支持 |
| **Claude Code** | Anthropic | 面向开发者的终端客户端 |
| **Cline** | VS Code 扩展 | 编辑器集成。多 LLM 支持 |
| **Open WebUI** | 开源 | 自托管。可与 Ollama 等本地 LLM 结合 |

注意：MCP 兼容客户端的数量正在快速增长。
任何支持 stdio 传输的客户端都应该能够连接。

## 设置

### 1. 启动 YU AI Manager

MCP 服务器通过 Web 服务器的 API 运行，因此需要先运行 YU AI Manager。

```bash
python web_ui.py --db ./tags.db --port 5000
```

### 2. 签发 API 密钥（推荐）

签发 API 密钥后，MCP 服务器可以在使用 LAN 共享或 PIN 认证时绕过 PIN 认证。

API 密钥可从设置 -> API Keys 签发。

在无 PIN 模式下运行时（`config_test.json`）不需要 API 密钥。

### 3. 在 MCP 客户端中添加连接设置

#### Claude Desktop

编辑 `claude_desktop_config.json`：

**Windows**：`%APPDATA%\Claude\claude_desktop_config.json`
**macOS**：`~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "C:/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Claude Code

在项目根目录的 `.mcp.json` 中添加设置，或使用 `claude mcp add` 命令：

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Cline (VS Code)

通过 Cline 的 MCP Settings 输入相同信息。

#### 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|---|---|---|---|
| `YU_BASE_URL` | - | `http://localhost:5000` | Web 服务器 URL |
| `YU_API_KEY` | - | 无 | API 密钥（PIN 环境中必需） |
| `YU_DEBUG_MODE` | - | `0` | 设为 `1` 添加调试工具 |

## 使用示例

连接后，您可以通过给 LLM 下达自然语言指令来操作图片库。

### 搜索与浏览

```
"显示最近 20 张蓝眼睛女孩的图片"
"筛选仅 NovelAI 生成的图片"
"显示上周扫描的图片的统计信息"
```

### 整理与分类

```
"给这 10 张图片打 5 星评分"
"将标签为 'landscape' 的图片添加到'风景合集'"
"列出所有评分 3 分及以下的图片"
```

### 分析与注解

```
"对最近添加的图片进行质量评分并保存到注解"
"显示图片 ID 12345 的所有注解"
"搜索 source 为 agent:claude 的注解"
```

### 扫描操作

```
"扫描新图片"
"检查扫描进度"
"显示扫描错误"
```

## 可用工具

MCP 服务器向 LLM 公开以下工具：

### 搜索与浏览（4 个工具）

| 工具名 | 说明 |
|---|---|
| `search_images` | 按标签、日期、格式、评分等搜索图片 |
| `get_image_detail` | 获取图片的所有元数据 |
| `get_library_stats` | 图片库统计信息（文件数、标签数、来源分布等） |
| `find_similar` | 使用感知哈希搜索相似图片 |

### 合集（4 个工具）

| 工具名 | 说明 |
|---|---|
| `list_collections` | 列出合集 |
| `create_collection` | 创建合集 |
| `delete_collection` | 删除合集 |
| `add_to_collection` / `remove_from_collection` | 添加/移除图片 |

### 标签与评分（2 个工具）

| 工具名 | 说明 |
|---|---|
| `rate_images` | 批量设置多张图片的星级评分 |
| `set_tags` | 批量添加/移除多张图片的标签 |

### 注解（4 个工具）

| 工具名 | 说明 |
|---|---|
| `set_annotations` | 将 AI 分析结果保存为注解 |
| `get_annotations` | 获取图片的注解 |
| `search_annotations` | 按来源、键和置信度搜索注解 |
| `delete_annotations` | 删除注解 |

### 扫描（3 个工具）

| 工具名 | 说明 |
|---|---|
| `trigger_scan` | 启动扫描 |
| `get_scan_status` | 检查扫描进度 |
| `get_scan_errors` | 列出扫描错误 |

### 其他

还包括提示词库、备份和 MCP 客户端管理的工具。

## 常见问题

### Q：应用里没有聊天功能吗？

A：没有。YU AI Manager 专注于图片元数据管理，对话式 AI 界面委托给 MCP 兼容客户端。通过并行运行 Claude Desktop 或类似客户端，您可以通过自然语言执行所有操作。

### Q：应该使用哪个 LLM？

A：只要 MCP 客户端支持，任何 LLM 都可以使用。
为了可靠的工具参数处理，Claude 或 GPT-4 级别的大规模模型往往表现最为稳定。

### Q：可以使用本地 LLM 吗？

A：可以，通过 Open WebUI + Ollama 等组合即可使用本地 LLM，前提是它们支持 MCP。但工具调用的准确性取决于模型的能力。

### Q：YU AI Manager 也有 MCP 客户端功能？

A：`MCP Client` 扩展（在工具页面上）将 YU AI Manager 连接到**其他 MCP 服务器**。本指南描述的是相反方向：外部 LLM -> YU AI Manager。

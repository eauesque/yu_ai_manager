# MCP 集成

YU AI Manager 内置 MCP（Model Context Protocol）服务器，
允许从 Claude Desktop、Claude Code、Cline 等 AI 客户端直接操作。
提供超过 137 个工具，可完整访问从图片管理到 AI 分析的所有功能。

## 支持的 MCP 客户端

| 客户端 | 连接方式 | 备注 |
|--------|----------|------|
| Claude Desktop | stdio / HTTP | 推荐客户端 |
| Claude Code | stdio | CLI 环境 |
| Cline (VS Code) | stdio | VS Code 扩展 |
| Open WebUI | HTTP/SSE | 基于 Web |

## 本地连接 (stdio)

从同一台机器上的 Claude Desktop / Claude Code 连接：

1. 在设置 > API Keys 标签页中创建 API 密钥
2. 将以下内容添加到客户端的配置文件中

### Claude Desktop

`claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

### Claude Code

`.mcp.json`：

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

## LAN 连接 (HTTP/SSE)

从 LAN 上的另一台机器连接：

1. 在 YU AI Manager 中启用 LAN 访问
2. 创建 API 密钥
3. 从设置 > API Keys 标签页的"MCP Connection Snippet"中复制连接设置

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "type": "http",
      "url": "http://192.168.x.x:5000/mcp",
      "headers": {
        "Authorization": "Bearer sk_your_api_key_here"
      }
    }
  }
}
```

## 可用工具（按类别）

### 图片搜索与管理

| 工具 | 说明 |
|------|------|
| `search_images` | 按标签、日期、评分等筛选搜索 |
| `get_image_detail` | 获取详细图片元数据 |
| `get_library_stats` | 图库统计（文件数、标签分布等） |
| `find_similar` | 使用感知哈希检测相似图片 |
| `rate_images` | 批量设置星级评分 |
| `set_tags` | 添加或移除标签 |
| `set_annotations` | 设置注释 |
| `get_annotations` | 获取注释 |

### 收藏集

| 工具 | 说明 |
|------|------|
| `list_collections` | 列出收藏集 |
| `create_collection` | 创建收藏集 |
| `add_to_collection` | 将图片添加到收藏集 |
| `remove_from_collection` | 从收藏集移除图片 |
| `delete_collection` | 删除收藏集 |

### 扫描

| 工具 | 说明 |
|------|------|
| `trigger_scan` | 运行扫描 |
| `get_scan_status` | 检查扫描进度 |
| `list_scan_roots` | 列出扫描根目录 |
| `add_scan_root` | 添加扫描根目录 |
| `scan_directory` | 扫描特定目录 |

### AI 分析

| 工具 | 说明 |
|------|------|
| `analyze_image` | AI 图片分析（单个） |
| `analyze_batch` | AI 图片分析（批量） |
| `wd_tagger_tag_file` | WD-Tagger 推理（单个） |
| `wd_tagger_batch` | WD-Tagger 推理（批量） |
| `semantic_search` | CLIP 语义搜索 |
| `s2t_transcribe_video` | 语音识别 |

### Bridge 集成

| 工具 | 说明 |
|------|------|
| `sd_generate` | 使用 SD WebUI 生成图片 |
| `sd_list_models` | 列出 SD WebUI 模型 |
| `comfyui_generate` | 使用 ComfyUI 生成图片 |
| `comfyui_generate_json` | 执行 ComfyUI 工作流 JSON |

### 提示词库

| 工具 | 说明 |
|------|------|
| `create_prompt` | 创建提示词 |
| `search_prompts` | 搜索提示词 |
| `get_prompt` | 获取提示词 |
| `update_prompt` | 更新提示词 |

### 设置

| 工具 | 说明 |
|------|------|
| `settings_get_schema` | 获取设置架构 |
| `settings_get` | 获取设置值 |
| `settings_set` | 更新设置值 |
| `secrets_status` | 检查加密密钥状态 |

### Agent Safety

| 工具 | 说明 |
|------|------|
| `agent_kill` / `agent_resume` | Kill Switch 控制 |
| `agent_status` | 安全机制状态 |
| `agent_journal` | 搜索操作日志 |
| `agent_undo` | 撤销操作 |
| `agent_circuit_breaker_status` | Circuit Breaker 状态 |
| `agent_budget_status` | Budget tracker 状态 |
| `agent_scope_set` | 设置范围 |
| `agent_anomaly_status` | 异常检测状态 |

### 其他

| 工具 | 说明 |
|------|------|
| `find_duplicates` | 检测重复文件 |
| `search_chat_logs` | 搜索聊天记录 |
| `search_md_files` | 搜索 Markdown 文件 |
| `help_search` | 搜索帮助文档 |
| `share_to_bluesky` | 发布到 Bluesky |
| `list_trophies` | 列出奖杯 |
| `get_monthly_report` | 月度报告 |

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `YU_BASE_URL` | 服务器 URL | `http://localhost:5000` |
| `YU_API_KEY` | API 密钥 | （必需） |
| `YU_DEBUG_MODE` | 启用调试工具 | `0` |

设置 `YU_DEBUG_MODE=1` 会添加直接 DB 查询和健康检查等仅调试工具。

## 故障排除

### 无法连接

1. 验证 YU AI Manager 正在运行
2. 验证 API 密钥正确（必须有 `sk_` 前缀）
3. 验证 `YU_BASE_URL` 正确
4. 对于 LAN 连接，验证已启用 LAN 访问

### 找不到工具

- 如果 Extension 被禁用，其工具将不可用
- 使用 `list_extensions` 检查启用状态

### 超时

- 大型图库的搜索和批量操作可能需要一些时间
- 使用 `limit` 参数限制结果数量

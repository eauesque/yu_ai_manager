# MCP Integration

YU AI Manager has a built-in MCP (Model Context Protocol) server,
allowing direct operation from AI clients such as Claude Desktop, Claude Code, and Cline.
It provides over 137 tools, giving full access to all features from image management to AI analysis.

## Supported MCP Clients

| Client | Connection Method | Notes |
|--------|-------------------|-------|
| Claude Desktop | stdio / HTTP | Recommended client |
| Claude Code | stdio | CLI environment |
| Cline (VS Code) | stdio | VS Code extension |
| Open WebUI | HTTP/SSE | Web-based |

## Local Connection (stdio)

To connect from Claude Desktop / Claude Code on the same machine:

1. Create an API key in Settings > API Keys tab
2. Add the following to your client's configuration file

### Claude Desktop

`claude_desktop_config.json`:

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

`.mcp.json`:

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

## LAN Connection (HTTP/SSE)

To connect from another machine on the LAN:

1. Enable LAN Access in YU AI Manager
2. Create an API key
3. Copy the connection settings from "MCP Connection Snippet" in Settings > API Keys tab

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

## Available Tools (by Category)

### Image Search & Management

| Tool | Description |
|------|-------------|
| `search_images` | Filter search by tags, date, rating, etc. |
| `get_image_detail` | Get detailed image metadata |
| `get_library_stats` | Library statistics (file count, tag distribution, etc.) |
| `find_similar` | Detect similar images using perceptual hashing |
| `rate_images` | Batch set star ratings |
| `set_tags` | Add or remove tags |
| `set_annotations` | Set annotations |
| `get_annotations` | Get annotations |

### Collections

| Tool | Description |
|------|-------------|
| `list_collections` | List collections |
| `create_collection` | Create collection |
| `add_to_collection` | Add images to collection |
| `remove_from_collection` | Remove images from collection |
| `delete_collection` | Delete collection |

### Scanning

| Tool | Description |
|------|-------------|
| `trigger_scan` | Run scan |
| `get_scan_status` | Check scan progress |
| `list_scan_roots` | List scan roots |
| `add_scan_root` | Add scan root |
| `scan_directory` | Scan a specific directory |

### AI Analysis

| Tool | Description |
|------|-------------|
| `analyze_image` | AI image analysis (single) |
| `analyze_batch` | AI image analysis (batch) |
| `wd_tagger_tag_file` | WD-Tagger inference (single) |
| `wd_tagger_batch` | WD-Tagger inference (batch) |
| `semantic_search` | CLIP semantic search |
| `s2t_transcribe_video` | Speech-to-text |

### Bridge Integration

| Tool | Description |
|------|-------------|
| `sd_generate` | Generate image with SD WebUI |
| `sd_list_models` | List SD WebUI models |
| `comfyui_generate` | Generate image with ComfyUI |
| `comfyui_generate_json` | Execute ComfyUI workflow JSON |

### Prompt Library

| Tool | Description |
|------|-------------|
| `create_prompt` | Create prompt |
| `search_prompts` | Search prompts |
| `get_prompt` | Get prompt |
| `update_prompt` | Update prompt |

### Settings

| Tool | Description |
|------|-------------|
| `settings_get_schema` | Get settings schema |
| `settings_get` | Get setting value |
| `settings_set` | Update setting value |
| `secrets_status` | Check encryption key status |

### Agent Safety

| Tool | Description |
|------|-------------|
| `agent_kill` / `agent_resume` | Kill Switch control |
| `agent_status` | Safety mechanism status |
| `agent_journal` | Search operation journal |
| `agent_undo` | Undo operation |
| `agent_circuit_breaker_status` | Circuit Breaker status |
| `agent_budget_status` | Budget tracker status |
| `agent_scope_set` | Set scope |
| `agent_anomaly_status` | Anomaly detection status |

### Other

| Tool | Description |
|------|-------------|
| `find_duplicates` | Detect duplicate files |
| `search_chat_logs` | Search chat logs |
| `search_md_files` | Search Markdown files |
| `help_search` | Search help documentation |
| `share_to_bluesky` | Post to Bluesky |
| `list_trophies` | List trophies |
| `get_monthly_report` | Monthly report |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `YU_BASE_URL` | Server URL | `http://localhost:5000` |
| `YU_API_KEY` | API key | (required) |
| `YU_DEBUG_MODE` | Enable debug tools | `0` |

Setting `YU_DEBUG_MODE=1` adds debug-only tools such as direct DB queries and health checks.

## Troubleshooting

### Cannot Connect

1. Verify that YU AI Manager is running
2. Verify the API key is correct (must have `sk_` prefix)
3. Verify `YU_BASE_URL` is correct
4. For LAN connections, verify that LAN Access is enabled

### Tool Not Found

- If an Extension is disabled, its tools become unavailable
- Use `list_extensions` to check the enabled status

### Timeout

- Search and batch operations on large libraries may take some time
- Use the `limit` parameter to restrict the number of results

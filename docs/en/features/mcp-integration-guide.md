# MCP Integration Guide — Operating YU AI Manager from an LLM

YU AI Manager has a built-in **MCP (Model Context Protocol)** server that lets LLM applications operate the image library using natural language.

There is no chat UI built into this application.
To interact with it using natural language, connect from your preferred MCP-compatible client.

---

## What Is MCP?

MCP (Model Context Protocol) is a standard protocol that enables LLM applications to access external tools and data sources.
YU AI Manager acts as an MCP server, and LLM clients (such as Claude Desktop) connect to it, translating natural language instructions into API operations.

```
┌─────────────────┐      MCP (stdio)       ┌─────────────────────┐
│  LLM Client     │ <--------------------> │  YU AI Manager      │
│  (Claude Desktop │                        │  MCP Server         │
│   / Open WebUI   │                        │  (python -m         │
│   / Cline etc.)  │                        │   mcp_server)       │
└─────────────────┘                        └────────┬────────────┘
                                                     │ HTTP API
                                                     v
                                           ┌─────────────────────┐
                                           │  YU AI Manager      │
                                           │  Web Server          │
                                           │  (localhost:5000)    │
                                           └─────────────────────┘
```

## Supported MCP Clients

The following are representative MCP-compatible clients. The configuration steps are similar for all of them.

| Client | Provider | Features |
|---|---|---|
| **Claude Desktop** | Anthropic | Direct Claude access. Native MCP support |
| **Claude Code** | Anthropic | Terminal-based client for developers |
| **Cline** | VS Code Extension | Editor integration. Multi-LLM support |
| **Open WebUI** | Open Source | Self-hosted. Can be combined with local LLMs such as Ollama |

Note: The number of MCP-compatible clients is growing rapidly.
Any client that supports stdio transport should be able to connect.

## Setup

### 1. Start YU AI Manager

The MCP server operates through the Web server's API, so YU AI Manager must be running first.

```bash
python web_ui.py --db ./tags.db --port 5000
```

### 2. Issue an API Key (Recommended)

Issuing an API key allows the MCP server to bypass PIN authentication when using LAN sharing or PIN authentication.

API keys can be issued from Settings -> API Keys.

An API key is not needed when running without a PIN (`config_test.json`).

### 3. Add Connection Settings to Your MCP Client

#### Claude Desktop

Edit `claude_desktop_config.json`:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

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

Add settings to `.mcp.json` at the project root, or use the `claude mcp add` command:

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

Enter the same information through Cline's MCP Settings.

#### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `YU_BASE_URL` | - | `http://localhost:5000` | Web server URL |
| `YU_API_KEY` | - | None | API key (required in PIN environments) |
| `YU_DEBUG_MODE` | - | `0` | Set to `1` to add debug tools |

## Usage Examples

Once connected, you can operate the image library by giving natural language instructions to the LLM.

### Search and Browse

```
"Show me the 20 most recent images of girls with blue eyes"
"Filter to only images generated with NovelAI"
"Show me statistics for images scanned last week"
```

### Organize and Classify

```
"Give these 10 images a 5-star rating"
"Add images tagged 'landscape' to the 'Scenery Collection'"
"List all images with a rating of 3 or below"
```

### Analysis and Annotation

```
"Score the quality of recently added images and save to annotations"
"Show me all annotations for image ID 12345"
"Search for annotations with source agent:claude"
```

### Scan Operations

```
"Scan for new images"
"Check the scan progress"
"Show me any scan errors"
```

## Available Tools

The MCP server exposes the following tools to the LLM:

### Search and Browse (4 tools)

| Tool Name | Description |
|---|---|
| `search_images` | Search images by tags, date, format, rating, etc. |
| `get_image_detail` | Retrieve all metadata for an image |
| `get_library_stats` | Library statistics (file count, tag count, source distribution, etc.) |
| `find_similar` | Search for similar images using perceptual hash |

### Collections (4 tools)

| Tool Name | Description |
|---|---|
| `list_collections` | List collections |
| `create_collection` | Create a collection |
| `delete_collection` | Delete a collection |
| `add_to_collection` / `remove_from_collection` | Add/remove images |

### Tags and Ratings (2 tools)

| Tool Name | Description |
|---|---|
| `rate_images` | Set star ratings for multiple images at once |
| `set_tags` | Add/remove tags for multiple images at once |

### Annotations (4 tools)

| Tool Name | Description |
|---|---|
| `set_annotations` | Save AI analysis results as annotations |
| `get_annotations` | Retrieve annotations for an image |
| `search_annotations` | Search annotations across source, key, and confidence |
| `delete_annotations` | Delete annotations |

### Scan (3 tools)

| Tool Name | Description |
|---|---|
| `trigger_scan` | Start a scan |
| `get_scan_status` | Check scan progress |
| `get_scan_errors` | List scan errors |

### Other

Tools for prompt library, backup, and MCP client management are also included.

## FAQ

### Q: Is there no chat feature in the app?

A: There is not. YU AI Manager specializes in image metadata management, and the conversational AI interface is delegated to MCP-compatible clients. You can perform all operations via natural language by running Claude Desktop or a similar client alongside it.

### Q: Which LLM should I use?

A: Any LLM works, as long as the MCP client supports it.
For reliable tool argument handling, large-scale models like Claude or GPT-4 class tend to perform most consistently.

### Q: Can I use a local LLM?

A: Yes, local LLMs work with combinations such as Open WebUI + Ollama, provided they support MCP. However, tool-calling accuracy depends on the model's capabilities.

### Q: YU AI Manager also has an MCP client feature?

A: The `MCP Client` extension (on the Tools page) connects YU AI Manager to **other MCP servers**. This guide describes the opposite direction: external LLM -> YU AI Manager.

# Yu AI Manager — Complete Specification

> **Intended Audience**: AI agents such as Claude Desktop  
> **Version**: v4.91.15  
> **Updated**: 2026-04-19

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [Architecture Overview](#3-architecture-overview)
4. [Authentication & Security](#4-authentication--security)
5. [REST API Endpoints](#5-rest-api-endpoints)
6. [MCP Server](#6-mcp-server)
7. [SSE Events](#7-sse-events)
8. [DB Schema](#8-db-schema)
9. [Extensions](#9-extensions)
10. [Configuration (config.json)](#10-configurationconfigjson)
11. [File Structure](#11-file-structure)
12. [Development Standards](#12-development-standards)

---

## 1. Project Overview

**Yu AI Manager** is a local library management system for AI-generated images, videos, audio, and text.  
Guided by an edge-first, cloud-independent design philosophy, it prioritizes completing operations locally/on LAN.

### Key Features

| Feature | Description |
|------|------|
| Library Management | Scan, tag, and search images/videos/audio/text |
| Metadata Extraction | Auto-extract generation parameters from A1111 / ComfyUI / NovelAI |
| AI Analysis | Image analysis via Claude / OpenAI / Ollama / Hailo VLM |
| Semantic Search | Meaning-based search using CLIP (ONNX/CoreML) + Hailo |
| Bridge Integration | Generate requests to Stable Diffusion / ComfyUI / NovelAI |
| LLM Router | Integrated routing to Ollama / OpenAI-compatible backends |
| Agent Safety | Safety mechanisms: Kill Switch / Circuit Breaker / Approval Gate, etc. |
| LAN Cooperation | Auto-discovery via mDNS + peer sharing |
| MCP Server | 180+ tools directly accessible from Claude Desktop |

---

## 2. Technology Stack

| Layer | Technology |
|---------|------|
| Backend | Python 3.11+ / Quart (async) / Hypercorn |
| Database | SQLite3 (FTS5 full-text search + zstd compressed BLOB) |
| Frontend | TypeScript + Vite build |
| Desktop | Tauri (Rust) |
| MCP | FastMCP (Anthropic MCP Server) |
| LLM | Claude API / OpenAI API / Ollama / Hailo VLM |
| Inference | ONNX Runtime / CoreML / Hailo Runtime |
| Package Management | Python: `uv pip` / Node.js: `pnpm` |

### Port Convention

- `5000–5099`: Production app reserved range (do not change)
- `5100+`: Test/debug use (`scripts/find_port.py` auto-detects available ports)

---

## 3. Architecture Overview

```
┌──────────────────────────────────────────────────┐
│  Client Layer                                     │
│  ├─ Web UI (TypeScript / Tauri)                  │
│  ├─ Claude Desktop (MCP)                         │
│  └─ External Tools (API Key / LAN Peer)           │
├──────────────────────────────────────────────────┤
│  Auth Layer (auth_chain.py)                       │
│  ├─ PIN / QuickLock (Boss Lock)                  │
│  ├─ API Key (Bearer / Scopes)                    │
│  └─ LAN Peer Trust (mDNS verification)           │
├──────────────────────────────────────────────────┤
│  API Layer                                        │
│  ├─ REST API (235+ endpoints / Quart Blueprint)  │
│  ├─ SSE Stream (/api/events/stream)              │
│  └─ MCP Server (180+ tools)                      │
├──────────────────────────────────────────────────┤
│  Service Layer                                    │
│  ├─ TagDB (SQLite / schema v53)                  │
│  ├─ Event Bus (SSE broadcaster)                  │
│  ├─ LLM Router (multi-backend integration)       │
│  ├─ Analysis Engine (Claude/OpenAI/Ollama/Hailo)│
│  ├─ Extensions (47 builtin)                      │
│  └─ File Services (scan/serve/thumbnail)         │
├──────────────────────────────────────────────────┤
│  Agent Safety Layer                               │
│  ├─ Kill Switch          ├─ Budget Tracker        │
│  ├─ Circuit Breaker      ├─ Approval Gate         │
│  ├─ Scope Fence          ├─ Undo Engine           │
│  ├─ Anomaly Detector     └─ Audit Bureau          │
└──────────────────────────────────────────────────┘
```

### Module Dependency Direction

```
routes/ → core/services_core/ → core/tagdb_core/ → SQLite
routes/ → core/web/ (authentication)
mcp_server/ → routes/ 経由 or コア直接呼び出し
extensions/ → core/extensions_core/ (lifecycle management)
```

---

## 4. Authentication & Security

### Auth Chain (core/web/auth_chain.py)

Evaluated in order for each request:

1. **Static File Bypass** — `/static/`, `/favicon.ico`, `/help/*`
2. **MCP Bypass** — `/mcp` (MCP's own authentication)
3. **LLM Router Bypass** — `/v1/` (loopback only)
4. **LAN Share Bypass** — `/s/<token>` (share token)
5. **LAN Peer Trust** — mDNS-verified peers do not require PIN
6. **API Key Auth** — `Authorization: Bearer <key>` (scope validation)
7. **QuickLock Check** — When locked, only `/api/lock/unlock` is allowed
8. **PIN Check** — Browser session authentication

### API Key Scopes

| Scope | Permission |
|---------|------|
| `read` | Read all |
| `write` | Write files/settings |
| `tag.write` | Add/remove tags |
| `collection.write` | Manage collections |
| `annotate` | Annotate |
| `scan` | Scan operations |
| `admin` | Administrator (all operations) |

### QuickLock / Boss Mode

- PIN is hashed with PBKDF2-SHA256 (600k iterations)
- Rate limit: max 5 failures, then 60-second lockout
- `/api/lock/status` checks lock state (no auth required)
- `/api/lock/unlock` to unlock (PIN required)

### Secret Management

- 1Password integration (`op://vault/item/field` reference format)
- Bitwarden integration
- Config values encrypted with Fernet symmetric encryption (`enc:...` prefix)

---

## 5. REST API Endpoints

Base URL: `http://localhost:5000` (default)

### Agent Safety

| Method | Path | Description |
|---------|------|------|
| GET | `/api/agent/status` | Kill Switch + CB + Budget state |
| POST | `/api/agent/kill` | Activate Kill Switch |
| POST | `/api/agent/resume` | Deactivate Kill Switch |
| GET | `/api/agent/circuit-breaker` | Circuit Breaker state |
| POST | `/api/agent/circuit-breaker/reset` | Reset CB |
| GET | `/api/agent/budget` | Remaining budget |
| POST | `/api/agent/budget/reset` | Reset budget |
| GET | `/api/agent/journal` | Search action journal |
| GET | `/api/agent/journal/stats` | Journal stats |
| GET | `/api/agent/approval` | Pending approval requests |
| POST | `/api/agent/approval/<request_id>` | Approve/reject |
| GET | `/api/agent/approval/history` | Approval history |
| POST | `/api/agent/undo/<int:journal_id>` | Execute undo |
| GET | `/api/agent/undoable` | Undoable journals |
| GET | `/api/agent/anomaly` | Anomaly detection alerts |
| GET | `/api/agent/audit` | Audit logs |
| GET | `/api/agent/scope` | Scope list |
| GET | `/api/agent/scope/<session_id>` | Session scope |
| POST | `/api/agent/scope/<session_id>` | Update scope |
| DELETE | `/api/agent/scope/<session_id>` | Delete scope |
| GET | `/api/agent/auto-approve` | Auto-approval rules |
| POST | `/api/agent/auto-approve` | Add rule |
| DELETE | `/api/agent/auto-approve/<int:index>` | Delete rule |
| GET | `/api/agent/tool-levels` | Tool safety levels |

### AI Analysis

| Method | Path | Description |
|---------|------|------|
| GET | `/api/analysis/config` | Get config |
| POST | `/api/analysis/config` | Update config |
| GET | `/api/analysis/available-engines` | Available engines |
| GET | `/api/analysis/ollama/models` | Ollama model list |
| POST | `/api/analysis/ollama/test` | Connection test |
| POST | `/api/analysis/analyze/<int:file_id>` | Analyze file |
| GET | `/api/analysis/result/<int:file_id>` | Analysis result |
| POST | `/api/analysis/batch` | Batch analyze |
| POST | `/api/analysis/batch/cancel` | Cancel batch |
| GET | `/api/analysis/servers` | Server list |
| POST | `/api/analysis/servers` | Add server |
| PUT | `/api/analysis/servers/<server_id>` | Update server |
| DELETE | `/api/analysis/servers/<server_id>` | Delete server |
| GET | `/api/analysis/servers/discovered` | Auto-discovered servers |
| POST | `/api/analysis/servers/discovered/register` | Register |

### File & Scan

| Method | Path | Description |
|---------|------|------|
| POST | `/api/scan/start` | Start scan |
| POST | `/api/scan/cancel` | Cancel |
| POST | `/api/scan/resume` | Resume |
| GET | `/api/scan/status` | Status |
| GET | `/api/scan/queue` | Queue list |
| DELETE | `/api/scan/queue/<queue_id>` | Delete queue |
| POST | `/api/scan/queue/clear` | Clear queue |
| GET | `/api/scan/history` | Scan history |
| GET | `/api/scan-errors` | Scan errors |
| POST | `/api/scan-errors/<int:error_id>/resolve` | Resolve error |
| GET | `/api/scanned-roots` | Scanned scan roots |
| POST | `/api/scanned-roots/purge` | Delete scan root |

### Tags, Favorites & Ratings

| Method | Path | Description |
|---------|------|------|
| POST | `/api/tags/add` | Add tag |
| POST | `/api/tags/remove` | Remove tag |
| GET | `/api/tags/list` | Tag list |
| POST | `/api/favorites/toggle` | Toggle favorite |
| GET | `/api/favorites/check` | Check favorite |
| GET | `/api/favorites/list` | Favorite list |
| GET | `/api/ratings/get` | Get rating |
| POST | `/api/ratings/set` | Set rating |
| POST | `/api/ratings/batch-set` | Batch set |
| GET | `/api/ratings/stats` | Stats |

### Collections

| Method | Path | Description |
|---------|------|------|
| GET | `/api/collections` | Collection list |
| POST | `/api/collections` | Create |
| PUT | `/api/collections/<int:collection_id>` | Update |
| DELETE | `/api/collections/<int:collection_id>` | Delete |
| POST | `/api/collections/reorder` | Reorder |
| POST | `/api/collections/<int:collection_id>/batch-add` | Batch add |
| POST | `/api/collections/<int:collection_id>/batch-remove` | Batch remove |
| GET | `/api/collections/<int:collection_id>/export/csv` | Export CSV |

### LLM Router

| Method | Path | Description |
|---------|------|------|
| GET | `/api/llm_router/status` | ステータス |
| POST | `/api/llm_router/refresh` | リフレッシュ |
| POST | `/api/llm_router/backends/<alias>/enable` | バックエンド有効化 |
| POST | `/api/llm_router/backends/<alias>/disable` | バックエンド無効化 |
| POST | `/v1/chat/completions` | OpenAI 互換チャット |
| GET | `/v1/models` | モデル一覧 |

### システム・サーバー情報

| Method | Path | Description |
|---------|------|------|
| GET | `/api/system/inference-info` | 推論エンジン情報 |
| GET | `/api/mdns/identity` | mDNS アイデンティティ |
| GET | `/api/mdns/peers` | LAN ピア一覧 |
| GET | `/api/logs/recent` | 最近のログ |
| GET | `/api/logs/stream` | ログ SSE ストリーム |
| GET | `/api/jobs/status` | ジョブ状態 |
| GET | `/api/events/stream` | SSE イベントストリーム |
| GET | `/api/events/info` | SSE 接続情報 |

### 設定・シークレット

| Method | Path | Description |
|---------|------|------|
| GET/POST | `/api/settings/llm-endpoints` | LLM エンドポイント管理 |
| GET/POST | `/api/settings/secrets/*` | シークレット管理 |
| GET | `/api/settings/bw-status` | Bitwarden 状態 |
| GET | `/api/settings/op-status` | 1Password 状態 |

### ヘルプ

| Method | Path | Description |
|---------|------|------|
| GET | `/api/help/toc` | 目次 |
| GET | `/api/help/content/<section>` | コンテンツ |
| GET | `/api/help/search` | 検索 |

---

## 6. MCP Server

### Connection

```
Transport: stdio or SSE
Endpoint: /mcp (SSE mode)
```

### Tool Groups (180+ tools)

| グループ | 登録関数 | 主なツール |
|---------|---------|-----------|
| **Agent Safety** | `register_agent_safety_tools` 他 | kill_switch, circuit_breaker, budget, journal, approval, scope, undo, anomaly, audit |
| **Analysis** | `register_analysis_tools` 他 | analyze_file, batch_analyze, analysis_config, analysis_servers |
| **Batch** | `register_batch_tools` 他 | batch_scan, batch_annotate, batch_operation |
| **File Management** | `register_misc_file_tools` 他 | file_meta, duplicate_detect, dnd_register, download |
| **Search** | `register_search_tools` 他 | search, cross_search, collection_search, semantic_search |
| **LLM** | `register_llm_tools` 他 | llm_chat, llm_endpoint, llm_router |
| **Bridge - NAI** | `register_nai_bridge_tools` | nai_generate, nai_config |
| **Bridge - SD** | `register_sd_bridge_tools` | sd_generate, sd_config |
| **Bridge - ComfyUI** | `register_comfyui_bridge_tools` | comfyui_generate, comfyui_workflow |
| **Bridge - SD↔NAI** | `register_sd_nai_convert_tools` | convert_prompt |
| **Extensions** | `register_extension_tools` 他 | extension_list, extension_enable, extension_disable |
| **Scan Roots** | `register_scan_roots_tools` 他 | scan_root_add, scan_root_remove, scan_start |
| **Hailo GenAI** | `register_hailo_genai_tools` 他 | hailo_generate, hailo_benchmark |
| **Hailo Tagger** | `register_hailo_tagger_tools` | hailo_tag |
| **YOLO** | `register_yolo_detect_tools` 他 | yolo_detect, yolo_stream |
| **Semantic** | `register_semantic_tools` | semantic_search, semantic_index |
| **WD-Tagger** | `register_wd_tagger_tools` | wd_tag, wd_batch_tag |
| **OCR** | `register_ocr_tools` | ocr_extract |
| **Chatlog** | `register_chatlog_tools` | chatlog_save, chatlog_search |
| **Prompt Library** | `register_prompt_library_tools` | prompt_save, prompt_search |
| **Prompt Sim** | `register_prompt_sim_tools` | prompt_simulate, wildcard_expand |
| **LoRA Dataset** | `register_lora_dataset_tools` | lora_dataset_manage |
| **Stats** | `register_stats_tools` 他 | stats_summary, monthly_report, trophy |
| **GitHub** | `register_github_tools` 他 | github_issues, github_queue, github_triage |
| **SNS** | `register_sns_share_tools` 他 | sns_post, bluesky_post |
| **Utility** | `register_debug_tools` 他 | debug_query, help_search, settings_get |

### Safety Interceptor

All MCP tool calls automatically check:
1. Kill Switch — All tools blocked when active
2. Circuit Breaker — Auto-blocked on consecutive errors
3. Budget Tracker — Warning/stop on budget exceeded
4. Approval Gate — `admin` scope operations await human approval
5. Scope Fence — Block access outside session scope

---

## 7. SSE Events

### Connection

```
GET /api/events/stream?types=<event1>,<event2>,...
Content-Type: text/event-stream
```

Omit `types` to receive all events.

### Event List

**Scan**

| Event | Description |
|---------|------|
| `scan.start` | Scan started |
| `scan.progress` | Progress (processed/total) |
| `scan.complete` | Completed |
| `scan.error` | Error |
| `scan.queued` | Queued |

**File Operations**

| Event | Description |
|---------|------|
| `favorite.add` / `favorite.remove` | Favorite |
| `tag.add` / `tag.remove` | Tag |
| `rating.set` / `rating.clear` | Rating |
| `annotation.set` / `annotation.delete` | Annotation |
| `collection.create` / `collection.delete` | Collection |

**Generation**

| Event | Description |
|---------|------|
| `generation.submit` | Generation request |
| `generation.progress` | Progress |
| `generation.complete` | Completed |
| `generation.error` | Error |
| `generation.cancel` | Cancelled |

**Analysis & Inference**

| Event | Description |
|---------|------|
| `analysis.complete` | Analysis complete |
| `batch_analysis.complete` | Batch complete |
| `semantic_index.start/progress/complete` | Index |
| `yolo_detect.start/progress/complete` | Object detection |
| `wd_tagger.complete` | WD-Tagger complete |
| `ocr.complete` | OCR complete |

**Agent Safety**

| Event | Description |
|---------|------|
| `agent.killed` | Kill Switch active |
| `agent.resumed` | Resumed |
| `agent.circuit_open` | Circuit Breaker open |
| `agent.circuit_closed` | Closed |
| `agent.budget_warning` | Budget warning |
| `agent.budget_exhausted` | Budget exhausted |

**LAN Cooperation**

| Event | Description |
|---------|------|
| `peer.discovered` | Peer discovered |
| `peer.online` / `peer.offline` | State change |
| `sync.file_changed` / `sync.file_received` | File sync |
| `sync.conflict` | Conflict |

**Other**

| Event | Description |
|---------|------|
| `scheduler.job_executed` | Scheduler job executed |
| `backup.complete` / `backup.error` | Backup |
| `config.scan_roots_changed` | Scan root changed |
| `watcher.started` / `watcher.stopped` | File watch |
| `webhook.received` | Webhook received |
| `github_queue.new_issues` | GitHub new issues |
| `bsky_queue.new_notifications` | Bluesky new notifications |
| `chatlog_reprocess.start/progress/complete` | Chatlog reprocess |
| `fpb.start/progress/complete/error` | Freeze & Pull-back |

---

## 8. DB Schema

**DB File**: `tags.db` (project root, specify with `--db`)  
**Schema Version**: 53  
**Read/Write Separation**: GET operations must use `get_readonly_db()`

### Main Tables

```sql
-- Files
files (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  mtime INTEGER,
  size INTEGER,
  hash TEXT,
  is_deleted INTEGER DEFAULT 0,         -- Soft delete
  parser_version INTEGER DEFAULT 1,
  meta_source TEXT,
  is_zip_member INTEGER DEFAULT 0,
  extracted_from_zip TEXT,
  extracted_from_internal TEXT,
  extraction_date INTEGER,
  extracted_to_file_id INTEGER,
  width INTEGER,
  height INTEGER,
  file_ext TEXT GENERATED ALWAYS AS     -- Auto-generated
    (lower(substr(path, instr(path,'.',-1)+1))) STORED
)

-- Tag dictionary
tags (
  id INTEGER PRIMARY KEY,
  tag TEXT NOT NULL,
  namespace TEXT,                        -- "namespace:tag" format
  first_seen_mtime INTEGER,
  UNIQUE(tag, namespace)
)

-- Files↔タグ関連
file_tags (
  file_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  weight REAL DEFAULT 1.0,              -- Tag weight
  source TEXT DEFAULT 'meta',           -- 'meta'|'manual'|'ai'|'wd'
  PRIMARY KEY (file_id, tag_id)
)

-- Generation parameters
templates (
  id INTEGER PRIMARY KEY,
  file_id INTEGER NOT NULL UNIQUE,
  raw_prompt TEXT,
  raw_negative TEXT,
  format TEXT,                           -- 'a1111'|'comfyui'|'nai'
  model_name TEXT,
  model_hash TEXT,
  char_positive TEXT,
  char_negative TEXT
)

-- Prompt tokens
template_tokens (
  id INTEGER PRIMARY KEY,
  template_id INTEGER NOT NULL,
  token_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  position INTEGER NOT NULL
)

-- Metadata extraction state
media_extract_state (
  file_id INTEGER PRIMARY KEY,
  cache_state TEXT DEFAULT 'none',       -- 'none'|'pending'|'done'|'error'
  metadata_schema_version INTEGER,
  metadata_extracted_at INTEGER,
  metadata_source TEXT,
  fingerprint_mtime INTEGER,
  fingerprint_hash TEXT,
  error_code TEXT,
  error_count INTEGER DEFAULT 0,
  next_retry_after INTEGER,
  last_access_at INTEGER,
  updated_at INTEGER
)

-- Filesキャッシュ（サムネイル等）
cache_entry (
  cache_key TEXT PRIMARY KEY,
  kind TEXT NOT NULL,                    -- 'thumbnail'|'preview'|'clip_emb'
  path TEXT NOT NULL,
  file_id INTEGER,
  size_bytes INTEGER DEFAULT 0,
  last_access_at INTEGER,
  updated_at INTEGER
)

-- Favorites
favorites (
  file_id INTEGER NOT NULL,
  collection_id INTEGER DEFAULT 1,
  added_at INTEGER,
  PRIMARY KEY (file_id, collection_id)
)

-- Schema version management
schema_version (
  version INTEGER PRIMARY KEY,
  applied_at INTEGER,
  description TEXT
)

-- Extension schema version
extension_schema_versions (
  extension_name TEXT NOT NULL,
  version INTEGER NOT NULL,
  applied_at INTEGER,
  description TEXT,
  PRIMARY KEY (extension_name, version)
)

-- DB metadata
db_meta (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at INTEGER
)
```

### FTS5 (Full-Text Search)

```sql
-- Prompt full-text search
templates_fts USING fts5 (
  content='templates',
  raw_prompt, raw_negative, model_name
)
```

Note: CJK characters are not supported by FTS5, so LIKE fallback is used.

### Main Indexes

```sql
idx_tags_tag_lower          -- Case-insensitive tag
idx_files_deleted_mtime     -- Soft delete + mtime
idx_files_deleted_source    -- Soft delete + ソース
idx_file_tags_tag_id        -- Tag ID search
idx_file_tags_source        -- Metadata source
idx_media_extract_cache_state -- Cache state
idx_media_extract_next_retry  -- Retry wait
idx_files_hash              -- Hash (duplicate detection)
idx_files_deleted_ext       -- Extension filter
```

---

## 9. Extensions

### Structure

```
extensions/
  builtin-<name>/
    extension.json     # Metadata
    <name>_ext.py      # エントリーポイント
    templates/         # HTML templates
    static/            # 静的ファイル
```

### extension.json Format

```json
{
  "name": "builtin-analysis",
  "version": "1.0.0",
  "description": "AI image analysis engine",
  "type": "general",
  "category": "ai",
  "entry": "analysis_ext.py",
  "has_blueprint": true,
  "core_shim": "analysis",
  "config": {
    "enabled": true,
    "priority": 150
  }
}
```

### Builtin Extensions List (47)

| Extension | Category | Description |
|--------|---------|------|
| builtin-a1111 | parser | A1111 metadata extraction |
| builtin-analysis | ai | AI image analysis (Claude/OpenAI/Ollama) |
| builtin-annotations | utility | Annotation management |
| builtin-audio-analysis | ai | Audio analysis (Whisper) |
| builtin-auto-scan-watcher | utility | Auto-scan on file changes |
| builtin-backup | utility | DB/config backup |
| builtin-chatlog | utility | Chatlog management |
| builtin-clip-coreml | ai | CLIP semantic search (macOS) |
| builtin-clip-onnx | ai | CLIP semantic search (cross-platform) |
| builtin-clip-search | search | CLIP search UI |
| builtin-comfyui | parser | ComfyUI metadata extraction |
| builtin-comfyui-bridge | bridge | ComfyUI API integration |
| builtin-cross-search | search | Text full-text search |
| builtin-debug-check | utility | System diagnostics |
| builtin-download | utility | URL/magnet link download |
| builtin-export | utility | CSV/JSON/ZIP export |
| builtin-favorites-manager | utility | Favorites & collections |
| builtin-freeze-pullback | utility | File recovery |
| builtin-github-integration | integration | GitHub issue/PR management |
| builtin-hailo-genai | ai | Hailo generative AI |
| builtin-hailo-semantic-search | search | Hailo semantic search |
| builtin-hailo-yolo-detect | ai | Hailo YOLO object detection |
| builtin-inference | ai | Remote inference management |
| builtin-lan-cowork | network | LAN cooperation |
| builtin-lan-share | network | LAN QR share |
| builtin-lora-dataset-manager | utility | LoRA dataset (kohya_ss integration) |
| builtin-mcp-client | integration | External MCP server connection |
| builtin-md-viewer | utility | Markdown file viewer |
| builtin-nai-bridge | bridge | NovelAI API integration |
| builtin-novelai-v3 | parser | NovelAI v3 metadata |
| builtin-novelai-v4 | parser | NovelAI v4 metadata |
| builtin-ocr | ai | OCR text extraction |
| builtin-prompt-library | utility | Prompt management & search |
| builtin-prompt-simulator | utility | Wildcard expansion |
| builtin-prompt-syntax | utility | LoRA/control token parsing |
| builtin-ratings | utility | 5-star rating |
| builtin-sd-nai-convert | utility | SD ↔ NAI prompt conversion |
| builtin-sd-webui-bridge | bridge | SD WebUI API integration |
| builtin-sns-share | integration | SNS posting (Bluesky/Twitter) |
| builtin-speech-to-text | ai | Speech recognition |
| builtin-stats | utility | Statistics dashboard |
| builtin-tag-dictionary | utility | Tag dictionary & description |
| builtin-trophy | utility | Milestone achievement |
| builtin-video-analysis | ai | Video keyframe analysis |
| builtin-wd-tagger | ai | WD-Tagger auto tagging |
| builtin-webhook | integration | Webhook send/receive |

---

## 10. Configuration (config.json)

**Path**: `{project root}/config.json`

```json
{
  "scan_roots": [
    {
      "path": "/path/to/images",
      "enabled": true,
      "recursive": true,
      "comment": "Main image folder"
    }
  ],

  "server": {
    "host": "127.0.0.1",
    "port": 5000,
    "lan": false,
    "pin": null,
    "allow_remote_restart": false
  },

  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "local",
        "base_url": "http://localhost:11434",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "fast": "local/qwen2.5:7b",
      "large": "local/qwen2.5:32b"
    }
  },

  "api_keys": [
    {
      "id": "ak_...",
      "key_hash": "<sha256_hex>",
      "key_prefix": "sk_...",
      "label": "Claude Desktop",
      "scopes": ["read", "write", "admin"]
    }
  ],

  "ai_analysis": {
    "engine": "claude",
    "model": "claude-opus-4-7",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llava",
    "language": "ja"
  },

  "wd_tagger": {
    "model": "WD14",
    "general_threshold": 0.35,
    "character_threshold": 0.85,
    "write_xmp": true,
    "engine_type": "onnx"
  },

  "inference_servers": [
    {
      "id": "hailo-1",
      "name": "Hailo Server",
      "endpoint_url": "http://localhost:8080",
      "priority": 100,
      "enabled": true,
      "inference_types": ["clip", "yolo"],
      "timeout": 30
    }
  ],

  "extensions": {
    "builtin-analysis": {
      "enabled": true
    }
  },

  "mdns": {
    "bind_address": "0.0.0.0"
  }
}
```

### Environment Variables

| Variable | Description |
|-----|------|
| `TAGDB_DATA_DIR` | Data directory |
| `TAGDB_CACHE_DIR` | Cache directory |
| `TAGDB_LOG_DIR` | Log directory |
| `TAGDB_PROFILES_DIR` | Profiles directory |
| `YU_DEBUG_MODE` | Set to `1` to enable debug API |

---

## 11. File Structure

```
O:/yu_ai_manager/
├── web_ui.py              # ASGI entry point
├── app.py                 # Quart app init
├── config.json            # Main config
├── tags.db                # Dev DB (specify with --db)
├── VERSION                # Version number
├── CHANGELOG.md           # Change history
├── TODO.md                # Issue tracking
│
├── routes/                # REST API Blueprint
│   ├── agent_safety.py
│   ├── analysis.py
│   ├── collections.py
│   ├── debug.py
│   ├── favorites.py
│   ├── files.py
│   ├── maintenance.py
│   ├── ratings.py
│   ├── scan.py
│   ├── scan_roots.py
│   ├── server_info.py
│   ├── settings.py
│   └── tags.py
│
├── core/                  # Core modules
│   ├── agent_safety/      # Safety mechanisms
│   ├── analysis/          # AI analysis engine
│   ├── event_bus/         # Event bus
│   ├── extensions_core/   # Extension lifecycle
│   ├── files_core/        # File serving
│   ├── infra_core/        # API response, etc.
│   ├── llm_router/        # LLM routing
│   ├── scan_core/         # Scanning
│   ├── schema_core/       # DB schema & migration
│   ├── services_core/     # DB async adapter
│   ├── settings_core/     # Settings management
│   ├── sse/               # SSE broadcaster
│   ├── tagdb_core/        # Tag DB core
│   └── web/               # Auth & request handling
│
├── mcp_server/            # MCP Server (180+ tools)
│   ├── server.py          # FastMCP entry
│   ├── tools/             # Tool definitions
│   └── interceptor.py     # Safety interceptor
│
├── extensions/            # Extensions (47 builtin)
│   └── builtin-*/
│
├── src/ts/                # TypeScript frontend
│   ├── main/              # Main screen
│   ├── nav/               # Navigation
│   ├── tools-page/        # Tools page
│   └── types/             # Type definitions
│
├── src-tauri/             # Tauri desktop
│
├── ui/default/            # HTML templates
│   ├── templates/
│   └── static/dist/       # Built JS
│
├── docs/                  # Documentation (ja/ is primary)
│   ├── ja/                # Japanese (primary source)
│   │   ├── SPEC.md        # This file
│   │   ├── features/
│   │   ├── api/
│   │   └── troubleshooting/
│   └── bugreport.html     # Bug report relay page
│
└── scripts/
    ├── find_port.py       # Auto port detection
    └── ...
```

---

## 12. Development Standards

### Versioning

- `feat:` → minor version bump
- `fix:` → patch version bump
- Update `VERSION` / `CHANGELOG.md` / `TODO.md` with each task

### Coding

- i18n required for Blueprint additions (`data-i18n` / `window.tr()`)
- HTML form elements must have `id` or `name`
- `type="password"` must be wrapped in `<form>`
- Inline `onclick` prohibited (use `data-action` delegation)
- DB read/write separation: GET operations must use `get_readonly_db()`

### File Size Limits

| Lines | Action |
|-----|------|
| 300 | Consider splitting |
| 500 | Practical limit |
| 800 | Split immediately |

### License Prohibition

No new GPL / LGPL / AGPL dependencies.

### Documentation

- New API: Implement MCP tool simultaneously + create in all languages `docs/{ja,en,zh-tw,zh-cn,ko}/api/`
- New feature: Create in all languages `docs/{ja,en,zh-tw,zh-cn,ko}/` (no stubs)
- Multi-language docs: `ja/` is primary source, other languages generated from ja/

### Testing

- Run Playwright tests after WebUI/CSS changes
- Verify CSS in both light & dark modes
- Test server must use ports 5100+
- Temporary files go in `tmp/` and deleted after completion

---

*This document is stored at `docs/ja/SPEC.md`. Refer to code and git log if content becomes outdated.*

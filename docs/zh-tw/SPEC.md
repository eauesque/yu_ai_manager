# Yu AI Manager — 完整規格書

> **目標讀者**: Claude Desktop 等 AI 代理  
> **版本**: v4.91.15  
> **更新時間**: 2026-04-19

---

## 目錄

1. [項目概述](#1-項目概述)
2. [技術堆疊](#2-技術堆疊)
3. [架構概述](#3-架構概述)
4. [認證與安全](#4-認證與安全)
5. [REST API 端點](#5-rest-api-端點)
6. [MCP 伺服器](#6-mcp-伺服器)
7. [SSE 事件](#7-sse-事件)
8. [DB 架構](#8-db-架構)
9. [擴充功能（Extensions）](#9-擴充功能extensions)
10. [設定（config.json）](#10-設定configjson)
11. [檔案結構](#11-檔案結構)
12. [開發規範](#12-開發規範)

---

## 1. 項目概述

**Yu AI Manager** 是 AI 生成圖像、動畫、音聲、文本的本地媒體庫管理系統。  
設計思想為邊緣優先、雲端獨立，優先實現本地/LAN 完全自主運行。

### 主要功能

| 功能 | 說明 |
|------|------|
| 媒體庫管理 | 圖像/動畫/音聲/文本的掃描、標籤、搜索 |
| 元數據抽取 | A1111 / ComfyUI / NovelAI 生成參數自動抽取 |
| AI 分析 | Claude / OpenAI / Ollama / Hailo VLM 圖像解析 |
| 語義搜索 | CLIP (ONNX/CoreML) + Hailo 語義搜索 |
| Bridge 連携 | Stable Diffusion / ComfyUI / NovelAI 生成請求 |
| LLM Router | Ollama / OpenAI 兼容後端統合路由 |
| Agent Safety | Kill Switch / Circuit Breaker / Approval Gate 等安全機制 |
| LAN 協業 | mDNS 自動發現 + 節點間共享 |
| MCP 伺服器 | Claude Desktop 等直接操作的 180+ 工具 |

---

## 2. 技術堆疊

| 層級 | 技術 |
|---------|------|
| Backend | Python 3.11+ / Quart (async) / Hypercorn |
| Database | SQLite3 (FTS5 全文搜索 + zstd 壓縮 BLOB) |
| Frontend | TypeScript + Vite 構建 |
| Desktop | Tauri (Rust) |
| MCP | FastMCP (Anthropic MCP Server) |
| LLM | Claude API / OpenAI API / Ollama / Hailo VLM |
| Inference | ONNX Runtime / CoreML / Hailo Runtime |
| 套件管理 | Python: `uv pip` / Node.js: `pnpm` |

### 埠口規範

- `5000–5099`: 生產應用預留帶寬（禁止修改）
- `5100+`: 測試・偵錯用（`scripts/find_port.py` 自動獲取空閒埠口）

---

## 3. 架構概述

```
┌──────────────────────────────────────────────────┐
│  客戶端層                                    │
│  ├─ Web UI (TypeScript / Tauri)                  │
│  ├─ Claude Desktop (MCP)                         │
│  └─ 外部工具 (API Key / LAN Peer)               │
├──────────────────────────────────────────────────┤
│  認證層 (auth_chain.py)                           │
│  ├─ PIN / QuickLock (老闆鎖)                  │
│  ├─ API Key (Bearer / 範圍)                   │
│  └─ LAN 節點信任 (mDNS 驗證)                      │
├──────────────────────────────────────────────────┤
│  API 層                                           │
│  ├─ REST API (235+ 端點 / Quart Blueprint)│
│  ├─ SSE 串流 (/api/events/stream)           │
│  └─ MCP 伺服器 (180+ 工具)                    │
├──────────────────────────────────────────────────┤
│  服務層                                        │
│  ├─ TagDB (SQLite / 架構 v53)                 │
│  ├─ Event Bus (SSE 廣播)             │
│  ├─ LLM Router (多後端統合)              │
│  ├─ Analysis Engine (Claude/OpenAI/Ollama/Hailo) │
│  ├─ Extensions (47 內置)                      │
│  └─ File Services (掃描/服務/縮圖)    │
├──────────────────────────────────────────────────┤
│  Agent Safety 層                                  │
│  ├─ Kill Switch          ├─ Budget Tracker        │
│  ├─ Circuit Breaker      ├─ Approval Gate         │
│  ├─ Scope Fence          ├─ Undo Engine           │
│  ├─ Anomaly Detector     └─ Audit Bureau          │
└──────────────────────────────────────────────────┘
```

### モジュール依存方向

```
routes/ → core/services_core/ → core/tagdb_core/ → SQLite
routes/ → core/web/ (認證)
mcp_server/ → routes/ 經由 or 核心直接呼叫
extensions/ → core/extensions_core/ (生命週期管理)
```

---

## 4. 認證與安全

### 認證チェーン (core/web/auth_chain.py)

每個請求按以下順序評估:

1. **靜態檔案繞過** — `/static/`, `/favicon.ico`, `/help/*`
2. **MCP 繞過** — `/mcp` (MCP 自身認證)
3. **LLM Router 繞過** — `/v1/` (迴環時僅)
4. **LAN Share 繞過** — `/s/<token>` (共享令牌)
5. **LAN 節點信任** — mDNS 驗證的節點無需 PIN
6. **API 金鑰認證** — `Authorization: Bearer <key>` (範圍驗證)
7. **QuickLock 檢查** — 鎖定時僅許可 `/api/lock/unlock`
8. **PIN 檢查** — 瀏覽器工作階段認證

### API 金鑰範圍

| 範圍 | 權限 |
|---------|------|
| `read` | 全般讀取 |
| `write` | 檔案・設定寫入 |
| `tag.write` | 標籤新增・刪除 |
| `collection.write` | 合集管理 |
| `annotate` | 註釋 |
| `scan` | 掃描操作 |
| `admin` | 管理員（全操作） |

### QuickLock / Boss Mode

- PIN 透過 PBKDF2-SHA256 (600k iterations) 雜湊化
- 速率限制: 最大 5 次失敗後 60 秒鎖定
- `/api/lock/status` 檢查鎖定狀態（認證不需）
- `/api/lock/unlock` 解除（PIN 必須）

### 秘鑰管理

- 1Password 統合 (`op://vault/item/field` 參考格式)
- Bitwarden 統合
- 設定值透過 Fernet 對稱加密 (`enc:...` 前綴)

---

## 5. REST API 端點

基礎 URL: `http://localhost:5000`（預設）

### Agent Safety

| 方法 | 路徑 | 說明 |
|---------|------|------|
| GET | `/api/agent/status` | Kill Switch + CB + Budget 統合狀態 |
| POST | `/api/agent/kill` | Kill Switch 啟用 |
| POST | `/api/agent/resume` | Kill Switch 停用 |
| GET | `/api/agent/circuit-breaker` | Circuit Breaker 狀態 |
| POST | `/api/agent/circuit-breaker/reset` | CB 重設 |
| GET | `/api/agent/budget` | 預算剩餘 |
| POST | `/api/agent/budget/reset` | 預算重設 |
| GET | `/api/agent/journal` | 動作日誌搜索 |
| GET | `/api/agent/journal/stats` | 日誌統計 |
| GET | `/api/agent/approval` | 待批准請求列表 |
| POST | `/api/agent/approval/<request_id>` | 批准/拒絕 |
| GET | `/api/agent/approval/history` | 批准歷史 |
| POST | `/api/agent/undo/<int:journal_id>` | 執行撤銷 |
| GET | `/api/agent/undoable` | 可撤銷日誌 |
| GET | `/api/agent/anomaly` | 異常檢測警報 |
| GET | `/api/agent/audit` | 審計日誌 |
| GET | `/api/agent/scope` | 範圍一覧 |
| GET | `/api/agent/scope/<session_id>` | セッション範圍 |
| POST | `/api/agent/scope/<session_id>` | 範圍更新時間 |
| DELETE | `/api/agent/scope/<session_id>` | 範圍刪除 |
| GET | `/api/agent/auto-approve` | 自動批准規則 |
| POST | `/api/agent/auto-approve` | 規則新增 |
| DELETE | `/api/agent/auto-approve/<int:index>` | 規則刪除 |
| GET | `/api/agent/tool-levels` | 工具安全等級 |

### AI 分析

| 方法 | 路徑 | 說明 |
|---------|------|------|
| GET | `/api/analysis/config` | 設定取得 |
| POST | `/api/analysis/config` | 設定更新時間 |
| GET | `/api/analysis/available-engines` | 可用引擎列表 |
| GET | `/api/analysis/ollama/models` | Ollama 模型列表 |
| POST | `/api/analysis/ollama/test` | 連線測試 |
| POST | `/api/analysis/analyze/<int:file_id>` | 檔案分析 |
| GET | `/api/analysis/result/<int:file_id>` | 分析結果 |
| POST | `/api/analysis/batch` | 批量分析 |
| POST | `/api/analysis/batch/cancel` | 批量取消 |
| GET | `/api/analysis/servers` | 分析伺服器列表 |
| POST | `/api/analysis/servers` | 伺服器新增 |
| PUT | `/api/analysis/servers/<server_id>` | 伺服器更新時間 |
| DELETE | `/api/analysis/servers/<server_id>` | 伺服器刪除 |
| GET | `/api/analysis/servers/discovered` | 自動發現伺服器 |
| POST | `/api/analysis/servers/discovered/register` | 註冊 |

### 檔案・掃描

| 方法 | 路徑 | 說明 |
|---------|------|------|
| POST | `/api/scan/start` | 掃描開始 |
| POST | `/api/scan/cancel` | 取消 |
| POST | `/api/scan/resume` | 繼續 |
| GET | `/api/scan/status` | 狀態 |
| GET | `/api/scan/queue` | 佇列列表 |
| DELETE | `/api/scan/queue/<queue_id>` | 佇列刪除 |
| POST | `/api/scan/queue/clear` | 佇列清除 |
| GET | `/api/scan/history` | 掃描歷史 |
| GET | `/api/scan-errors` | 掃描錯誤 |
| POST | `/api/scan-errors/<int:error_id>/resolve` | 錯誤解決 |
| GET | `/api/scanned-roots` | 已掃描根目錄 |
| POST | `/api/scanned-roots/purge` | 根目錄刪除 |

### 標籤・收藏・評級

| 方法 | 路徑 | 說明 |
|---------|------|------|
| POST | `/api/tags/add` | 標籤新增 |
| POST | `/api/tags/remove` | 標籤刪除 |
| GET | `/api/tags/list` | 標籤列表 |
| POST | `/api/favorites/toggle` | 收藏切換 |
| GET | `/api/favorites/check` | 收藏檢查 |
| GET | `/api/favorites/list` | 收藏列表 |
| GET | `/api/ratings/get` | 評級取得 |
| POST | `/api/ratings/set` | 評級設定 |
| POST | `/api/ratings/batch-set` | 批量設定 |
| GET | `/api/ratings/stats` | 統計 |

### 合集

| 方法 | 路徑 | 說明 |
|---------|------|------|
| GET | `/api/collections` | 合集一覧 |
| POST | `/api/collections` | 建立 |
| PUT | `/api/collections/<int:collection_id>` | 更新時間 |
| DELETE | `/api/collections/<int:collection_id>` | 刪除 |
| POST | `/api/collections/reorder` | 重新排列 |
| POST | `/api/collections/<int:collection_id>/batch-add` | 批量新增 |
| POST | `/api/collections/<int:collection_id>/batch-remove` | バッチ刪除 |
| GET | `/api/collections/<int:collection_id>/export/csv` | CSV 匯出 |

### LLM Router

| 方法 | 路徑 | 說明 |
|---------|------|------|
| GET | `/api/llm_router/status` | 狀態 |
| POST | `/api/llm_router/refresh` | 重新整理 |
| POST | `/api/llm_router/backends/<alias>/enable` | 後端啟用 |
| POST | `/api/llm_router/backends/<alias>/disable` | 後端停用 |
| POST | `/v1/chat/completions` | OpenAI 兼容聊天 |
| GET | `/v1/models` | 模型列表 |

### 系統・伺服器資訊

| 方法 | 路徑 | 說明 |
|---------|------|------|
| GET | `/api/system/inference-info` | 推論引擎資訊 |
| GET | `/api/mdns/identity` | mDNS 身分 |
| GET | `/api/mdns/peers` | LAN 節點列表 |
| GET | `/api/logs/recent` | 最近日誌 |
| GET | `/api/logs/stream` | 日誌 SSE 串流 |
| GET | `/api/jobs/status` | 工作狀態 |
| GET | `/api/events/stream` | SSE 事件ストリーム |
| GET | `/api/events/info` | SSE 連線資訊 |

### 設定・秘鑰

| 方法 | 路徑 | 說明 |
|---------|------|------|
| GET/POST | `/api/settings/llm-endpoints` | LLM 端點管理 |
| GET/POST | `/api/settings/secrets/*` | 秘鑰管理 |
| GET | `/api/settings/bw-status` | Bitwarden 狀態 |
| GET | `/api/settings/op-status` | 1Password 狀態 |

### 說明

| 方法 | 路徑 | 說明 |
|---------|------|------|
| GET | `/api/help/toc` | 目錄 |
| GET | `/api/help/content/<section>` | 內容 |
| GET | `/api/help/search` | 搜索 |

---

## 6. MCP 伺服器

### 接続

```
Transport: stdio 或 SSE
端點: /mcp (SSE 模式時)
```

### ツール グループ (180+ 工具)

| グループ | 註冊関数 | 主なツール |
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

### Safety インターセプター

全 MCP ツール呼び出しは以下を自動チェック:
1. Kill Switch — 有効時は全ツール実行拒否
2. Circuit Breaker — 連続エラー時に自動遮断
3. Budget Tracker — 予算超過時に警告/停止
4. Approval Gate — `admin` 範圍操作は人間承認待ち
5. Scope Fence — セッション範圍外アクセス拒否

---

## 7. SSE 事件

### 接続

```
GET /api/events/stream?types=<event1>,<event2>,...
Content-Type: text/event-stream
```

`types` 省略で全事件受信。

### 事件一覧

**スキャン**

| 事件 | 說明 |
|---------|------|
| `scan.start` | 掃描開始 |
| `scan.progress` | 進捗（processed/total） |
| `scan.complete` | 完了 |
| `scan.error` | エラー |
| `scan.queued` | キュー註冊 |

**ファイル操作**

| 事件 | 說明 |
|---------|------|
| `favorite.add` / `favorite.remove` | お気に入り |
| `tag.add` / `tag.remove` | タグ |
| `rating.set` / `rating.clear` | レーティング |
| `annotation.set` / `annotation.delete` | 註釋 |
| `collection.create` / `collection.delete` | 合集 |

**生成**

| 事件 | 說明 |
|---------|------|
| `generation.submit` | 生成依頼 |
| `generation.progress` | 進捗 |
| `generation.complete` | 完了 |
| `generation.error` | エラー |
| `generation.cancel` | 取消 |

**分析・推論**

| 事件 | 說明 |
|---------|------|
| `analysis.complete` | 分析完了 |
| `batch_analysis.complete` | バッチ完了 |
| `semantic_index.start/progress/complete` | インデックス |
| `yolo_detect.start/progress/complete` | 物体検出 |
| `wd_tagger.complete` | WD-Tagger 完了 |
| `ocr.complete` | OCR 完了 |

**Agent Safety**

| 事件 | 說明 |
|---------|------|
| `agent.killed` | Kill Switch 有効 |
| `agent.resumed` | 繼續 |
| `agent.circuit_open` | Circuit Breaker 開放 |
| `agent.circuit_closed` | 閉鎖 |
| `agent.budget_warning` | 予算警告 |
| `agent.budget_exhausted` | 予算枯渇 |

**LAN 協業**

| 事件 | 說明 |
|---------|------|
| `peer.discovered` | ピア発見 |
| `peer.online` / `peer.offline` | 状態変化 |
| `sync.file_changed` / `sync.file_received` | ファイル同期 |
| `sync.conflict` | 競合 |

**その他**

| 事件 | 說明 |
|---------|------|
| `scheduler.job_executed` | スケジューラジョブ実行 |
| `backup.complete` / `backup.error` | バックアップ |
| `config.scan_roots_changed` | スキャンルート変更 |
| `watcher.started` / `watcher.stopped` | ファイル監視 |
| `webhook.received` | Webhook 受信 |
| `github_queue.new_issues` | GitHub 新規 Issue |
| `bsky_queue.new_notifications` | Bluesky 新規通知 |
| `chatlog_reprocess.start/progress/complete` | チャットログ再処理 |
| `fpb.start/progress/complete/error` | Freeze & Pull-back |

---

## 8. DB 架構

**DB ファイル**: `tags.db`（トップディレクトリ、`--db` で指定可）  
**架構版本**: 53  
**読み書き分離**: GET 系は `get_readonly_db()` 使用必須

### 主要テーブル

```sql
-- ファイル
files (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  mtime INTEGER,
  size INTEGER,
  hash TEXT,
  is_deleted INTEGER DEFAULT 0,         -- ソフトデリート
  parser_version INTEGER DEFAULT 1,
  meta_source TEXT,
  is_zip_member INTEGER DEFAULT 0,
  extracted_from_zip TEXT,
  extracted_from_internal TEXT,
  extraction_date INTEGER,
  extracted_to_file_id INTEGER,
  width INTEGER,
  height INTEGER,
  file_ext TEXT GENERATED ALWAYS AS     -- 自動生成
    (lower(substr(path, instr(path,'.',-1)+1))) STORED
)

-- タグ辞書
tags (
  id INTEGER PRIMARY KEY,
  tag TEXT NOT NULL,
  namespace TEXT,                        -- "namespace:tag" 形式
  first_seen_mtime INTEGER,
  UNIQUE(tag, namespace)
)

-- ファイル↔タグ関連
file_tags (
  file_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  weight REAL DEFAULT 1.0,              -- タグ重みづけ
  source TEXT DEFAULT 'meta',           -- 'meta'|'manual'|'ai'|'wd'
  PRIMARY KEY (file_id, tag_id)
)

-- 生成パラメータ
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

-- プロンプトトークン
template_tokens (
  id INTEGER PRIMARY KEY,
  template_id INTEGER NOT NULL,
  token_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  position INTEGER NOT NULL
)

-- 元數據抽取状態
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

-- ファイルキャッシュ（サムネイル等）
cache_entry (
  cache_key TEXT PRIMARY KEY,
  kind TEXT NOT NULL,                    -- 'thumbnail'|'preview'|'clip_emb'
  path TEXT NOT NULL,
  file_id INTEGER,
  size_bytes INTEGER DEFAULT 0,
  last_access_at INTEGER,
  updated_at INTEGER
)

-- お気に入り
favorites (
  file_id INTEGER NOT NULL,
  collection_id INTEGER DEFAULT 1,
  added_at INTEGER,
  PRIMARY KEY (file_id, collection_id)
)

-- 架構版本管理
schema_version (
  version INTEGER PRIMARY KEY,
  applied_at INTEGER,
  description TEXT
)

-- 拡張別架構版本
extension_schema_versions (
  extension_name TEXT NOT NULL,
  version INTEGER NOT NULL,
  applied_at INTEGER,
  description TEXT,
  PRIMARY KEY (extension_name, version)
)

-- DB メタ情報
db_meta (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at INTEGER
)
```

### FTS5（全文搜索）

```sql
-- プロンプト全文搜索
templates_fts USING fts5 (
  content='templates',
  raw_prompt, raw_negative, model_name
)
```

注意: CJK 文字は FTS5 が非対応のため LIKE フォールバックを使用。

### 主要インデックス

```sql
idx_tags_tag_lower          -- タグ大文字小文字区別なし
idx_files_deleted_mtime     -- ソフトデリート + mtime
idx_files_deleted_source    -- ソフトデリート + ソース
idx_file_tags_tag_id        -- タグID搜索
idx_file_tags_source        -- メタデータソース
idx_media_extract_cache_state -- キャッシュ状態
idx_media_extract_next_retry  -- リトライ待機
idx_files_hash              -- ハッシュ（重複検出）
idx_files_deleted_ext       -- 拡張子フィルタ
```

---

## 9. 擴充功能（Extensions）

### 構成

```
extensions/
  builtin-<name>/
    extension.json     # メタデータ
    <name>_ext.py      # エントリーポイント
    templates/         # HTML テンプレート
    static/            # 静的ファイル
```

### extension.json フォーマット

```json
{
  "name": "builtin-analysis",
  "version": "1.0.0",
  "description": "AI 画像分析エンジン",
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

### ビルトイン拡張一覧（47 個）

| 拡張名 | カテゴリ | 說明 |
|--------|---------|------|
| builtin-a1111 | parser | A1111 元數據抽取 |
| builtin-analysis | ai | AI 画像分析（Claude/OpenAI/Ollama） |
| builtin-annotations | utility | 註釋管理 |
| builtin-audio-analysis | ai | 音声分析（Whisper） |
| builtin-auto-scan-watcher | utility | ファイル変更自動スキャン |
| builtin-backup | utility | DB/設定バックアップ |
| builtin-chatlog | utility | チャットログ管理 |
| builtin-clip-coreml | ai | CLIP 語義搜索（macOS） |
| builtin-clip-onnx | ai | CLIP 語義搜索（クロスプラットフォーム） |
| builtin-clip-search | search | CLIP 搜索 UI |
| builtin-comfyui | parser | ComfyUI 元數據抽取 |
| builtin-comfyui-bridge | bridge | ComfyUI API 連携 |
| builtin-cross-search | search | テキスト全文搜索 |
| builtin-debug-check | utility | システム診断 |
| builtin-download | utility | URL/磁力リンクダウンロード |
| builtin-export | utility | CSV/JSON/ZIP エクスポート |
| builtin-favorites-manager | utility | お気に入り・合集 |
| builtin-freeze-pullback | utility | ファイル復元 |
| builtin-github-integration | integration | GitHub Issue/PR 管理 |
| builtin-hailo-genai | ai | Hailo 生成 AI |
| builtin-hailo-semantic-search | search | Hailo 語義搜索 |
| builtin-hailo-yolo-detect | ai | Hailo YOLO 物体検出 |
| builtin-inference | ai | リモート推論管理 |
| builtin-lan-cowork | network | LAN 協業 |
| builtin-lan-share | network | LAN QR 共有 |
| builtin-lora-dataset-manager | utility | LoRA データセット（kohya-ss 連携） |
| builtin-mcp-client | integration | 外部 MCP 伺服器接続 |
| builtin-md-viewer | utility | Markdown ファイル表示 |
| builtin-nai-bridge | bridge | NovelAI API 連携 |
| builtin-novelai-v3 | parser | NovelAI v3 メタデータ |
| builtin-novelai-v4 | parser | NovelAI v4 メタデータ |
| builtin-ocr | ai | OCR テキスト抽出 |
| builtin-prompt-library | utility | プロンプト管理・搜索 |
| builtin-prompt-simulator | utility | ワイルドカード展開 |
| builtin-prompt-syntax | utility | Lora/制御トークン解析 |
| builtin-ratings | utility | 5 段階評価 |
| builtin-sd-nai-convert | utility | SD ↔ NAI プロンプト変換 |
| builtin-sd-webui-bridge | bridge | SD WebUI API 連携 |
| builtin-sns-share | integration | SNS 投稿（Bluesky/Twitter） |
| builtin-speech-to-text | ai | 音声認識 |
| builtin-stats | utility | 統計ダッシュボード |
| builtin-tag-dictionary | utility | タグ辞書・說明 |
| builtin-trophy | utility | マイルストーン達成 |
| builtin-video-analysis | ai | 動画キーフレーム分析 |
| builtin-wd-tagger | ai | WD-Tagger 自動タグ生成 |
| builtin-webhook | integration | Webhook 送受信 |

---

## 10. 設定（config.json）

**路徑**: `{プロジェクトルート}/config.json`

```json
{
  "scan_roots": [
    {
      "path": "/path/to/images",
      "enabled": true,
      "recursive": true,
      "comment": "メイン画像フォルダ"
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

### 環境変数

| 変数 | 說明 |
|-----|------|
| `TAGDB_DATA_DIR` | データディレクトリ |
| `TAGDB_CACHE_DIR` | キャッシュディレクトリ |
| `TAGDB_LOG_DIR` | ログディレクトリ |
| `TAGDB_PROFILES_DIR` | プロフィールディレクトリ |
| `YU_DEBUG_MODE` | `1` でデバッグ API 有効 |

---

## 11. 檔案結構

```
O:/yu_ai_manager/
├── web_ui.py              # ASGI エントリーポイント
├── app.py                 # Quart アプリ初期化
├── config.json            # メイン設定
├── tags.db                # 開発用 DB（--db で指定）
├── VERSION                # 版本番号
├── CHANGELOG.md           # 変更履歴
├── TODO.md                # 課題管理
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
├── core/                  # コアモジュール
│   ├── agent_safety/      # 安全機構
│   ├── analysis/          # AI 分析エンジン
│   ├── event_bus/         # 事件バス
│   ├── extensions_core/   # 拡張ライフサイクル
│   ├── files_core/        # ファイルサーブ
│   ├── infra_core/        # API レスポンス等
│   ├── llm_router/        # LLM ルーティング
│   ├── scan_core/         # スキャン
│   ├── schema_core/       # DB 架構・マイグレーション
│   ├── services_core/     # DB 非同期アダプター
│   ├── settings_core/     # 設定管理
│   ├── sse/               # SSE ブロードキャスター
│   ├── tagdb_core/        # タグ DB コア
│   └── web/               # 認證・リクエスト処理
│
├── mcp_server/            # MCP 伺服器（180+ ツール）
│   ├── server.py          # FastMCP エントリー
│   ├── tools/             # ツール定義
│   └── interceptor.py     # Safety インターセプター
│
├── extensions/            # 拡張（47 builtin）
│   └── builtin-*/
│
├── src/ts/                # TypeScript フロントエンド
│   ├── main/              # メイン画面
│   ├── nav/               # ナビゲーション
│   ├── tools-page/        # ツールページ
│   └── types/             # 型定義
│
├── src-tauri/             # Tauri デスクトップ
│
├── ui/default/            # HTML テンプレート
│   ├── templates/
│   └── static/dist/       # ビルド済み JS
│
├── docs/                  # ドキュメント（ja/ が一次）
│   ├── ja/                # 日本語（一次ソース）
│   │   ├── SPEC.md        # 本ファイル
│   │   ├── features/
│   │   ├── api/
│   │   └── troubleshooting/
│   └── bugreport.html     # バグ報告リレーページ
│
└── scripts/
    ├── find_port.py       # 空きポート自動取得
    └── ...
```

---

## 12. 開發規範

### バージョニング

- `feat:` → minor 版本アップ
- `fix:` → patch 版本アップ
- 作業のたびに `VERSION` / `CHANGELOG.md` / `TODO.md` を更新時間

### コーディング

- Blueprint 追加時は i18n 必須（`data-i18n` / `window.tr()`）
- HTML フォーム要素には `id` または `name` を付与
- `type="password"` は `<form>` で囲む
- インライン `onclick` 禁止（`data-action` デリゲーション使用）
- DB 読み書き分離: GET 系は必ず `get_readonly_db()` を使う

### ファイルサイズ制限

| 行数 | 対応 |
|-----|------|
| 300 | 分割検討 |
| 500 | 実用上限 |
| 800 | 即分割 |

### 許可證禁止

禁止新增 GPL / LGPL / AGPL 系依賴。

### 文件

- 新 API: 同時實現 MCP 工具 + `docs/{ja,en,zh-tw,zh-cn,ko}/api/` 全語言建立
- 新功能: `docs/{ja,en,zh-tw,zh-cn,ko}/` 全語言建立（禁止存根）
- 多語言文件以 `ja/` 為主要來源，其他語言由 ja/ 生成

### 測試

- WebUI/CSS 變更後執行 Playwright 測試
- CSS 確認亮・暗兩種模式
- 測試伺服器必須使用 5100 號及以上埠口
- 臨時檔案放在 `tmp/` 下，完成後刪除

---

*本文件儲存於 `docs/ja/SPEC.md`。內容過時時請參考代碼和 git 日誌。*

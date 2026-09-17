# Yu AI Manager — Especificación General

> **Audiencia objetivo**: Claude Desktop などの AI エージェント  
> **Versión**: v4.91.15  
> **Actualizado**: 2026-04-19

---

## Índice de Contenidos

1. [Descripción General del Proyecto](#1-Descripción General del Proyecto)
2. [Stack Técnico](#2-Stack Técnico)
3. [Descripción de Arquitectura](#3-Descripción de Arquitectura)
4. [Autenticación y Seguridad](#4-認証セキュリティ)
5. [Endpoints REST API](#5-rest-api-エンドポイント)
6. [Servidor MCP](#6-mcp-サーバー)
7. [Eventos SSE](#7-sse-イベント)
8. [Esquema DB](#8-db-スキーマ)
9. [Extensiones (Extensions)](#9-拡張extensions)
10. [Configuración (config.json)](#10-設定configjson)
11. [Estructura de Archivos](#11-Estructura de Archivos)
12. [Convenciones de Desarrollo](#12-Convenciones de Desarrollo)

---

## 1. Descripción General del Proyecto

**Yu AI Manager** は、AI 生成画像・動画・音声・テキストのローカルライブラリ管理システム。  
エッジファースト・クラウド非依存を設計思想とし、ローカル/LAN で完結することを優先する。

### 主要機能

| 機能 | 説明 |
|------|------|
| ライブラリ管理 | 画像/動画/音声/テキストのスキャン・タグ付け・検索 |
| メタデータ抽出 | A1111 / ComfyUI / NovelAI 生成パラメータの自動抽出 |
| AI 分析 | Claude / OpenAI / Ollama / Hailo VLM による画像解析 |
| セマンティック検索 | CLIP (ONNX/CoreML) + Hailo による意味検索 |
| Bridge 連携 | Stable Diffusion / ComfyUI / NovelAI への生成依頼 |
| LLM Router | Ollama / OpenAI 互換バックエンドへの統合ルーティング |
| Agent Safety | Kill Switch / Circuit Breaker / Approval Gate 等の安全機構 |
| LAN 協業 | mDNS による自動発見 + ピア間共有 |
| Servidor MCP | Claude Desktop 等から直接操作可能な 180+ ツール |

---

## 2. Stack Técnico

| レイヤー | 技術 |
|---------|------|
| Backend | Python 3.11+ / Quart (async) / Hypercorn |
| Database | SQLite3 (FTS5 全文検索 + zstd 圧縮 BLOB) |
| Frontend | TypeScript + Vite ビルド |
| Desktop | Tauri (Rust) |
| MCP | FastMCP (Anthropic MCP Server) |
| LLM | Claude API / OpenAI API / Ollama / Hailo VLM |
| Inference | ONNX Runtime / CoreML / Hailo Runtime |
| パッケージ管理 | Python: `uv pip` / Node.js: `pnpm` |

### ポート規約

- `5000–5099`: 本番アプリ予約帯域（変更禁止）
- `5100+`: テスト・デバッグ用（`scripts/find_port.py` で空きポート自動取得）

---

## 3. Descripción de Arquitectura

```
┌──────────────────────────────────────────────────┐
│  クライアント層                                    │
│  ├─ Web UI (TypeScript / Tauri)                  │
│  ├─ Claude Desktop (MCP)                         │
│  └─ 外部ツール (API Key / LAN Peer)               │
├──────────────────────────────────────────────────┤
│  認証層 (auth_chain.py)                           │
│  ├─ PIN / QuickLock (ボスロック)                  │
│  ├─ API Key (Bearer / スコープ)                   │
│  └─ LAN ピア信頼 (mDNS 検証)                      │
├──────────────────────────────────────────────────┤
│  API 層                                           │
│  ├─ REST API (235+ エンドポイント / Quart Blueprint)│
│  ├─ SSE ストリーム (/api/events/stream)           │
│  └─ Servidor MCP (180+ ツール)                    │
├──────────────────────────────────────────────────┤
│  サービス層                                        │
│  ├─ TagDB (SQLite / スキーマ v53)                 │
│  ├─ Event Bus (SSE ブロードキャスター)             │
│  ├─ LLM Router (複数バックエンド統合)              │
│  ├─ Analysis Engine (Claude/OpenAI/Ollama/Hailo) │
│  ├─ Extensions (47 builtin)                      │
│  └─ File Services (スキャン/サーブ/サムネイル)    │
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
routes/ → core/web/ (認証)
mcp_server/ → routes/ 経由 or コア直接呼び出し
extensions/ → core/extensions_core/ (ライフサイクル管理)
```

---

## 4. Autenticación y Seguridad

### 認証チェーン (core/web/auth_chain.py)

リクエストごとに以下の順序で評価:

1. **静的ファイルバイパス** — `/static/`, `/favicon.ico`, `/help/*`
2. **MCP バイパス** — `/mcp` (MCP 自体の認証)
3. **LLM Router バイパス** — `/v1/` (ループバック時のみ)
4. **LAN Share バイパス** — `/s/<token>` (共有トークン)
5. **LAN ピア信頼** — mDNS 検証済みピアは PIN 不要
6. **API キー認証** — `Authorization: Bearer <key>` (スコープ検証)
7. **QuickLock チェック** — ロック時は `/api/lock/unlock` のみ許可
8. **PIN チェック** — ブラウザセッション認証

### API キー スコープ

| スコープ | 権限 |
|---------|------|
| `read` | 読み取り全般 |
| `write` | ファイル・設定の書き込み |
| `tag.write` | タグ追加・削除 |
| `collection.write` | コレクション管理 |
| `annotate` | アノテーション |
| `scan` | スキャン操作 |
| `admin` | 管理者（全操作） |

### QuickLock / Boss Mode

- PIN は PBKDF2-SHA256 (600k iterations) でハッシュ化
- レート制限: 最大 5 回失敗で 60 秒ロックアウト
- `/api/lock/status` でロック状態確認（認証不要）
- `/api/lock/unlock` で解除（PIN 必須）

### シークレット管理

- 1Password 統合 (`op://vault/item/field` 参照形式)
- Bitwarden 統合
- 設定値は Fernet 対称暗号化 (`enc:...` プレフィックス)

---

## 5. Endpoints REST API

ベース URL: `http://localhost:5000`（デフォルト）

### Agent Safety

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/agent/status` | Kill Switch + CB + Budget 統合状態 |
| POST | `/api/agent/kill` | Kill Switch 有効化 |
| POST | `/api/agent/resume` | Kill Switch 無効化 |
| GET | `/api/agent/circuit-breaker` | Circuit Breaker 状態 |
| POST | `/api/agent/circuit-breaker/reset` | CB リセット |
| GET | `/api/agent/budget` | 予算残量 |
| POST | `/api/agent/budget/reset` | 予算リセット |
| GET | `/api/agent/journal` | アクションジャーナル検索 |
| GET | `/api/agent/journal/stats` | ジャーナル統計 |
| GET | `/api/agent/approval` | 承認待ちリクエスト一覧 |
| POST | `/api/agent/approval/<request_id>` | 承認/却下 |
| GET | `/api/agent/approval/history` | 承認履歴 |
| POST | `/api/agent/undo/<int:journal_id>` | アンドゥ実行 |
| GET | `/api/agent/undoable` | アンドゥ可能ジャーナル |
| GET | `/api/agent/anomaly` | 異常検出アラート |
| GET | `/api/agent/audit` | 監査ログ |
| GET | `/api/agent/scope` | スコープ一覧 |
| GET | `/api/agent/scope/<session_id>` | セッションスコープ |
| POST | `/api/agent/scope/<session_id>` | スコープActualizado |
| DELETE | `/api/agent/scope/<session_id>` | スコープ削除 |
| GET | `/api/agent/auto-approve` | オート承認ルール |
| POST | `/api/agent/auto-approve` | ルール追加 |
| DELETE | `/api/agent/auto-approve/<int:index>` | ルール削除 |
| GET | `/api/agent/tool-levels` | ツール安全レベル |

### AI 分析

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/analysis/config` | 設定取得 |
| POST | `/api/analysis/config` | 設定Actualizado |
| GET | `/api/analysis/available-engines` | 利用可能エンジン一覧 |
| GET | `/api/analysis/ollama/models` | Ollama モデル一覧 |
| POST | `/api/analysis/ollama/test` | 接続テスト |
| POST | `/api/analysis/analyze/<int:file_id>` | ファイル分析 |
| GET | `/api/analysis/result/<int:file_id>` | 分析結果 |
| POST | `/api/analysis/batch` | バッチ分析 |
| POST | `/api/analysis/batch/cancel` | バッチキャンセル |
| GET | `/api/analysis/servers` | 分析サーバー一覧 |
| POST | `/api/analysis/servers` | サーバー追加 |
| PUT | `/api/analysis/servers/<server_id>` | サーバーActualizado |
| DELETE | `/api/analysis/servers/<server_id>` | サーバー削除 |
| GET | `/api/analysis/servers/discovered` | 自動発見サーバー |
| POST | `/api/analysis/servers/discovered/register` | 登録 |

### ファイル・スキャン

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/api/scan/start` | スキャン開始 |
| POST | `/api/scan/cancel` | キャンセル |
| POST | `/api/scan/resume` | 再開 |
| GET | `/api/scan/status` | ステータス |
| GET | `/api/scan/queue` | キュー一覧 |
| DELETE | `/api/scan/queue/<queue_id>` | キュー削除 |
| POST | `/api/scan/queue/clear` | キュークリア |
| GET | `/api/scan/history` | スキャン履歴 |
| GET | `/api/scan-errors` | スキャンエラー |
| POST | `/api/scan-errors/<int:error_id>/resolve` | エラー解決 |
| GET | `/api/scanned-roots` | スキャン済みルート |
| POST | `/api/scanned-roots/purge` | ルート削除 |

### タグ・お気に入り・レーティング

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/api/tags/add` | タグ追加 |
| POST | `/api/tags/remove` | タグ削除 |
| GET | `/api/tags/list` | タグ一覧 |
| POST | `/api/favorites/toggle` | お気に入りトグル |
| GET | `/api/favorites/check` | お気に入り確認 |
| GET | `/api/favorites/list` | お気に入り一覧 |
| GET | `/api/ratings/get` | レーティング取得 |
| POST | `/api/ratings/set` | レーティング設定 |
| POST | `/api/ratings/batch-set` | バッチ設定 |
| GET | `/api/ratings/stats` | 統計 |

### コレクション

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/collections` | コレクション一覧 |
| POST | `/api/collections` | 作成 |
| PUT | `/api/collections/<int:collection_id>` | Actualizado |
| DELETE | `/api/collections/<int:collection_id>` | 削除 |
| POST | `/api/collections/reorder` | 並べ替え |
| POST | `/api/collections/<int:collection_id>/batch-add` | バッチ追加 |
| POST | `/api/collections/<int:collection_id>/batch-remove` | バッチ削除 |
| GET | `/api/collections/<int:collection_id>/export/csv` | CSV エクスポート |

### LLM Router

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/llm_router/status` | ステータス |
| POST | `/api/llm_router/refresh` | リフレッシュ |
| POST | `/api/llm_router/backends/<alias>/enable` | バックエンド有効化 |
| POST | `/api/llm_router/backends/<alias>/disable` | バックエンド無効化 |
| POST | `/v1/chat/completions` | OpenAI 互換チャット |
| GET | `/v1/models` | モデル一覧 |

### システム・サーバー情報

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/system/inference-info` | 推論エンジン情報 |
| GET | `/api/mdns/identity` | mDNS アイデンティティ |
| GET | `/api/mdns/peers` | LAN ピア一覧 |
| GET | `/api/logs/recent` | 最近のログ |
| GET | `/api/logs/stream` | ログ SSE ストリーム |
| GET | `/api/jobs/status` | ジョブ状態 |
| GET | `/api/events/stream` | Eventos SSEストリーム |
| GET | `/api/events/info` | SSE 接続情報 |

### 設定・シークレット

| メソッド | パス | 説明 |
|---------|------|------|
| GET/POST | `/api/settings/llm-endpoints` | LLM エンドポイント管理 |
| GET/POST | `/api/settings/secrets/*` | シークレット管理 |
| GET | `/api/settings/bw-status` | Bitwarden 状態 |
| GET | `/api/settings/op-status` | 1Password 状態 |

### ヘルプ

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/help/toc` | Índice de Contenidos |
| GET | `/api/help/content/<section>` | コンテンツ |
| GET | `/api/help/search` | 検索 |

---

## 6. Servidor MCP

### 接続

```
Transport: stdio または SSE
エンドポイント: /mcp (SSE モード時)
```

### ツール グループ (180+ ツール)

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

### Safety インターセプター

全 MCP ツール呼び出しは以下を自動チェック:
1. Kill Switch — 有効時は全ツール実行拒否
2. Circuit Breaker — 連続エラー時に自動遮断
3. Budget Tracker — 予算超過時に警告/停止
4. Approval Gate — `admin` スコープ操作は人間承認待ち
5. Scope Fence — セッションスコープ外アクセス拒否

---

## 7. Eventos SSE

### 接続

```
GET /api/events/stream?types=<event1>,<event2>,...
Content-Type: text/event-stream
```

`types` 省略で全イベント受信。

### イベント一覧

**スキャン**

| イベント | 説明 |
|---------|------|
| `scan.start` | スキャン開始 |
| `scan.progress` | 進捗（processed/total） |
| `scan.complete` | 完了 |
| `scan.error` | エラー |
| `scan.queued` | キュー登録 |

**ファイル操作**

| イベント | 説明 |
|---------|------|
| `favorite.add` / `favorite.remove` | お気に入り |
| `tag.add` / `tag.remove` | タグ |
| `rating.set` / `rating.clear` | レーティング |
| `annotation.set` / `annotation.delete` | アノテーション |
| `collection.create` / `collection.delete` | コレクション |

**生成**

| イベント | 説明 |
|---------|------|
| `generation.submit` | 生成依頼 |
| `generation.progress` | 進捗 |
| `generation.complete` | 完了 |
| `generation.error` | エラー |
| `generation.cancel` | キャンセル |

**分析・推論**

| イベント | 説明 |
|---------|------|
| `analysis.complete` | 分析完了 |
| `batch_analysis.complete` | バッチ完了 |
| `semantic_index.start/progress/complete` | インデックス |
| `yolo_detect.start/progress/complete` | 物体検出 |
| `wd_tagger.complete` | WD-Tagger 完了 |
| `ocr.complete` | OCR 完了 |

**Agent Safety**

| イベント | 説明 |
|---------|------|
| `agent.killed` | Kill Switch 有効 |
| `agent.resumed` | 再開 |
| `agent.circuit_open` | Circuit Breaker 開放 |
| `agent.circuit_closed` | 閉鎖 |
| `agent.budget_warning` | 予算警告 |
| `agent.budget_exhausted` | 予算枯渇 |

**LAN 協業**

| イベント | 説明 |
|---------|------|
| `peer.discovered` | ピア発見 |
| `peer.online` / `peer.offline` | 状態変化 |
| `sync.file_changed` / `sync.file_received` | ファイル同期 |
| `sync.conflict` | 競合 |

**その他**

| イベント | 説明 |
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

## 8. Esquema DB

**DB ファイル**: `tags.db`（トップディレクトリ、`--db` で指定可）  
**スキーマVersión**: 53  
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

-- メタデータ抽出状態
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

-- スキーマVersión管理
schema_version (
  version INTEGER PRIMARY KEY,
  applied_at INTEGER,
  description TEXT
)

-- 拡張別スキーマVersión
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

### FTS5（全文検索）

```sql
-- プロンプト全文検索
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
idx_file_tags_tag_id        -- タグID検索
idx_file_tags_source        -- メタデータソース
idx_media_extract_cache_state -- キャッシュ状態
idx_media_extract_next_retry  -- リトライ待機
idx_files_hash              -- ハッシュ（重複検出）
idx_files_deleted_ext       -- 拡張子フィルタ
```

---

## 9. Extensiones (Extensions)

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

| 拡張名 | カテゴリ | 説明 |
|--------|---------|------|
| builtin-a1111 | parser | A1111 メタデータ抽出 |
| builtin-analysis | ai | AI 画像分析（Claude/OpenAI/Ollama） |
| builtin-annotations | utility | アノテーション管理 |
| builtin-audio-analysis | ai | 音声分析（Whisper） |
| builtin-auto-scan-watcher | utility | ファイル変更自動スキャン |
| builtin-backup | utility | DB/設定バックアップ |
| builtin-chatlog | utility | チャットログ管理 |
| builtin-clip-coreml | ai | CLIP セマンティック検索（macOS） |
| builtin-clip-onnx | ai | CLIP セマンティック検索（クロスプラットフォーム） |
| builtin-clip-search | search | CLIP 検索 UI |
| builtin-comfyui | parser | ComfyUI メタデータ抽出 |
| builtin-comfyui-bridge | bridge | ComfyUI API 連携 |
| builtin-cross-search | search | テキスト全文検索 |
| builtin-debug-check | utility | システム診断 |
| builtin-download | utility | URL/磁力リンクダウンロード |
| builtin-export | utility | CSV/JSON/ZIP エクスポート |
| builtin-favorites-manager | utility | お気に入り・コレクション |
| builtin-freeze-pullback | utility | ファイル復元 |
| builtin-github-integration | integration | GitHub Issue/PR 管理 |
| builtin-hailo-genai | ai | Hailo 生成 AI |
| builtin-hailo-semantic-search | search | Hailo セマンティック検索 |
| builtin-hailo-yolo-detect | ai | Hailo YOLO 物体検出 |
| builtin-inference | ai | リモート推論管理 |
| builtin-lan-cowork | network | LAN 協業 |
| builtin-lan-share | network | LAN QR 共有 |
| builtin-lora-dataset-manager | utility | LoRA データセット（kohya-ss 連携） |
| builtin-mcp-client | integration | 外部 Servidor MCP接続 |
| builtin-md-viewer | utility | Markdown ファイル表示 |
| builtin-nai-bridge | bridge | NovelAI API 連携 |
| builtin-novelai-v3 | parser | NovelAI v3 メタデータ |
| builtin-novelai-v4 | parser | NovelAI v4 メタデータ |
| builtin-ocr | ai | OCR テキスト抽出 |
| builtin-prompt-library | utility | プロンプト管理・検索 |
| builtin-prompt-simulator | utility | ワイルドカード展開 |
| builtin-prompt-syntax | utility | Lora/制御トークン解析 |
| builtin-ratings | utility | 5 段階評価 |
| builtin-sd-nai-convert | utility | SD ↔ NAI プロンプト変換 |
| builtin-sd-webui-bridge | bridge | SD WebUI API 連携 |
| builtin-sns-share | integration | SNS 投稿（Bluesky/Twitter） |
| builtin-speech-to-text | ai | 音声認識 |
| builtin-stats | utility | 統計ダッシュボード |
| builtin-tag-dictionary | utility | タグ辞書・説明 |
| builtin-trophy | utility | マイルストーン達成 |
| builtin-video-analysis | ai | 動画キーフレーム分析 |
| builtin-wd-tagger | ai | WD-Tagger 自動タグ生成 |
| builtin-webhook | integration | Webhook 送受信 |

---

## 10. Configuración (config.json)

**パス**: `{プロジェクトルート}/config.json`

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

| 変数 | 説明 |
|-----|------|
| `TAGDB_DATA_DIR` | データディレクトリ |
| `TAGDB_CACHE_DIR` | キャッシュディレクトリ |
| `TAGDB_LOG_DIR` | ログディレクトリ |
| `TAGDB_PROFILES_DIR` | プロフィールディレクトリ |
| `YU_DEBUG_MODE` | `1` でデバッグ API 有効 |

---

## 11. Estructura de Archivos

```
O:/yu_ai_manager/
├── web_ui.py              # ASGI エントリーポイント
├── app.py                 # Quart アプリ初期化
├── config.json            # メイン設定
├── tags.db                # 開発用 DB（--db で指定）
├── VERSION                # Versión番号
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
│   ├── event_bus/         # イベントバス
│   ├── extensions_core/   # 拡張ライフサイクル
│   ├── files_core/        # ファイルサーブ
│   ├── infra_core/        # API レスポンス等
│   ├── llm_router/        # LLM ルーティング
│   ├── scan_core/         # スキャン
│   ├── schema_core/       # Esquema DB・マイグレーション
│   ├── services_core/     # DB 非同期アダプター
│   ├── settings_core/     # 設定管理
│   ├── sse/               # SSE ブロードキャスター
│   ├── tagdb_core/        # タグ DB コア
│   └── web/               # 認証・リクエスト処理
│
├── mcp_server/            # Servidor MCP（180+ ツール）
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

## 12. Convenciones de Desarrollo

### バージョニング

- `feat:` → minor Versiónアップ
- `fix:` → patch Versiónアップ
- 作業のたびに `VERSION` / `CHANGELOG.md` / `TODO.md` をActualizado

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

### ライセンス禁止

GPL / LGPL / AGPL 系の新規依存追加禁止。

### ドキュメント

- 新規 API: MCP ツール同時実装 + `docs/{ja,en,zh-tw,zh-cn,ko}/api/` に全言語作成
- 新機能: `docs/{ja,en,zh-tw,zh-cn,ko}/` に全言語作成（スタブ禁止）
- 多言語ドキュメントは `ja/` が一次ソース、他言語は ja/ をベースに生成

### テスト

- WebUI/CSS 変更後は Playwright テスト実施
- CSS はライト・ダーク両モード確認
- テスト用サーバーは必ず 5100 番以上のポートを使う
- 一時ファイルは `tmp/` 以下に配置し、作業完了後に削除

---

*このドキュメントは `docs/ja/SPEC.md` に格納されています。内容が古くなった場合はコードと git log を参照してください。*

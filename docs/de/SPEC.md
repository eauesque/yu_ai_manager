# Yu AI Manager — Gesamtspezifikation

> **Zielgruppe**: Claude Desktop usw.の AI エージェント  
> **Version**: v4.91.15  
> **aktualisieren**: 2026-04-19

---

## Inhaltsverzeichnis

1. [Projektübersicht](#1-Projektübersicht)
2. [Technischer Stack](#2-Technischer Stack)
3. [Architekturübersicht](#3-Architekturübersicht)
4. [Authentifizierung und Sicherheit](#4-認証セキュリティ)
5. [REST-API-Endpunkte](#5-rest-api-Endpunkt)
6. [MCP-Server](#6-mcp-Server)
7. [SSE-Ereignisse](#7-sse-Ereignis)
8. [DB-Schema](#8-db-スSchlüsselマ)
9. [Erweiterungen (Extensions)](#9-拡張extensions)
10. [Konfiguration (config.json)](#10-設定configjson)
11. [Dateistruktur](#11-Dateistruktur)
12. [Entwicklungsrichtlinien](#12-Entwicklungsrichtlinien)

---

## 1. Projektübersicht

**Yu AI Manager** は、AI 生成画像・動画・音声・テキストのローカルライブラリ管理System。  
エッジファースト・クラウド非依存を設計思想とし、ローカル/LAN で完結することを優先する。

### 主要機能

| 機能 | Beschreibung |
|------|------|
| ライブラリ管理 | 画像/動画/音声/テキストのScan・Tag付け・Suche |
| メタデータ抽出 | A1111 / ComfyUI / NovelAI 生成パラメータのautomatisch抽出 |
| AI Analyse | Claude / OpenAI / Ollama / Hailo VLM durch画像解析 |
| セマンティックSuche | CLIP (ONNX/CoreML) + Hailo durch意味Suche |
| Bridge 連携 | Stable Diffusion / ComfyUI / NovelAI für生成依頼 |
| LLM Router | Ollama / OpenAI 互換Backendfür統合ルーティング |
| Agent Safety | Kill Switch / Circuit Breaker / Approval Gate 等のSicherheit機構 |
| LAN 協業 | mDNS durchautomatischerkannt + Peer間共有 |
| MCP-Server | Claude Desktop 等von直接操作可能な 180+ ツール |

---

## 2. Technischer Stack

| レイヤー | 技術 |
|---------|------|
| Backend | Python 3.11+ / Quart (async) / Hypercorn |
| Database | SQLite3 (FTS5 全文Suche + zstd 圧縮 BLOB) |
| Frontend | TypeScript + Vite ビルド |
| Desktop | Tauri (Rust) |
| MCP | FastMCP (Anthropic MCP Server) |
| LLM | Claude API / OpenAI API / Ollama / Hailo VLM |
| Inference | ONNX Runtime / CoreML / Hailo Runtime |
| パッケージ管理 | Python: `uv pip` / Node.js: `pnpm` |

### ポート規約

- `5000–5099`: 本番アプリ予約帯域（変更禁止）
- `5100+`: Test・デバッグ用（`scripts/find_port.py` で空きポートautomatischabrufen）

---

## 3. Architekturübersicht

```
┌──────────────────────────────────────────────────┐
│  クライアント層                                    │
│  ├─ Web UI (TypeScript / Tauri)                  │
│  ├─ Claude Desktop (MCP)                         │
│  └─ 外部ツール (API Key / LAN Peer)               │
├──────────────────────────────────────────────────┤
│  認証層 (auth_chain.py)                           │
│  ├─ PIN / QuickLock (ボスロック)                  │
│  ├─ API Key (Bearer / Scope)                   │
│  └─ LAN Peer信頼 (mDNS 検証)                      │
├──────────────────────────────────────────────────┤
│  API 層                                           │
│  ├─ REST API (235+ Endpunkt / Quart Blueprint)│
│  ├─ SSE Stream (/api/events/stream)           │
│  └─ MCP-Server (180+ ツール)                    │
├──────────────────────────────────────────────────┤
│  サービス層                                        │
│  ├─ TagDB (SQLite / スSchlüsselマ v53)                 │
│  ├─ Event Bus (SSE ブロードキャスター)             │
│  ├─ LLM Router (複数Backend統合)              │
│  ├─ Analysis Engine (Claude/OpenAI/Ollama/Hailo) │
│  ├─ Extensions (47 builtin)                      │
│  └─ File Services (Scan/サーブ/サムネイル)    │
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

## 4. Authentifizierung und Sicherheit

### 認証Kette (core/web/auth_chain.py)

リクエストごとに以下の順序でAuswertung:

1. **静的DateiUmgehung** — `/static/`, `/favicon.ico`, `/help/*`
2. **MCP Umgehung** — `/mcp` (MCP 自体の認証)
3. **LLM Router Umgehung** — `/v1/` (ループバック時のみ)
4. **LAN Share Umgehung** — `/s/<token>` (共有トークン)
5. **LAN Peer信頼** — mDNS 検証済みPeerは PIN 不要
6. **API Schlüssel認証** — `Authorization: Bearer <key>` (Scope検証)
7. **QuickLock チェック** — ロック時は `/api/lock/unlock` のみ許可
8. **PIN チェック** — ブラウザSitzung認証

### API Schlüssel Scope

| Scope | 権限 |
|---------|------|
| `read` | 読み取り全般 |
| `write` | Datei・設定の書き込み |
| `tag.write` | Taghinzufügen・Löschen |
| `collection.write` | Sammlung管理 |
| `annotate` | アノテーション |
| `scan` | Scan操作 |
| `admin` | 管理者（全操作） |

### QuickLock / Boss Mode

- PIN は PBKDF2-SHA256 (600k iterations) でハッシュ化
- レート制限: 最大 5 回失敗で 60 秒ロックアウト
- `/api/lock/status` でロックStatusprüfen（認証不要）
- `/api/lock/unlock` で解除（PIN 必須）

### Geheimnis管理

- 1Password 統合 (`op://vault/item/field` 参照形式)
- Bitwarden 統合
- 設定値は Fernet 対称Verschlüsselung (`enc:...` プレフィックス)

---

## 5. REST-API-Endpunkte

Basis URL: `http://localhost:5000`（デフォルト）

### Agent Safety

| Methode | Pfad | Beschreibung |
|---------|------|------|
| GET | `/api/agent/status` | Kill Switch + CB + Budget 統合Status |
| POST | `/api/agent/kill` | Kill Switch aktivieren化 |
| POST | `/api/agent/resume` | Kill Switch deaktivieren化 |
| GET | `/api/agent/circuit-breaker` | Circuit Breaker Status |
| POST | `/api/agent/circuit-breaker/reset` | CB zurücksetzen |
| GET | `/api/agent/budget` | 予算残量 |
| POST | `/api/agent/budget/reset` | 予算zurücksetzen |
| GET | `/api/agent/journal` | アクションJournalSuche |
| GET | `/api/agent/journal/stats` | JournalStatistiken |
| GET | `/api/agent/approval` | Genehmigung待ちリクエストListe |
| POST | `/api/agent/approval/<request_id>` | Genehmigung/Ablehnung |
| GET | `/api/agent/approval/history` | GenehmigungVerlauf |
| POST | `/api/agent/undo/<int:journal_id>` | Undoausführen |
| GET | `/api/agent/undoable` | Undo可能Journal |
| GET | `/api/agent/anomaly` | AnomalieErkennungアラート |
| GET | `/api/agent/audit` | AuditLog |
| GET | `/api/agent/scope` | ScopeListe |
| GET | `/api/agent/scope/<session_id>` | SitzungScope |
| POST | `/api/agent/scope/<session_id>` | Scopeaktualisieren |
| DELETE | `/api/agent/scope/<session_id>` | ScopeLöschen |
| GET | `/api/agent/auto-approve` | AutoGenehmigungルール |
| POST | `/api/agent/auto-approve` | ルールhinzufügen |
| DELETE | `/api/agent/auto-approve/<int:index>` | ルールLöschen |
| GET | `/api/agent/tool-levels` | ツールSicherheitStufe |

### AI Analyse

| Methode | Pfad | Beschreibung |
|---------|------|------|
| GET | `/api/analysis/config` | 設定abrufen |
| POST | `/api/analysis/config` | 設定aktualisieren |
| GET | `/api/analysis/available-engines` | 利用可能EngineListe |
| GET | `/api/analysis/ollama/models` | Ollama ModellListe |
| POST | `/api/analysis/ollama/test` | VerbindungTest |
| POST | `/api/analysis/analyze/<int:file_id>` | DateiAnalyse |
| GET | `/api/analysis/result/<int:file_id>` | AnalyseErgebnis |
| POST | `/api/analysis/batch` | BatchAnalyse |
| POST | `/api/analysis/batch/cancel` | Batchabbrechen |
| GET | `/api/analysis/servers` | AnalyseServerListe |
| POST | `/api/analysis/servers` | Serverhinzufügen |
| PUT | `/api/analysis/servers/<server_id>` | Serveraktualisieren |
| DELETE | `/api/analysis/servers/<server_id>` | ServerLöschen |
| GET | `/api/analysis/servers/discovered` | automatischerkanntServer |
| POST | `/api/analysis/servers/discovered/register` | Registrierung |

### Datei・Scan

| Methode | Pfad | Beschreibung |
|---------|------|------|
| POST | `/api/scan/start` | Scan開始 |
| POST | `/api/scan/cancel` | abbrechen |
| POST | `/api/scan/resume` | 再開 |
| GET | `/api/scan/status` | Status |
| GET | `/api/scan/queue` | WarteschlangeListe |
| DELETE | `/api/scan/queue/<queue_id>` | WarteschlangeLöschen |
| POST | `/api/scan/queue/clear` | Warteschlangeleeren |
| GET | `/api/scan/history` | ScanVerlauf |
| GET | `/api/scan-errors` | ScanFehler |
| POST | `/api/scan-errors/<int:error_id>/resolve` | Fehlerauflösen |
| GET | `/api/scanned-roots` | Scan済みWurzel |
| POST | `/api/scanned-roots/purge` | WurzelLöschen |

### Tag・Favoriten・Bewertung

| Methode | Pfad | Beschreibung |
|---------|------|------|
| POST | `/api/tags/add` | Taghinzufügen |
| POST | `/api/tags/remove` | TagLöschen |
| GET | `/api/tags/list` | TagListe |
| POST | `/api/favorites/toggle` | Favoritenumschalten |
| GET | `/api/favorites/check` | Favoritenprüfen |
| GET | `/api/favorites/list` | FavoritenListe |
| GET | `/api/ratings/get` | Bewertungabrufen |
| POST | `/api/ratings/set` | Bewertung設定 |
| POST | `/api/ratings/batch-set` | Batch設定 |
| GET | `/api/ratings/stats` | Statistiken |

### Sammlung

| Methode | Pfad | Beschreibung |
|---------|------|------|
| GET | `/api/collections` | SammlungListe |
| POST | `/api/collections` | Erstellen |
| PUT | `/api/collections/<int:collection_id>` | aktualisieren |
| DELETE | `/api/collections/<int:collection_id>` | Löschen |
| POST | `/api/collections/reorder` | 並べ替え |
| POST | `/api/collections/<int:collection_id>/batch-add` | Batchhinzufügen |
| POST | `/api/collections/<int:collection_id>/batch-remove` | BatchLöschen |
| GET | `/api/collections/<int:collection_id>/export/csv` | CSV エクスポート |

### LLM Router

| Methode | Pfad | Beschreibung |
|---------|------|------|
| GET | `/api/llm_router/status` | Status |
| POST | `/api/llm_router/refresh` | Aktualisieren |
| POST | `/api/llm_router/backends/<alias>/enable` | Backendaktivieren化 |
| POST | `/api/llm_router/backends/<alias>/disable` | Backenddeaktivieren化 |
| POST | `/v1/chat/completions` | OpenAI 互換Chat |
| GET | `/v1/models` | ModellListe |

### System・ServerInformation

| Methode | Pfad | Beschreibung |
|---------|------|------|
| GET | `/api/system/inference-info` | InferenzEngineInformation |
| GET | `/api/mdns/identity` | mDNS Identität |
| GET | `/api/mdns/peers` | LAN PeerListe |
| GET | `/api/logs/recent` | AktuellのLog |
| GET | `/api/logs/stream` | Log SSE Stream |
| GET | `/api/jobs/status` | JobStatus |
| GET | `/api/events/stream` | SSE-EreignisseStream |
| GET | `/api/events/info` | SSE VerbindungInformation |

### 設定・Geheimnis

| Methode | Pfad | Beschreibung |
|---------|------|------|
| GET/POST | `/api/settings/llm-endpoints` | LLM Endpunkt管理 |
| GET/POST | `/api/settings/secrets/*` | Geheimnis管理 |
| GET | `/api/settings/bw-status` | Bitwarden Status |
| GET | `/api/settings/op-status` | 1Password Status |

### Hilfe

| Methode | Pfad | Beschreibung |
|---------|------|------|
| GET | `/api/help/toc` | Inhaltsverzeichnis |
| GET | `/api/help/content/<section>` | コンテンツ |
| GET | `/api/help/search` | Suche |

---

## 6. MCP-Server

### Verbindung

```
Transport: stdio または SSE
Endpunkt: /mcp (SSE モード時)
```

### ツール グループ (180+ ツール)

| グループ | Registrierung関数 | 主なツール |
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

全 MCP ツール呼び出しは以下をautomatischチェック:
1. Kill Switch — aktivieren時は全ツールausführen拒否
2. Circuit Breaker — 連続Fehler時にautomatisch遮断
3. Budget Tracker — 予算超過時に警告/停止
4. Approval Gate — `admin` Scope操作は人間Genehmigung待ち
5. Scope Fence — SitzungScope外アクセス拒否

---

## 7. SSE-Ereignisse

### Verbindung

```
GET /api/events/stream?types=<event1>,<event2>,...
Content-Type: text/event-stream
```

`types` 省略で全Ereignis受信。

### EreignisListe

**Scan**

| Ereignis | Beschreibung |
|---------|------|
| `scan.start` | Scan開始 |
| `scan.progress` | 進捗（processed/total） |
| `scan.complete` | 完了 |
| `scan.error` | Fehler |
| `scan.queued` | WarteschlangeRegistrierung |

**Datei操作**

| Ereignis | Beschreibung |
|---------|------|
| `favorite.add` / `favorite.remove` | Favoriten |
| `tag.add` / `tag.remove` | Tag |
| `rating.set` / `rating.clear` | Bewertung |
| `annotation.set` / `annotation.delete` | アノテーション |
| `collection.create` / `collection.delete` | Sammlung |

**生成**

| Ereignis | Beschreibung |
|---------|------|
| `generation.submit` | 生成依頼 |
| `generation.progress` | 進捗 |
| `generation.complete` | 完了 |
| `generation.error` | Fehler |
| `generation.cancel` | abbrechen |

**Analyse・Inferenz**

| Ereignis | Beschreibung |
|---------|------|
| `analysis.complete` | Analyse完了 |
| `batch_analysis.complete` | Batch完了 |
| `semantic_index.start/progress/complete` | Index |
| `yolo_detect.start/progress/complete` | 物体Erkennung |
| `wd_tagger.complete` | WD-Tagger 完了 |
| `ocr.complete` | OCR 完了 |

**Agent Safety**

| Ereignis | Beschreibung |
|---------|------|
| `agent.killed` | Kill Switch aktivieren |
| `agent.resumed` | 再開 |
| `agent.circuit_open` | Circuit Breaker 開放 |
| `agent.circuit_closed` | 閉鎖 |
| `agent.budget_warning` | 予算警告 |
| `agent.budget_exhausted` | 予算枯渇 |

**LAN 協業**

| Ereignis | Beschreibung |
|---------|------|
| `peer.discovered` | Peererkannt |
| `peer.online` / `peer.offline` | Status変化 |
| `sync.file_changed` / `sync.file_received` | Datei同期 |
| `sync.conflict` | 競合 |

**その他**

| Ereignis | Beschreibung |
|---------|------|
| `scheduler.job_executed` | スケジューラJobausführen |
| `backup.complete` / `backup.error` | バックアップ |
| `config.scan_roots_changed` | ScanWurzel変更 |
| `watcher.started` / `watcher.stopped` | Datei監視 |
| `webhook.received` | Webhook 受信 |
| `github_queue.new_issues` | GitHub 新規 Issue |
| `bsky_queue.new_notifications` | Bluesky 新規通知 |
| `chatlog_reprocess.start/progress/complete` | ChatLog再処理 |
| `fpb.start/progress/complete/error` | Freeze & Pull-back |

---

## 8. DB-Schema

**DB Datei**: `tags.db`（トップディレクトリ、`--db` で指定可）  
**スSchlüsselマVersion**: 53  
**読み書き分離**: GET 系は `get_readonly_db()` 使用必須

### 主要Tabelle

```sql
-- Datei
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
  file_ext TEXT GENERATED ALWAYS AS     -- automatisch生成
    (lower(substr(path, instr(path,'.',-1)+1))) STORED
)

-- Tag辞書
tags (
  id INTEGER PRIMARY KEY,
  tag TEXT NOT NULL,
  namespace TEXT,                        -- "namespace:tag" 形式
  first_seen_mtime INTEGER,
  UNIQUE(tag, namespace)
)

-- Datei↔Tag関連
file_tags (
  file_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL,
  weight REAL DEFAULT 1.0,              -- Tag重みづけ
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

-- メタデータ抽出Status
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

-- Dateiキャッシュ（サムネイル等）
cache_entry (
  cache_key TEXT PRIMARY KEY,
  kind TEXT NOT NULL,                    -- 'thumbnail'|'preview'|'clip_emb'
  path TEXT NOT NULL,
  file_id INTEGER,
  size_bytes INTEGER DEFAULT 0,
  last_access_at INTEGER,
  updated_at INTEGER
)

-- Favoriten
favorites (
  file_id INTEGER NOT NULL,
  collection_id INTEGER DEFAULT 1,
  added_at INTEGER,
  PRIMARY KEY (file_id, collection_id)
)

-- スSchlüsselマVersion管理
schema_version (
  version INTEGER PRIMARY KEY,
  applied_at INTEGER,
  description TEXT
)

-- 拡張別スSchlüsselマVersion
extension_schema_versions (
  extension_name TEXT NOT NULL,
  version INTEGER NOT NULL,
  applied_at INTEGER,
  description TEXT,
  PRIMARY KEY (extension_name, version)
)

-- DB メタInformation
db_meta (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at INTEGER
)
```

### FTS5（全文Suche）

```sql
-- プロンプト全文Suche
templates_fts USING fts5 (
  content='templates',
  raw_prompt, raw_negative, model_name
)
```

注意: CJK 文字は FTS5 が非対応のため LIKE フォールバックを使用。

### 主要Index

```sql
idx_tags_tag_lower          -- Tag大文字小文字区別なし
idx_files_deleted_mtime     -- ソフトデリート + mtime
idx_files_deleted_source    -- ソフトデリート + ソース
idx_file_tags_tag_id        -- TagIDSuche
idx_file_tags_source        -- メタデータソース
idx_media_extract_cache_state -- キャッシュStatus
idx_media_extract_next_retry  -- リトライ待機
idx_files_hash              -- ハッシュ（重複Erkennung）
idx_files_deleted_ext       -- 拡張子フィルタ
```

---

## 9. Erweiterungen (Extensions)

### 構成

```
extensions/
  builtin-<name>/
    extension.json     # メタデータ
    <name>_ext.py      # エントリーポイント
    templates/         # HTML テンプレート
    static/            # 静的Datei
```

### extension.json フォーマット

```json
{
  "name": "builtin-analysis",
  "version": "1.0.0",
  "description": "AI 画像AnalyseEngine",
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

### ビルトイン拡張Liste（47 個）

| 拡張名 | カテゴリ | Beschreibung |
|--------|---------|------|
| builtin-a1111 | parser | A1111 メタデータ抽出 |
| builtin-analysis | ai | AI 画像Analyse（Claude/OpenAI/Ollama） |
| builtin-annotations | utility | アノテーション管理 |
| builtin-audio-analysis | ai | 音声Analyse（Whisper） |
| builtin-auto-scan-watcher | utility | Datei変更automatischScan |
| builtin-backup | utility | DB/設定バックアップ |
| builtin-chatlog | utility | ChatLog管理 |
| builtin-clip-coreml | ai | CLIP セマンティックSuche（macOS） |
| builtin-clip-onnx | ai | CLIP セマンティックSuche（クロスプラットフォーム） |
| builtin-clip-search | search | CLIP Suche UI |
| builtin-comfyui | parser | ComfyUI メタデータ抽出 |
| builtin-comfyui-bridge | bridge | ComfyUI API 連携 |
| builtin-cross-search | search | テキスト全文Suche |
| builtin-debug-check | utility | System診断 |
| builtin-download | utility | URL/磁力リンクダウンロード |
| builtin-export | utility | CSV/JSON/ZIP エクスポート |
| builtin-favorites-manager | utility | Favoriten・Sammlung |
| builtin-freeze-pullback | utility | Datei復元 |
| builtin-github-integration | integration | GitHub Issue/PR 管理 |
| builtin-hailo-genai | ai | Hailo 生成 AI |
| builtin-hailo-semantic-search | search | Hailo セマンティックSuche |
| builtin-hailo-yolo-detect | ai | Hailo YOLO 物体Erkennung |
| builtin-inference | ai | リモートInferenz管理 |
| builtin-lan-cowork | network | LAN 協業 |
| builtin-lan-share | network | LAN QR 共有 |
| builtin-lora-dataset-manager | utility | LoRA データsetzen（kohya-ss 連携） |
| builtin-mcp-client | integration | 外部 MCP-ServerVerbindung |
| builtin-md-viewer | utility | Markdown Datei表示 |
| builtin-nai-bridge | bridge | NovelAI API 連携 |
| builtin-novelai-v3 | parser | NovelAI v3 メタデータ |
| builtin-novelai-v4 | parser | NovelAI v4 メタデータ |
| builtin-ocr | ai | OCR テキスト抽出 |
| builtin-prompt-library | utility | プロンプト管理・Suche |
| builtin-prompt-simulator | utility | ワイルドカード展開 |
| builtin-prompt-syntax | utility | Lora/制御トークン解析 |
| builtin-ratings | utility | 5 段階Auswertung |
| builtin-sd-nai-convert | utility | SD ↔ NAI プロンプト変換 |
| builtin-sd-webui-bridge | bridge | SD WebUI API 連携 |
| builtin-sns-share | integration | SNS 投稿（Bluesky/Twitter） |
| builtin-speech-to-text | ai | 音声認識 |
| builtin-stats | utility | Statistikenダッシュボード |
| builtin-tag-dictionary | utility | Tag辞書・Beschreibung |
| builtin-trophy | utility | マイルストーン達成 |
| builtin-video-analysis | ai | 動画SchlüsselフレームAnalyse |
| builtin-wd-tagger | ai | WD-Tagger automatischTag生成 |
| builtin-webhook | integration | Webhook 送受信 |

---

## 10. Konfiguration (config.json)

**Pfad**: `{プロジェクトWurzel}/config.json`

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

| 変数 | Beschreibung |
|-----|------|
| `TAGDB_DATA_DIR` | データディレクトリ |
| `TAGDB_CACHE_DIR` | キャッシュディレクトリ |
| `TAGDB_LOG_DIR` | Logディレクトリ |
| `TAGDB_PROFILES_DIR` | プロフィールディレクトリ |
| `YU_DEBUG_MODE` | `1` でデバッグ API aktivieren |

---

## 11. Dateistruktur

```
O:/yu_ai_manager/
├── web_ui.py              # ASGI エントリーポイント
├── app.py                 # Quart アプリ初期化
├── config.json            # メイン設定
├── tags.db                # 開発用 DB（--db で指定）
├── VERSION                # Version番号
├── CHANGELOG.md           # 変更Verlauf
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
│   ├── agent_safety/      # Sicherheit機構
│   ├── analysis/          # AI AnalyseEngine
│   ├── event_bus/         # Ereignisバス
│   ├── extensions_core/   # 拡張ライフサイクル
│   ├── files_core/        # Dateiサーブ
│   ├── infra_core/        # API レスポンス等
│   ├── llm_router/        # LLM ルーティング
│   ├── scan_core/         # Scan
│   ├── schema_core/       # DB-Schema・マイグレーション
│   ├── services_core/     # DB 非同期アダプター
│   ├── settings_core/     # 設定管理
│   ├── sse/               # SSE ブロードキャスター
│   ├── tagdb_core/        # Tag DB コア
│   └── web/               # 認証・リクエスト処理
│
├── mcp_server/            # MCP-Server（180+ ツール）
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
│   │   ├── SPEC.md        # 本Datei
│   │   ├── features/
│   │   ├── api/
│   │   └── troubleshooting/
│   └── bugreport.html     # バグ報告リレーページ
│
└── scripts/
    ├── find_port.py       # 空きポートautomatischabrufen
    └── ...
```

---

## 12. Entwicklungsrichtlinien

### バージョニング

- `feat:` → minor Versionアップ
- `fix:` → patch Versionアップ
- 作業のたびに `VERSION` / `CHANGELOG.md` / `TODO.md` をaktualisieren

### コーディング

- Blueprint hinzufügen時は i18n 必須（`data-i18n` / `window.tr()`）
- HTML フォーム要素には `id` または `name` を付与
- `type="password"` は `<form>` で囲む
- インライン `onclick` 禁止（`data-action` デリゲーション使用）
- DB 読み書き分離: GET 系は必ず `get_readonly_db()` を使う

### Dateiサイズ制限

| 行数 | 対応 |
|-----|------|
| 300 | 分割検討 |
| 500 | 実用上限 |
| 800 | 即分割 |

### ライセンス禁止

GPL / LGPL / AGPL 系の新規依存hinzufügen禁止。

### ドキュメント

- 新規 API: MCP ツール同時実装 + `docs/{ja,en,zh-tw,zh-cn,ko}/api/` に全言語Erstellen
- 新機能: `docs/{ja,en,zh-tw,zh-cn,ko}/` に全言語Erstellen（スタブ禁止）
- 多言語ドキュメントは `ja/` が一次ソース、他言語は ja/ をBasisに生成

### Test

- WebUI/CSS 変更後は Playwright Test実施
- CSS はライト・ダーク両モードprüfen
- Test用Serverは必ず 5100 番以上のポートを使う
- 一時Dateiは `tmp/` 以下に配置し、作業完了後にLöschen

---

*このドキュメントは `docs/ja/SPEC.md` に格納されています。内容が古くなった場合はコードと git log を参照してください。*

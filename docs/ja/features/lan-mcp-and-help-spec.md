# LAN MCP アクセス & ヘルプエンドポイント仕様書

**実装バージョン**: 3.1.0
**関連ドキュメント**: `docs/ja/features/mcp-integration-guide.md`
**関連ファイル**: `routes/mcp_endpoint.py`, `routes/help.py`, `mcp_server/help_tools.py`

---

## 概要

1. **LAN MCP アクセス** — LAN 公開モード時に、LAN 内の MCP クライアントから IP アドレス指定で MCP エンドポイントへ接続できるようにする
2. **`/help` エンドポイント** — アプリ内蔵のウェブマニュアルを提供する（MCP リソースとしても公開）

---

## 1. LAN MCP アクセス

### 1-1. アーキテクチャ

LAN 経由の場合、MCP クライアントは HTTP/SSE トランスポートで YU AI Manager の `/mcp` エンドポイントに直接接続する。

### 1-2. MCP SSE エンドポイント

| 項目 | 内容 |
|------|------|
| エンドポイント | `/mcp` (SSE + メッセージ送信) |
| トランスポート | HTTP + Server-Sent Events (SSE) |
| 認証 | localhost からは不要。LAN IP からは API キー必須 |

### 1-3. API キー認証

既存の API キー管理機構（`/api/keys`）を流用する。

### 1-4. Settings UI

Settings > API Keys タブに LAN MCP 接続設定スニペット（HTTP 版）を追加。

---

## 2. `/help` エンドポイント

### 2-1. 設計方針

- オフライン完結
- MCP リソース兼用
- 認証不要

### 2-2. エンドポイント

| エンドポイント | 内容 |
|----------------|------|
| `GET /help` | マニュアルトップページ |
| `GET /help/<section>` | セクション別ページ |
| `GET /api/help/toc` | 目次 JSON |
| `GET /api/help/content/<section>` | セクション本文 JSON |

### 2-3. MCP ツール

- `help_search`: キーワード検索
- `help_get_section`: セクション取得

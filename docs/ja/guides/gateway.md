# Gateway — LAN 認証境界ガイド

> 対象バージョン: Gateway Phase 1 (v4.75.0 以降) / Gradio 追加 (v4.255.11 以降) / headroom プロキシ追加 (v4.258.0 以降) / headroom 2 層認証 (v4.259.0 以降)

## Gateway とは

Gateway は、SD WebUI・ComfyUI・Ollama・Gradio アプリなどの**認証機能を持たないバックエンドツール**へのアクセスを、  
**Bearer トークン + スコープモデル**で一元保護するリバースプロキシです。

```
外部クライアント / LAN の別マシン
    │
    │  Authorization: Bearer <api_key>
    ▼
 yu_ai_manager  (/v1/*, /sd/*, /comfy/*, /gradio/<name>/*)
 ┌────────────────────────────────────────────────────────┐
 │                      Gateway                          │
 │          scope チェック ──► バックエンド選択           │
 └────────────────────────────────────────────────────────┘
    │          │            │            │
    ▼          ▼            ▼            ▼
 Ollama    SD WebUI     ComfyUI      Gradio
 :11434     :7860         :8188        :7861
```

### LLM Router との違い

| | Gateway | LLM Router |
|---|---|---|
| **対象** | SD WebUI・ComfyUI・Ollama・Gradio をまとめて | LLM (Ollama) のみ |
| **認証** | scope ベースの Bearer 必須 | loopback は bypass 可 |
| **プロキシ先** | `/sd/*`, `/comfy/*`, `/v1/*`, `/gradio/<name>/*` | `/v1/*` のみ |
| **主な用途** | 外部 / LAN に生成ツールを安全公開 | AI コーディングツールのバックエンド |

同一マシンで両方を有効にすることもできます。

---

## セットアップ

### 1. 初回 API キーの作成（CLI）

```bash
uv run python -m core.gateway.cli create-key --id admin-local --scopes "*"
```

出力例:
```
id:      admin-local
secret:  gw_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
(このシークレットは一度だけ表示されます。必ずコピーしてください)
```

### 2. config.json に設定を追加

```json
{
  "gateway": {
    "auth": {
      "mode": "api_key",
      "allow_loopback_bypass": true,
      "api_keys": [
        {
          "id": "admin-local",
          "secret_enc": "enc:v2:...",
          "scopes": ["*"],
          "allowed_models": null
        }
      ]
    },
    "backends": {
      "ollama":       {"type": "ollama",   "base_url": "http://127.0.0.1:11434"},
      "sd_webui":     {"type": "sd_webui", "base_url": "http://127.0.0.1:7860"},
      "comfyui":      {"type": "comfyui",  "base_url": "http://127.0.0.1:8188", "ws_url": "ws://127.0.0.1:8188/ws"},
      "irodori-tts":  {"type": "gradio",   "base_url": "http://127.0.0.1:7861"}
    },
    "health_probe": {"enabled": true, "interval_seconds": 10}
  }
}
```

> `secret_enc` フィールドには CLI が出力した `enc:v2:...` 形式の暗号化済み値を使います。  
> 平文シークレットは `config.json` に直接書かないでください。

### 3. アプリを再起動して動作確認

```bash
GW_HOST=<このマシンの LAN IP>
GW_PORT=5000
BEARER=<api-key-secret>

# 認証なしは 401
curl -i http://$GW_HOST:$GW_PORT/v1/models

# 正しい Bearer で 200
curl http://$GW_HOST:$GW_PORT/v1/models \
  -H "Authorization: Bearer $BEARER"

# バックエンドの稼働状況
curl http://$GW_HOST:$GW_PORT/v1/router/capabilities \
  -H "Authorization: Bearer $BEARER"

# ノードサービス一覧
curl http://$GW_HOST:$GW_PORT/v1/node/services \
  -H "Authorization: Bearer $BEARER"
```

---

## WebUI（/gateway ページ）

`/gateway` で開く管理ダッシュボード。

### バックエンド一覧

登録済みバックエンドの稼働状態を一覧表示します。

| 列 | 説明 |
|---|---|
| **タイプ** | バックエンドの種類（`ollama`, `sd_webui`, `comfyui`, `gradio`）|
| **ポート** | プロキシ先のポート番号 |
| **状態** | `online` / `offline` / `unknown` |
| **操作** | Probe（疎通確認）・設定変更 |

### バックエンドの自動スキャン

「スキャン」ボタンを押すと、ローカルの一般的なポート（7860, 8188, 11434, 7861 等）を  
スキャンして稼働中のツールを自動検出・登録提案します。

### API キー管理

WebUI からも API キーの追加・失効が可能です（`*` スコープを持つキーが必要）。

---

## スコープ一覧

| スコープ | 許可されるエンドポイント |
|---|---|
| `llm:chat` | `POST /v1/chat/completions` |
| `llm:messages` | `POST /v1/messages`（Anthropic 互換）|
| `llm:models` | `GET /v1/models` |
| `sd:generate` | `POST /sd/sdapi/v1/txt2img` 等 |
| `sd:query` | `GET /sd/sdapi/v1/samplers` 等 |
| `sd:admin` | `POST /sd/sdapi/v1/options` 等 |
| `comfy:generate` | `POST /comfy/api/prompt` 等 |
| `comfy:query` | `GET /comfy/api/queue` 等 |
| `memory:read` | `GET /agentmemory/memories` 等（読み取り）|
| `memory:write` | `POST /agentmemory/observe` 等（書き込み）|
| `memory:admin` | `POST /agentmemory/migrate` 等（管理）|
| `ollama:proxy` | `GET/POST /ollama/<name>/*`（Ollama ネイティブ API + OpenAI 互換 全透過）|
| `gradio:proxy` | `GET/POST /gradio/<name>/*`（全エンドポイント透過）|
| `headroom:read` | `GET/POST /headroom/*`（headroom LLM プロキシ 読み取り・推論）|
| `headroom:admin` | headroom バックエンド設定変更 |
| `gateway:admin` | API キー管理・設定変更（loopback から自動付与）|
| `node:status` | `GET /v1/node/services` |
| `*` | 全スコープ（管理者用）|

### 用途別キーの例

```json
"api_keys": [
  {
    "id": "claude-code",
    "secret_enc": "enc:v2:...",
    "scopes": ["llm:chat", "llm:messages", "llm:models"],
    "allowed_models": null
  },
  {
    "id": "comfy-client",
    "secret_enc": "enc:v2:...",
    "scopes": ["comfy:generate", "comfy:query"],
    "allowed_models": null
  }
]
```

---

## Ollama プロキシ

LLM Router の `/v1/*` とは別に、Ollama ネイティブ API（`/api/*`）および OpenAI 互換 API（`/v1/*`）を  
そのまま透過転送するプロキシです。`OLLAMA_HOST` の向き先を Gateway に変えるだけで認証が付きます。

### プロキシ URL

```
/ollama/<backend_name>/<subpath>  →  登録済み base_url の /<subpath> に転送
```

### 設定例

```json
"backends": {
  "ollama": {"type": "ollama", "base_url": "http://127.0.0.1:11434"}
}
```

### クライアント設定（`OLLAMA_HOST` 方式）

```bash
export OLLAMA_HOST=http://<gateway-host>:5000/ollama/ollama
# 以降の ollama コマンドはすべて Gateway 経由になる
ollama list
ollama run llama3.3:70b
```

> `OLLAMA_HOST` に Bearer を渡せないクライアントは `allow_loopback_bypass: true` +  
> loopback 経由でキーなし通過させるか、`*` スコープキーで代替してください。

### 大容量ファイル転送

モデル blob（`/api/blobs/*`）はストリーミング転送するためタイムアウトなし（他のパスは 300 秒）。  
GB 単位のモデルプル・プッシュも問題なく動作します。

---

## Gradio プロキシ

Gradio ベースの WebUI（Irodori-TTS 等）を Gateway 経由で認証付きアクセス可能にします。  
全エンドポイントを透過転送する最小実装です（エンドポイント制限なし・50 MiB ボディ上限のみ）。

### プロキシ URL

```
/gradio/<backend_name>/<subpath>  →  登録済み base_url の /<subpath> に転送
```

バックエンド名（`<backend_name>`）は `config.json` の `backends` に登録したキー名です。

### 設定例

```json
"backends": {
  "irodori-tts": {"type": "gradio", "base_url": "http://127.0.0.1:7861"}
}
```

### 動作確認

```bash
GW=http://localhost:5000
KEY=<api-key-secret>

# Gradio アプリの情報取得
curl -H "Authorization: Bearer $KEY" "$GW/gradio/irodori-tts/"

# Gradio 3.x 互換 predict
curl -H "Authorization: Bearer $KEY" \
  -X POST "$GW/gradio/irodori-tts/run/predict" \
  -H "Content-Type: application/json" \
  -d '{"data": ["Hello"], "fn_index": 0}'
```

### 制限事項

- WebSocket（`/queue/join`）は非対応（HTTP のみ）
- Gradio 4.x の SSE ストリーム（`GET /call/{api_name}/{event_id}`）は全バッファ転送のため、  
  長時間生成ではタイムアウトの恐れがあります

---

## Agent Memory（agentmemory）プロキシ

Gateway は `@agentmemory/mcp` など agentmemory クライアントを  
LAN 越しに安全に利用するためのプロキシも提供します。

### エンドポイント

```
/agentmemory/livez       → 認証不要（ヘルスチェック）
/agentmemory/health      → memory:read スコープ必要
/agentmemory/memories    → memory:read
/agentmemory/observe     → memory:write
/agentmemory/migrate     → memory:admin
...（以降、完全一覧は agentmemory 公式 API を参照）
```

### 同一マシンで使う場合

`allow_loopback_bypass: true` のとき、loopback (127.0.0.1) からは  
API キー不要でそのまま通過します。MCP 設定の変更は**不要**です。

### LAN の別マシンから使う場合

`@agentmemory/mcp` は環境変数 `AGENTMEMORY_SECRET` を  
`Authorization: Bearer <secret>` として upstream に送ります。

**Claude Code / Claude Desktop（`claude_desktop_config.json` / `.mcp.json`）の変更例：**

```json
{
  "agentmemory": {
    "command": "npx",
    "args": ["-y", "@agentmemory/mcp"],
    "env": {
      "AGENTMEMORY_URL": "http://<gateway-host>:5000/agentmemory",
      "AGENTMEMORY_SECRET": "<api-key-secret>"
    }
  }
}
```

**Codex（`~/.codex/config.toml`）の変更例：**

```toml
[mcp_servers.agentmemory]
command = "npx"
args = ["-y", "@agentmemory/mcp"]

[mcp_servers.agentmemory.env]
AGENTMEMORY_URL = "http://<gateway-host>:5000/agentmemory"
AGENTMEMORY_SECRET = "<api-key-secret>"
```

必要なスコープ（API キー作成時に指定）:

```json
"scopes": ["memory:read", "memory:write"]
```

管理操作（`/migrate`・`/governance/*` 等）も必要な場合は `memory:admin` を追加。

### 接続先 URL の変更（v4.257.7+）

agentmemory サーバーのポートやホストが変わった場合は、  
**Gateway 設定ページ**（`/gateway`）→「バックエンド設定」から変更できます（再起動不要）。  
`config.json` を直接編集する場合は `backends.agentmemory.base_url` を修正してください。

### 動作確認

```bash
GW=http://<gateway-host>:5000
KEY=<api-key-secret>

# 認証不要（livez）
curl $GW/agentmemory/livez

# Bearer で memories 取得
curl -H "Authorization: Bearer $KEY" "$GW/agentmemory/memories?limit=3"

# Basic 認証でも動作（SD クライアント互換）
curl -u "user:$KEY" "$GW/agentmemory/health"
```

---

## headroom（LLM コンテキスト圧縮）プロキシ

Gateway は headroom の全エンドポイントを `/headroom/*` でプロキシします。
`ANTHROPIC_BASE_URL` を Gateway に向けることで、Claude Code 等の Anthropic SDK クライアントが
**LAN 越しに headroom を経由して Claude API へアクセス**できます。

### ヘッダー分離（2 層認証・v4.259.0 以降）

headroom は `/v1/*` で**クライアントの `Authorization` Bearer をそのまま upstream（Anthropic 等）へ
転送するパススルー型**です。max plan ではホストごとに OAuth トークンが異なり固定の upstream キーを
持てないため、認証を 2 層に分離します。

| ヘッダー | 役割 |
|---|---|
| `Proxy-Authorization: Bearer <gateway-key>` | Gateway 認証（プロキシで**消費**・headroom へ渡さない） |
| `Authorization: Bearer <OAuth / api-key>` | upstream 認証（各ホスト自身の資格情報・headroom へ**透過**） |

- Gateway は upstream 資格情報を**保持しません**。各ホストが自分の `Authorization`（OAuth 等）を持ち込みます。
- 2 つのヘッダーは名前が異なるため同一リクエストに共存できます。
- `/headroom/*` は API 専用パスのため `Proxy-Authorization` は**必須**です（無い場合は Gateway が 401）。

> **以前の設定からの移行**: 旧版は gateway キーを `Authorization`（または `ANTHROPIC_DEFAULT_HEADERS`）に
> 載せていましたが、現在は `Proxy-Authorization` に移りました。`Authorization` はクライアント自身の
> upstream 認証専用です。

### gateway 経由の設定（custom header 対応クライアント）

`Proxy-Authorization` を送れるのは custom header に対応したクライアントのみです（**Claude Code・Codex**）。

#### A. Claude Code（Anthropic 形式・ルートパス `/headroom`）

`ANTHROPIC_CUSTOM_HEADERS` は `Name: Value` 形式の文字列です（複数ヘッダーは改行 `\n` 区切り）。
**JSON 形式は不可**（`Invalid header name` エラーになります）。`ANTHROPIC_DEFAULT_HEADERS` は存在しません。

**Windows PowerShell の場合**（永続化は `$PROFILE` に追記）:

```powershell
$env:ANTHROPIC_BASE_URL = "http://<gateway-host>:5000/headroom"
$env:ANTHROPIC_CUSTOM_HEADERS = "Proxy-Authorization: Bearer <gateway-headroom:read-key>"
claude
```

**Linux / macOS の場合**:

```bash
export ANTHROPIC_BASE_URL="http://<gateway-host>:5000/headroom"
export ANTHROPIC_CUSTOM_HEADERS="Proxy-Authorization: Bearer <gateway-headroom:read-key>"
claude
```

**`~/.claude/settings.json` で固定する場合**:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://<gateway-host>:5000/headroom",
    "ANTHROPIC_CUSTOM_HEADERS": "Proxy-Authorization: Bearer <gateway-headroom:read-key>"
  }
}
```

> upstream 認証（`Authorization`）は Claude Code が自身の資格情報を自動付与します（max plan の OAuth 等）。
> 固定キー運用なら `ANTHROPIC_AUTH_TOKEN`（→ `Authorization: Bearer`）または `ANTHROPIC_API_KEY`（→ `x-api-key`）を併用。

#### B. Codex（OpenAI 形式・`/headroom/v1`）

OpenAI 互換クライアントは base URL に `/v1` を含めます。Codex は `~/.codex/config.toml` の
`http_headers` で `Proxy-Authorization` を付加できます。

```toml
# ~/.codex/config.toml
model = "<model>"
model_provider = "yu_headroom"

[model_providers.yu_headroom]
name = "yu gateway headroom"
base_url = "http://<gateway-host>:5000/headroom/v1"
env_key = "OPENAI_API_KEY"        # upstream 認証 → Authorization: Bearer として透過
wire_api = "responses"             # /v1/responses エンドポイントを使用
requires_openai_auth = false       # 第三者ゲートウェイ（sk- 前提を解除）
http_headers = { "Proxy-Authorization" = "Bearer <gateway-headroom:read-key>" }
```

> Codex を Plus/Pro/max plan の OAuth 認証で使う場合は、`env_key = "OPENAI_API_KEY"` 行を削除してください。
> `env_key` を残すと Codex が `OPENAI_API_KEY` 環境変数を要求し、OAuth の資格情報を使えず通信できません。
> API key 運用の場合だけ `env_key` を指定します。

### gateway 経由が使えないクライアント

**Cursor / Aider** は custom request header の追加に対応していません（base URL と API キーのみ）。
`Proxy-Authorization` を送れず Gateway 認証を通せないため、**gateway 経由では利用できません**。
これらは下記の headroom wrap（ローカル起動）を使ってください。

### headroom wrap（ローカル起動・gateway を経由しない）

各自のマシンで headroom を直接起動してクライアントをラップする方式です（Gateway 共有とは別経路）。

```bash
headroom wrap claude     # Claude Code
headroom wrap codex      # Codex
headroom wrap cursor     # Cursor（config を出力。一度貼り付け）
headroom wrap aider      # Aider
```

詳細は headroom 本家 <https://github.com/chopratejas/headroom> を参照。

### PIN 認証（LAN 公開時）

`/headroom/*` は API 専用パスのため、ブラウザ PIN セッションの有無に関わらず
`Proxy-Authorization: Bearer <gateway-key>` が**必須**です（PIN フォールバックは行いません）。

### 必要なスコープ

```json
"scopes": ["headroom:read"]
```

headroom のバックエンド設定（接続先 URL 変更等）も必要な場合は `headroom:admin` を追加。

### 動作確認

```bash
GW=http://<gateway-host>:5000
KEY=<gateway-headroom-key>
OAUTH=<your-oauth-or-api-key>

# ① Gateway 認証のみを切り分け確認（OAuth 無し）
#    → Gateway は通過し、headroom が "Missing bearer authentication in header" を返せば素通し成功
curl -H "Proxy-Authorization: Bearer $KEY" "$GW/headroom/v1/models"

# ② OAuth も載せて疎通（完全形）
curl -X POST \
     -H "Proxy-Authorization: Bearer $KEY" \
     -H "Authorization: Bearer $OAUTH" \
     -H "Content-Type: application/json" \
     -d '{"model":"claude-sonnet-4-6","max_tokens":64,"messages":[{"role":"user","content":"ping"}]}' \
     "$GW/headroom/v1/messages"
```

---

## 認証モード

| モード | 動作 |
|---|---|
| `api_key` | Bearer トークンが必須（`allow_loopback_bypass: true` で loopback のみ免除）|
| `loopback` | loopback (127.0.0.1) からは認証不要。LAN からは `api_key` と同等 |
| `none` | 認証なし（開発・テスト専用。本番不可）|

`allow_loopback_bypass: true` にすることで、同一マシン上のツール（Claude Code CLI 等）は  
API キーなしで Gateway を通過できます。

---

## Health Probe

`health_probe.enabled: true` のとき、設定した間隔でバックエンドへ自動疎通確認を実施します。

```json
"health_probe": {
  "enabled": true,
  "interval_seconds": 10
}
```

オフラインのバックエンドは `/v1/router/capabilities` の `backends` フィールドで  
`"status": "offline"` と報告されます。

---

## よくある詰まり

| 症状 | 原因 / 対処 |
|---|---|
| 全リクエストが 401 | `allow_loopback_bypass` が `false` で loopback からもキーが必要。または Bearer 値が誤っている |
| SD WebUI へのプロキシが 404 | `sd_webui.base_url` のポートが正しくない（デフォルト 7860）。`/gateway` で Probe を実行 |
| ComfyUI WebSocket が繋がらない | `ws_url` を設定しているか確認（`ws://127.0.0.1:8188/ws`）|
| Gradio プロキシが 404 | `backend_name` が `config.json` の backends キー名と一致しているか確認。`type: "gradio"` の指定も必要 |
| Gradio の SSE ストリームがタイムアウト | 長尺生成（動画等）では全バッファ方式の制限あり。短時間推論（TTS 等）は問題なし |
| スコープ不足で 403 | 使用しているキーのスコープが足りない。`*` スコープのキーで API キー管理から追加 |
| `allowed_models` で特定モデルだけ使わせたい | `"allowed_models": ["qwen2.5:7b", "llama3.3:70b"]` のように配列で指定 |
| headroom プロキシで SSE が途中で止まる | headroom の起動確認（`curl http://127.0.0.1:8787/livez`）。タイムアウトは 300 秒で十分長いはず |
| headroom 経由で 502 / "connection_error" | headroom が 127.0.0.1:8787 で起動していない。Gateway の headroom バックエンド URL を確認 |
| `Invalid header name: '{"...'` | `ANTHROPIC_CUSTOM_HEADERS` を JSON で書いている。`Name: Value` 形式が正しい（例 `Proxy-Authorization: Bearer <key>`、複数は改行 `\n` 区切り）。`ANTHROPIC_DEFAULT_HEADERS` は存在しない変数 |
| headroom が `Unauthorized`(Gateway 401) | gateway キーを `Authorization` に載せている。v4.259.0 以降は `Proxy-Authorization` に載せる（`Authorization` はクライアント自身の upstream 認証用） |
| headroom が `Missing bearer authentication` | Gateway 認証は通過済み。upstream 認証（`Authorization`）が無い。Claude Code は自動付与、Codex は `env_key` を設定 |
| Cursor / Aider が gateway 経由で繋がらない | custom header 非対応で `Proxy-Authorization` を送れない。`headroom wrap` でローカル起動する |

---

## Non-Goals（Phase 1 の対象外）

- バックエンドの start/stop/restart（SSH + systemctl で実施）
- `/v1/responses`（Codex 互換 façade）— Phase 2 以降
- 複数 Gateway インスタンスの負荷分散 — LAN Cowork の分散推論を利用

---

## 関連ドキュメント

- [Gateway API リファレンス](../api/gateway.md) — `/api/gateway/*` エンドポイント詳細
- [LLM Router セットアップ](../llm-router/setup.md) — LLM 専用の軽量プロキシ
- [LAN Cowork 概要](../lan-cowork/README.md) — 複数ノードの連携

## WebUI での APIキー管理

設定ページの **「Gateway APIキー」** タブから、APIキーの作成・一覧・削除が可能です。
[Gateway ページ](/gateway) にもリンクがあります。

### APIキーの作成

1. **ラベル** を入力（例: `Claude Desktop`）— IDは自動でslug化（例: `claude-desktop`）
2. **スコープ**をバッジで選択（1つ以上必須）
3. `*`（全許可）選択時は確認チェックボックスにチェック
4. 「作成」ボタンをクリック
5. 表示されたシークレットをコピー — **この画面を離れると二度と表示されません**

### 注意事項

- `*` スコープを持つ最後のキーは削除できません（Bearer経路 lockout防止）
- 先に別の `*` キーを作成してから削除してください

### 使い方

```bash
curl -H "Authorization: Bearer <secret>" http://localhost:5000/v1/chat/completions ...
```

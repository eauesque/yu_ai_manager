# AI Analysis API

AI による画像分析・プロンプトトレンド分析・サーバー管理に関する API。

全ての POST/PUT/DELETE エンドポイントには `X-Requested-With` ヘッダが必要（Bearer API Key 使用時は不要）。

## レート制限

`/api/analysis/` 配下の書き込みエンドポイントは全て **HEAVY** ティア（約 20 req/min、バースト 5）。GET エンドポイントは無制限。

---

## 設定

### GET /api/analysis/config

AI 分析の現在の設定を取得。API キーはマスクされて返される。

#### レスポンス

```json
{
  "engine": "ollama",
  "api_key": "sk-T...xy",
  "model": "claude-sonnet-4-6",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "openai_api_key": "sk-...xy",
  "openai_model": "gpt-4o-mini",
  "openai_compat_url": "http://localhost:8080/v1",
  "openai_compat_api_key": "***...ey",
  "openai_compat_model": "qwen2-vl",
  "hailo_vlm_model": "qwen2-vl-2b-instruct",
  "fallback_local_only": false,
  "language": "ja",
  "is_local": true,
  "has_servers": true,
  "servers": [],
  "active_server": "ollama-main"
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `engine` | string | 現在のエンジン種別 (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `api_key` | string | Claude API キー（マスク済み） |
| `model` | string | Claude API モデル名 |
| `ollama_url` | string | Ollama サーバー URL |
| `ollama_model` | string | Ollama モデル名 |
| `openai_api_key` | string | OpenAI API キー（マスク済み） |
| `openai_model` | string | OpenAI モデル名 |
| `openai_compat_url` | string | OpenAI 互換サーバー URL |
| `openai_compat_api_key` | string | OpenAI 互換 API キー（マスク済み） |
| `openai_compat_model` | string | OpenAI 互換モデル名 |
| `hailo_vlm_model` | string | Hailo VLM モデル名 |
| `fallback_local_only` | boolean | ローカルエンジンのみ使用するか |
| `language` | string | 分析結果の言語 (`ja`, `en` 等) |
| `is_local` | boolean | 現在のエンジンがローカル（無料）かどうか |
| `has_servers` | boolean | サーバーレジストリが設定されているか |
| `servers` | array | サーバー一覧（`has_servers` が true の場合のみ） |
| `active_server` | string | アクティブサーバーの ID（`has_servers` が true の場合のみ） |

### POST /api/analysis/config

AI 分析の設定を保存。マスクされた値（`...` を含む文字列）は上書きされない。API キーは自動的に暗号化される。

#### レート制限

HEAVY

#### リクエスト

```json
{
  "engine": "ollama",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "llava:latest",
  "language": "ja"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `engine` | string | いいえ | エンジン種別 |
| `api_key` | string | いいえ | Claude API キー |
| `model` | string | いいえ | Claude API モデル |
| `ollama_url` | string | いいえ | Ollama サーバー URL |
| `ollama_model` | string | いいえ | Ollama モデル名 |
| `openai_api_key` | string | いいえ | OpenAI API キー |
| `openai_model` | string | いいえ | OpenAI モデル名 |
| `openai_compat_url` | string | いいえ | OpenAI 互換サーバー URL |
| `openai_compat_api_key` | string | いいえ | OpenAI 互換 API キー |
| `openai_compat_model` | string | いいえ | OpenAI 互換モデル名 |
| `hailo_vlm_model` | string | いいえ | Hailo VLM モデル名 |
| `fallback_local_only` | boolean | いいえ | ローカルエンジンのみに制限 |
| `language` | string | いいえ | 分析結果の言語 |

#### レスポンス

```json
{
  "success": true
}
```

---

## エンジン検出

### GET /api/analysis/available-engines

設定済みで到達可能なエンジンの一覧を取得。`fallback_local_only` が有効な場合、クラウドエンジンは除外される。

#### レスポンス

```json
{
  "engines": [
    {
      "type": "ollama",
      "label": "Ollama",
      "model": "llava:latest",
      "models": ["llava:latest", "llava:13b", "bakllava:latest"]
    },
    {
      "type": "hailo_vlm",
      "label": "Hailo VLM",
      "model": "qwen2-vl-2b-instruct",
      "models": ["qwen2-vl-2b-instruct"]
    }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `engines[].type` | string | エンジン種別識別子 |
| `engines[].label` | string | 表示用ラベル |
| `engines[].model` | string | 現在設定されているモデル |
| `engines[].models` | string[] | 利用可能なモデル一覧 |

---

## 単体分析

### POST /api/analysis/analyze/\<file_id\>

指定したファイルを AI エンジンで分析する。画像・動画・アーカイブ内画像に対応。

#### レート制限

HEAVY

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `file_id` | int | ファイル ID（パスパラメータ） |

#### リクエスト

JSON ボディはオプション。省略時はデフォルト設定で分析される。

```json
{
  "mode": "full",
  "engine": "ollama",
  "model": "llava:latest",
  "server_id": "ollama-main"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `mode` | string | いいえ | 分析モード。デフォルト `"full"` |
| `engine` | string | いいえ | エンジン種別を上書き |
| `model` | string | いいえ | モデル名を上書き |
| `server_id` | string | いいえ | 使用するサーバー ID を指定 |

#### レスポンス (200)

```json
{
  "success": true,
  "result": {
    "description": "A landscape painting with mountains...",
    "style": "digital art",
    "quality_score": 8,
    "tags": ["landscape", "mountains", "sunset"]
  },
  "engine": "Ollama (llava:latest)"
}
```

#### エラーレスポンス

- `400`: エンジンが設定されていない / 無効なエンジン指定
- `404`: ファイルが見つからない / ディスク上にファイルが存在しない
- `500`: 分析処理中のエラー

### GET /api/analysis/result/\<file_id\>

保存済みの分析結果を取得。複数エンジン・モードの結果がある場合は全て返される。

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `file_id` | int | ファイル ID（パスパラメータ） |

#### レスポンス (200) — 結果あり

```json
{
  "found": true,
  "result": {
    "engine": "Ollama (llava:latest)",
    "description": "A landscape painting...",
    "style": "digital art",
    "quality_score": 8,
    "analyzed_at": 1709500000
  },
  "results": [
    {
      "engine": "Ollama (llava:latest)",
      "description": "A landscape painting...",
      "style": "digital art",
      "quality_score": 8,
      "analyzed_at": 1709500000
    }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `found` | boolean | 分析結果が存在するか |
| `result` | object | 最新の分析結果（後方互換用） |
| `results` | array | 全ての分析結果の配列 |

#### レスポンス (200) — 結果なし

```json
{
  "found": false
}
```

---

## バッチ分析

### POST /api/analysis/batch

未分析ファイルのバッチ AI 分析を開始。バックグラウンドで実行される。

#### レート制限

HEAVY

#### リクエスト

```json
{
  "limit": 10,
  "scan_root": "",
  "file_ids": [],
  "server_ids": ["ollama-main", "openai-compat"]
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `limit` | int | いいえ | 分析対象の上限数。デフォルト 10。クラウドエンジンの場合は最大 10 に制限される。ローカルエンジンの場合、0 で全件 |
| `scan_root` | string | いいえ | 対象を特定のスキャンルート内に限定 |
| `file_ids` | int[] | いいえ | 分析対象のファイル ID を直接指定 |
| `server_ids` | string[] | いいえ | 使用するサーバー ID のリスト。複数指定で並列分析 |

#### レスポンス (200)

```json
{
  "started": true,
  "count": 10,
  "parallel": false
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `started` | boolean | ジョブが開始されたか |
| `count` | int | 分析対象のファイル数 |
| `parallel` | boolean | 並列実行かどうか（`server_ids` 複数指定時） |
| `worker` | boolean | 推論ワーカー経由で実行された場合 true |
| `subprocess` | boolean | サブプロセスで実行された場合 true（Hailo VLM） |

#### エラーレスポンス

- `400`: 分析対象のファイルがない
- `409`: AI 分析ジョブが既に実行中

### POST /api/analysis/batch/cancel

実行中のバッチ AI 分析ジョブをキャンセルする。

#### レート制限

HEAVY

#### リクエスト

ボディ不要。

#### レスポンス (200)

```json
{
  "status": "cancelling",
  "message": "AI analysis cancel requested"
}
```

#### エラーレスポンス

- `404`: 実行中の AI 分析ジョブがない

---

## プロンプトトレンド分析

### POST /api/analysis/trends

最近の 50 件のプロンプトに対してトレンド分析を実行。結果は履歴に自動保存される。

#### レート制限

HEAVY

#### リクエスト

ボディ不要。

#### レスポンス (200)

```json
{
  "success": true,
  "result": {
    "summary": "Recent prompts focus on landscape and character art...",
    "top_themes": ["landscape", "character", "fantasy"],
    "trend_direction": "increasing variety"
  }
}
```

#### エラーレスポンス

- `400`: API キーが設定されていない（クラウドエンジン使用時）
- `500`: トレンド分析処理中のエラー

### GET /api/analysis/trends/history

プロンプトトレンド分析の履歴を取得。新しい順でソート。最大 50 件保持。

#### パラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|------|-----------|------|
| `limit` | int | 20 | 取得件数（最大 50） |
| `offset` | int | 0 | オフセット |

#### レスポンス

```json
{
  "items": [
    {
      "id": 5,
      "engine": "ollama",
      "analyzed_at": 1709500000,
      "prompt_count": 50,
      "result": {
        "summary": "Recent prompts focus on...",
        "top_themes": ["landscape", "character"]
      }
    }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `items[].id` | int | 履歴 ID |
| `items[].engine` | string | 使用されたエンジン種別 |
| `items[].analyzed_at` | int | 分析実行時の UNIX タイムスタンプ |
| `items[].prompt_count` | int | 分析対象のプロンプト数 |
| `items[].result` | object | トレンド分析結果 |

### DELETE /api/analysis/trends/history/\<history_id\>

トレンド分析履歴の個別エントリを削除。

#### レート制限

HEAVY

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `history_id` | int | 履歴 ID（パスパラメータ） |

#### レスポンス

```json
{
  "deleted": true
}
```

#### エラーレスポンス

- `404`: 指定された履歴が見つからない

---

## 統計

### GET /api/analysis/stats

AI 分析の統計情報を取得。

#### レスポンス

```json
{
  "total_analyzed": 150,
  "total_files": 1200,
  "styles": [
    { "style": "digital art", "count": 45 },
    { "style": "anime", "count": 30 }
  ],
  "quality_distribution": [
    { "tier": "excellent", "count": 20, "avg_score": 8.5 },
    { "tier": "good", "count": 60, "avg_score": 6.8 },
    { "tier": "average", "count": 50, "avg_score": 4.9 },
    { "tier": "low", "count": 20, "avg_score": 2.3 }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `total_analyzed` | int | 分析済みファイル数 |
| `total_files` | int | 全ファイル数（削除済み除く） |
| `styles` | array | スタイル別の集計（上位 10 件） |
| `styles[].style` | string | スタイル名 |
| `styles[].count` | int | 該当ファイル数 |
| `quality_distribution` | array | 品質スコアの分布 |
| `quality_distribution[].tier` | string | 品質ティア (`excellent` >= 8, `good` >= 6, `average` >= 4, `low` < 4) |
| `quality_distribution[].count` | int | 該当ファイル数 |
| `quality_distribution[].avg_score` | float | 平均スコア |

---

## Ollama 接続

### GET /api/analysis/ollama/models

設定済みの Ollama サーバーに接続し、利用可能なモデル一覧を取得。

#### レスポンス

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### エラーレスポンス

- `400`: Ollama URL が無効

### POST /api/analysis/ollama/test

指定した URL で Ollama サーバーへの接続をテスト。

#### レート制限

HEAVY

#### リクエスト

```json
{
  "ollama_url": "http://localhost:11434"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `ollama_url` | string | はい | テスト対象の Ollama サーバー URL |

#### レスポンス

```json
{
  "available": true,
  "models": [
    { "name": "llava:latest", "size": 4700000000 }
  ]
}
```

#### エラーレスポンス

- `400`: URL が空 / URL が無効

---

## OpenAI 互換サーバー接続

### GET /api/analysis/openai-compat/models

設定済みの OpenAI 互換サーバーに接続し、利用可能なモデル一覧を取得。

#### レスポンス

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### エラーレスポンス

- `400`: URL が設定されていない / URL が無効

### POST /api/analysis/openai-compat/test

指定した URL で OpenAI 互換サーバーへの接続をテスト。

#### レート制限

HEAVY

#### リクエスト

```json
{
  "url": "http://localhost:8080/v1",
  "api_key": "optional-key"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `url` | string | はい | テスト対象の URL |
| `api_key` | string | いいえ | API キー（必要な場合） |

#### レスポンス

```json
{
  "available": true,
  "models": [
    { "id": "qwen2-vl-7b-instruct" }
  ]
}
```

#### エラーレスポンス

- `400`: URL が空 / URL が無効

---

## AI サーバーレジストリ

複数の AI サーバーを登録・管理し、優先度ベースのフォールバックや並列分析を実現する。

### GET /api/analysis/servers

登録済みサーバーの一覧をステータス付きで取得。API キーはマスクされる。

#### レスポンス

```json
{
  "servers": [
    {
      "id": "ollama-main",
      "name": "Ollama (llava:latest)",
      "type": "ollama",
      "priority": 10,
      "enabled": true,
      "config": {
        "base_url": "http://localhost:11434",
        "model": "llava:latest"
      },
      "is_active": true,
      "status": "unknown"
    }
  ]
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `servers[].id` | string | サーバー ID（不変） |
| `servers[].name` | string | 表示名 |
| `servers[].type` | string | エンジン種別 (`claude_api`, `openai`, `ollama`, `openai_compat`, `hailo_vlm`) |
| `servers[].priority` | int | 優先度（小さいほど高優先） |
| `servers[].enabled` | boolean | 有効/無効 |
| `servers[].config` | object | エンジン固有の設定 |
| `servers[].is_active` | boolean | 現在アクティブなサーバーか |
| `servers[].status` | string | 接続ステータス（一覧では常に `"unknown"`） |

### POST /api/analysis/servers

新しいサーバーを登録。最初のサーバーは自動的にアクティブに設定される。

#### レート制限

HEAVY

#### リクエスト

```json
{
  "name": "Local Ollama",
  "type": "ollama",
  "config": {
    "base_url": "http://localhost:11434",
    "model": "llava:latest"
  }
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `name` | string | はい | サーバー名 |
| `type` | string | はい | エンジン種別 |
| `config` | object | はい | エンジン固有の設定 |
| `priority` | int | いいえ | 優先度 |
| `enabled` | boolean | いいえ | 有効/無効。デフォルト true |

#### レスポンス (201)

```json
{
  "success": true,
  "server": {
    "id": "local-ollama",
    "name": "Local Ollama",
    "type": "ollama",
    "priority": 10,
    "enabled": true,
    "config": { "base_url": "http://localhost:11434", "model": "llava:latest" }
  }
}
```

#### エラーレスポンス

- `400`: バリデーションエラー / サーバー数上限

### PUT /api/analysis/servers/\<server_id\>

サーバーの設定を更新。`id` は変更不可。

#### レート制限

HEAVY

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `server_id` | string | サーバー ID（パスパラメータ） |

#### リクエスト

```json
{
  "name": "Updated Name",
  "type": "ollama",
  "priority": 20,
  "enabled": true,
  "config": { "base_url": "http://192.168.1.100:11434", "model": "llava:13b" }
}
```

全フィールドはオプション。指定したフィールドのみ更新される。

#### レスポンス

```json
{
  "success": true,
  "server": { "id": "ollama-main", "name": "Updated Name", "..." : "..." }
}
```

#### エラーレスポンス

- `400`: 無効な type / サーバーが見つからない

### DELETE /api/analysis/servers/\<server_id\>

サーバーを削除。アクティブサーバーが削除された場合、次の優先度のサーバーが自動的にアクティブになる。

#### レート制限

HEAVY

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `server_id` | string | サーバー ID（パスパラメータ） |

#### レスポンス

```json
{
  "success": true
}
```

#### エラーレスポンス

- `400`: サーバーが見つからない

### POST /api/analysis/servers/\<server_id\>/activate

指定したサーバーをアクティブに切り替え。

#### レート制限

HEAVY

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `server_id` | string | サーバー ID（パスパラメータ） |

#### レスポンス

```json
{
  "success": true,
  "active": "ollama-main"
}
```

#### エラーレスポンス

- `400`: サーバーが見つからない

### POST /api/analysis/servers/\<server_id\>/test

サーバーへの接続テストを実行。応答時間も測定される。

#### レート制限

HEAVY

#### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `server_id` | string | サーバー ID（パスパラメータ） |

#### レスポンス

```json
{
  "success": true,
  "available": true,
  "elapsed_ms": 45,
  "server": {
    "id": "ollama-main",
    "name": "Local Ollama",
    "type": "ollama",
    "config": { "..." : "..." }
  }
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `available` | boolean | サーバーが到達可能か |
| `elapsed_ms` | int | 接続テストの応答時間（ミリ秒） |
| `server` | object | サーバー情報 |

#### エラーレスポンス

- `400`: サーバーが見つからない

### PUT /api/analysis/servers/reorder

サーバーの優先順位を一括変更。

#### レート制限

HEAVY

#### リクエスト

```json
{
  "server_ids": ["ollama-main", "openai-compat", "claude-api"]
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `server_ids` | string[] | はい | サーバー ID の配列。指定順が新しい優先順位になる |

#### レスポンス

```json
{
  "success": true
}
```

#### エラーレスポンス

- `400`: `server_ids` が配列でない

### POST /api/analysis/servers/migrate

レガシー `ai_analysis` 設定から新しいサーバーレジストリ形式へ自動マイグレーション。既にサーバーが登録済みの場合はエラー。

#### レート制限

HEAVY

#### リクエスト

ボディ不要。

#### レスポンス

```json
{
  "success": true,
  "servers": [
    { "id": "ollama", "name": "Ollama (llava:latest)", "type": "ollama", "..." : "..." }
  ],
  "migrated": 3
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `servers` | array | マイグレーションで作成されたサーバー一覧 |
| `migrated` | int | 作成されたサーバー数 |

#### エラーレスポンス

- `400`: `ai_servers` が既に存在する

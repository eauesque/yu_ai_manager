# API: /api/llm_router (Admin)

LLM Router の管理操作用エンドポイント群。通常の WebUI セッション認証（PIN/セッション）で保護されており、OpenAI 互換の `/v1/*` サーフェスとは完全に分離されている。

> **注意**: これらは管理用エンドポイントであり、LLM 推論リクエストを行う `/v1/chat/completions` 等とは別物。

---

## 共通レスポンス形式

全エンドポイントは `api_result` ラッパーを使用する。成功時のボディは `data` キー配下にネストされる。

```json
{
  "status": "ok",
  "data": { ... }
}
```

エラー時:

```json
{
  "status": "error",
  "error": "エラーの説明"
}
```

---

## GET /api/llm_router/status

ダッシュボード全体を 1 リクエストで描画するためのスナップショット。全バックエンド情報・エイリアスマップを返す。

### リクエスト

```
GET /api/llm_router/status
```

パラメータなし。

### レスポンス `200 OK`

```json
{
  "status": "ok",
  "data": {
    "router": {
      "version": "1.0.0",
      "alias_count": 2
    },
    "backends": [
      {
        "alias": "ollama-mac",
        "base_url": "http://192.168.1.10:11434",
        "source": "static",
        "status": "ready",
        "slo_state": null,
        "disabled": false,
        "model_count": 3,
        "models": [
          {
            "name": "qwen2.5:7b",
            "context_window": 32768,
            "size_b": 7.6
          },
          {
            "name": "llama3.2:3b",
            "context_window": 128000,
            "size_b": 3.2
          }
        ],
        "last_seen": "2026-04-09T12:34:56.789123",
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "base_url": "http://192.168.1.20:8080",
        "source": "mdns",
        "status": "unreachable",
        "slo_state": "unknown",
        "disabled": false,
        "model_count": 0,
        "models": [],
        "last_seen": null,
        "last_error": "Connection refused"
      }
    ],
    "aliases": {
      "default-llm": "ollama-mac/qwen2.5:7b",
      "fast-chat": "ollama-mac/llama3.2:3b"
    }
  }
}
```

### フィールド説明

**`router`**

| フィールド | 型 | 説明 |
|---|---|---|
| `version` | string | ルーターのスキーマバージョン（現在 `"1.0.0"`） |
| `alias_count` | int | 定義されているエイリアス数 |

**`backends[]`**

| フィールド | 型 | 説明 |
|---|---|---|
| `alias` | string | バックエンドの一意識別子 |
| `base_url` | string | OpenAI 互換エンドポイントのベース URL |
| `source` | string | `"static"`（設定ファイル）または `"mdns"`（自動発見） |
| `status` | string | `"ready"` / `"unreachable"` / `"unknown"` |
| `slo_state` | string \| null | `"vision_idle"` / `"vision_active"` / `"unknown"` / `null` |
| `disabled` | bool | `true` の場合はルーティング対象外 |
| `model_count` | int | 公開モデル数 |
| `models[]` | array | モデル一覧（`name`, `context_window`, `size_b`） |
| `last_seen` | string \| null | 最後の正常疎通日時（ISO 8601） |
| `last_error` | string \| null | 最後のエラーメッセージ |

**`aliases`**

論理エイリアス名 → 物理モデル ID（`バックエンドalias/モデル名`）のマップ。

---

## POST /api/llm_router/refresh

全バックエンドまたは指定バックエンドに対して強制プローブを実行し、`status` とモデル一覧を更新する。

### リクエスト

**全バックエンドを更新する場合（ボディなし）:**

```
POST /api/llm_router/refresh
Content-Type: application/json

{}
```

または Content-Type ヘッダーなしの空ボディでも可。

**特定バックエンドのみ更新する場合:**

```json
{
  "alias": "ollama-mac"
}
```

### レスポンス `200 OK`

```json
{
  "status": "ok",
  "data": {
    "refreshed": [
      {
        "alias": "ollama-mac",
        "status": "ready",
        "model_count": 3,
        "disabled": false,
        "last_error": null
      },
      {
        "alias": "mdns-pi5-hailo",
        "status": "unreachable",
        "model_count": 0,
        "disabled": false,
        "last_error": "Connection refused"
      }
    ]
  }
}
```

`refreshed` 配列の各要素は軽量な更新結果のみを含む（全フィールドは `/status` で取得）。

### エラー `404 Not Found`

`alias` を指定したが存在しない場合:

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### 備考

- プローブは同期的に実行される（完了まで待機してからレスポンスを返す）
- `disabled: true` のバックエンドに対してもプローブは実行される（status は更新される）
- mDNS 由来バックエンドも対象

---

## POST /api/llm_router/backends/`<alias>`/disable

指定バックエンドを無効化する。無効化されたバックエンドはルーティングから除外され、`data/llm_router_state.json` に永続化される。

### リクエスト

```
POST /api/llm_router/backends/ollama-mac/disable
```

ボディは不要。

### レスポンス `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": true
  }
}
```

### エラー `404 Not Found`

```json
{
  "status": "error",
  "error": "unknown backend: nonexistent-alias"
}
```

### エラー `500 Internal Server Error`

ディスクへの永続化に失敗した場合（権限エラー・ディスクフル等）。インメモリ状態はロールバックされる。

```json
{
  "status": "error",
  "error": "failed to persist disabled state"
}
```

### 永続化の仕組み

1. インメモリカタログの `disabled` フラグを `true` に設定
2. `data/llm_router_state.json` をアトミック書き込み（`.tmp` 経由で `os.replace`）
3. 書き込み失敗時はステップ 1 をロールバックして `500` を返す

アプリ再起動後も無効化状態が保持される。mDNS で動的発見されるバックエンドが起動前に disable された場合も、発見後に自動的に disabled 状態が適用される。

---

## POST /api/llm_router/backends/`<alias>`/enable

指定バックエンドを有効化する。`disable` の逆操作。

### リクエスト

```
POST /api/llm_router/backends/ollama-mac/enable
```

ボディは不要。

### レスポンス `200 OK`

```json
{
  "status": "ok",
  "data": {
    "alias": "ollama-mac",
    "disabled": false
  }
}
```

### エラー

`disable` エンドポイントと同じ（`404` / `500`）。`disabled: false` で永続化される。

---

## エンドポイント一覧

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/api/llm_router/status` | 全バックエンド・エイリアスのスナップショット取得 |
| `POST` | `/api/llm_router/refresh` | 全体または個別バックエンドの強制プローブ |
| `POST` | `/api/llm_router/backends/<alias>/disable` | バックエンド無効化（永続化あり） |
| `POST` | `/api/llm_router/backends/<alias>/enable` | バックエンド有効化（永続化あり） |

## 関連ドキュメント

- [LLM Router WebUI ガイド](../llm-router/webui.md)
- [LLM Router セットアップ](../llm-router/setup.md)

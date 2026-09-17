# API: /api/mdns (ピア発見)

> 対象バージョン: v4.64.0 以降（Hailo 拡張は v4.66.0 以降、`_ollama._tcp.local.` bare Ollama peer は v4.71.0 以降）

LAN 上の yu_ai_manager ノードが mDNS (`_yu-ai._tcp.local.`) で互いを発見するための API です。v4.71.0 以降は、`yu_ai_manager` 同居 local Ollama を `_ollama._tcp.local.` で独自広告した bare Ollama peer もこの一覧に含まれます。エンドポイントは 2 つあります。

---

## GET /api/mdns/identity

### 概要

ノードの自己紹介エンドポイント。他のノードがピア検証時に呼び出し、mDNS でアドバタイズした情報が本物の yu_ai_manager インスタンスのものかを確認します。

### 認証

**認証バイパス（不要）。** ピア間の相互検証で使うため意図的に認証を外しています。レスポンスには mDNS で既に公開済みの情報のみが含まれます。シークレットや機密情報は一切含まれません。

### レスポンス

```json
{
  "product": "yu_ai_manager",
  "node_id": "a1b2c3d4-...",
  "version": "4.66.0",
  "capabilities": ["hailo"],
  "hailo_ollama_url": "http://192.168.1.10:11434"
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `product` | string | 常に `"yu_ai_manager"` |
| `node_id` | string | ノードの一意 UUID |
| `version` | string | アプリバージョン（VERSION ファイルから読込）|
| `capabilities` | string[] | 利用可能な機能リスト。現在は `"hailo"` のみ |
| `hailo_ollama_url` | string (省略可) | Hailo-Ollama の LAN アクセス URL。LAN IP が特定できない場合は含まれない |

**`capabilities` に `"hailo"` が含まれる条件:** LLM Router カタログに `"hailo-local"` バックエンドが登録されている場合。

**`hailo_ollama_url` が含まれる条件:** カタログに `"hailo-ollama-local"` が登録されており、かつ LAN IP を特定できた場合。ループバックアドレス (`127.0.0.1` 等) は LAN IP に書き換えられます。

---

## GET /api/mdns/peers

### 概要

このノードが発見した LAN ピアの一覧を返します。mDNS サブシステムの状態確認・デバッグ用です。

### 認証

**認証バイパス（不要）。** レスポンスには mDNS で既に LAN にブロードキャスト済みの情報のみが含まれます。

### レスポンス（通常時）

```json
{
  "running": true,
  "status": "browsing",
  "self_node_id": "a1b2c3d4-...",
  "peers": [
    {
      "node_id": "e5f6a7b8-...",
      "hostname": "raspberrypi.local",
      "version": "4.66.0",
      "llm_base_url": "http://192.168.1.20:11434",
      "llm_provider": "ollama",
      "capabilities": ["hailo"],
      "web_port": 5000,
      "addresses": ["192.168.1.20"],
      "hailo_ollama_url": "http://192.168.1.20:11434",
      "first_seen": 1712600000.0,
      "last_seen": 1712603600.0
    },
    {
      "node_id": "dbc8d83c...",
      "hostname": "windows-box.local",
      "version": "0",
      "llm_base_url": "http://192.168.50.247:11434/v1",
      "llm_provider": "ollama",
      "capabilities": ["llm"],
      "web_port": 0,
      "addresses": ["192.168.50.247", "172.27.48.1", "172.18.192.1"],
      "hailo_ollama_url": null,
      "first_seen": 1712600000.0,
      "last_seen": 1712603600.0
    }
  ]
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `running` | bool | mDNS サブシステムが稼働中か |
| `status` | string | サブシステムの状態文字列 |
| `self_node_id` | string | 自ノードの node_id |
| `peers` | object[] | 発見済みピアのリスト（下表参照）|

**peers 各要素:**

| フィールド | 型 | 説明 |
|---|---|---|
| `node_id` | string | ピアの一意 UUID |
| `hostname` | string | mDNS ホスト名 |
| `version` | string | ピアのアプリバージョン |
| `llm_base_url` | string \| null | ピアの LLM エンドポイント URL |
| `llm_provider` | string \| null | LLM プロバイダ名（例: `"ollama"`）|
| `capabilities` | string[] | ピアの capability リスト |
| `web_port` | int \| null | ピアの Web UI ポート |
| `addresses` | string[] | ピアの LAN IP アドレス一覧 |
| `hailo_ollama_url` | string \| null | ピアの Hailo-Ollama URL |
| `first_seen` | float \| null | 初回発見時刻（Unix タイムスタンプ）|
| `last_seen` | float \| null | 最終確認時刻（Unix タイムスタンプ）|

**bare Ollama peer (`_ollama._tcp.local.`) の補足:**

- `version` は `"0"`
- `web_port` は `0`
- `llm_provider` は `"ollama"`
- `llm_base_url` は `http://<reachable_ip>:11434/v1`
- これは `yu_ai_manager` 同居 local Ollama を独自広告した結果で、
  `yu_ai_manager` 未起動の pure Ollama ノードを意味するとは限りません

### レスポンス（mDNS 未初期化時）

```json
{
  "running": false,
  "reason": "mdns subsystem not initialised (disabled or init failed)",
  "peers": []
}
```

`running: false` の場合は mDNS が無効か初期化に失敗しています。設定と起動ログを確認してください。

---

## デバッグモード

環境変数 `TAGDB_DEBUG_TRUSTED_PEERS=1` を設定して起動すると、`/api/mdns/peers` のレスポンスに追加フィールドが含まれます。

```json
{
  "running": true,
  "peers": [...],
  "trusted_ips": ["192.168.1.20", "192.168.1.30"],
  "bridge": {
    "managed_aliases": ["ollama-192.168.1.20"],
    "config_aliases": ["my-nas"],
    "cooldown_seconds_remaining": {
      "e5f6a7b8": 12.3
    }
  }
}
```

| フィールド | 説明 |
|---|---|
| `trusted_ips` | 信頼済み IP レジストリに登録された IP 一覧 |
| `bridge.managed_aliases` | mDNS ブリッジが管理するエイリアス一覧 |
| `bridge.config_aliases` | config で静的に定義されたエイリアス一覧 |
| `bridge.cooldown_seconds_remaining` | node_id 先頭 8 文字をキーとしたクールダウン残り秒数 |

**注意:** `trusted_ips` は攻撃対象リストになり得るため、デフォルトでは非公開です。本番環境では `TAGDB_DEBUG_TRUSTED_PEERS=1` を設定しないでください。

---

## mDNS 発見フロー

```
他ノード起動
    │
    ▼
mDNS _yu-ai._tcp.local. / _ollama._tcp.local. をアドバタイズ
    │
    ▼
LlmRouterMdnsBridge が on_peer_added() を受信
    │
    ▼
yu peer は GET /api/mdns/identity で HTTP 検証
bare Ollama peer は /api/tags で reachability probe
    │
    ├─ 成功 → PeerRegistry・BackendCatalog に登録
    └─ 失敗 → クールダウン後に再試行
```

---

## 関連ファイル

- `routes/mdns_identity.py` — エンドポイント実装
- `core/mdns/` — mDNS サービス・アドレスユーティリティ
- `docs/development/investigations/` — mDNS 実機確認ログ（`ollama_mdns_phasec_validation_2026-04-11.md` は削除済み）
- `core/llm_router/state.py` — BackendCatalog
- `core/web/trusted_peer_registry.py` — 信頼済み IP レジストリ
- `docs/ja/mesh-inference/overview.md` — メッシュ推論アーキテクチャ全体

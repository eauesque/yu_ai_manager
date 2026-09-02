# Hailo LLM 自動発見

**対応バージョン**: v4.66.0 以降

## 概要

yu_ai_manager は Pi5 の Hailo NPU で動作する LLM エンドポイントを、
`config.json` の編集なしで自動的に発見して利用できるようにします。
Pi5 を LAN に挿すだけで、他の yu_ai_manager ノードから Hailo LLM を
呼び出せるようになります。

## 検出対象の 2 系統

| エンドポイント | 説明 | 既定 URL パターン |
|---|---|---|
| **yu extension Hailo LLM** | yu_ai_manager 内蔵の `builtin-hailo-genai` extension が提供する OpenAI 互換 LLM | `http://<host>:<yu-port>/ext/hailo-genai/v1/` |
| **hailo-ollama** | 外部バイナリ `/usr/bin/hailo-ollama` が提供する OpenAI 互換 LLM (既定 `:8000`) | `http://<host>:8000/v1/` |

両方が同時に動作していても両方とも自動登録されます。HailoRT 5.3.0+ で
`HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED` を設定すると HailoRT scheduler が
物理デバイスを round-robin で共有するため、同時に使っても衝突しません。

## ローカル自動登録 (Phase A)

yu_ai_manager 起動時に、以下の 2 つを独立に検出します:

1. **yu extension**: `hailo_platform.genai.LLM` が import 可能、かつ
   `/dev/hailo0` または `/dev/h1x-0` のどちらかが存在 → `hailo-local`
   backend として catalog に自動登録
   (v4.66.1 で Raspberry Pi 5 + AI HAT + HailoRT 5.3.0 の実機が
   `/dev/h1x-0` として公開されることに対応)
2. **hailo-ollama**: `localhost:8000/v1/models` に HTTP probe (2 秒タイムアウト)
   → 200 応答があれば `hailo-ollama-local` backend として自動登録

既に `config.json` の `llm_router.backends` に同名の alias があれば、その
設定が優先されます (上書きしません)。

## mDNS 自動広告 (Phase B)

Phase A の検出結果に応じて、yu_ai_manager は mDNS TXT レコードで他のノードに
Hailo capability を広告します:

- `capabilities=llm,hailo` — yu extension が利用可能なことを示す
- `hailo_ollama_url=http://192.168.1.10:8000/v1/` — hailo-ollama が動いている
  場合のみ (LAN 到達可能な IP に書き換えられる)

他の yu_ai_manager ノードは mDNS 経由でこれを受信すると、`/api/mdns/identity`
エンドポイントで identity 検証を行ったあと、以下の alias で追加 backend を
自動登録します:

- `mdns-<node_id[:8]>-hailo` — yu extension Hailo LLM (`capabilities` に
  `hailo` が含まれる場合、peer の `web_port` + addresses から URL を導出)
- `mdns-<node_id[:8]>-hailo-ollama` — 外部 hailo-ollama (`hailo_ollama_url`
  が広告されている場合、TXT に載った URL をそのまま使用)

## 設定

既定で有効。`config.json` で以下のように無効化できます:

```json
{
  "llm_router": {
    "hailo_ollama": {
      "enabled": false,
      "port": 8000
    }
  }
}
```

- **`enabled`**: `false` にすると hailo-ollama の自動検出を完全に無効化。
  yu extension 側の検出は別に制御されます (extension がロードされているか
  どうかで自動判定)
- **`port`**: hailo-ollama のポート番号 (既定 8000)。1〜65535 以外は既定値に
  フォールバックし warning ログを出します

## セキュリティ上の注意

**hailo-ollama には認証機能がありません**。mDNS で広告すると、**LAN 上の
任意のノードが hailo-ollama の推論リソースを自由に消費できる状態**になります。

| エンドポイント | 認証 | 実効的な LAN 公開範囲 |
|---|---|---|
| yu extension (`/ext/hailo-genai/v1/`) | yu の web auth chain (PIN/session/api-key) | yu に認証できるクライアントのみ |
| hailo-ollama (`hailo_ollama_url`) | **なし** | **LAN 上の全ノード** |

家庭内 LAN や信頼できる VLAN 以外での運用 (公衆 Wi-Fi 等) では、
`hailo_ollama.enabled: false` で自動広告を無効化してください。

## LLM Router WebUI での見え方

v4.65.0 の `/llm-router` ダッシュボードに自動登録された backend が表示
されます:

- `hailo-local` / `hailo-ollama-local` — ローカル検出 (source: `static` バッジ)
- `mdns-<id>-hailo` / `mdns-<id>-hailo-ollama` — mDNS で発見 (source: `mdns` バッジ)

いずれも Disable トグルで一時的に無効化可能です。無効化状態は
`data/llm_router_state.json` に永続化され、再起動後も保持されます
(v4.65.0 で実装)。

## 誤検出の安全性

Phase A 検出には 2 つの安全装置があります:

1. **自己 probe 回避**: `hailo_ollama.port` が yu 自身の web port と同じ値に
   設定されている場合、probe を完全スキップします (yu が自分自身を
   hailo-ollama と誤認するのを防ぐ)
2. **既存 backend 優先**: `config.json` に同じ `localhost:<port>/v1` の
   backend が既に登録されている場合、probe をスキップしてユーザの意図を
   尊重します

## TODO 残置項目

- (P3) 他言語翻訳 (`en`, `zh-tw`, `zh-cn`, `ko`) — v4.65.0 LLM Router WebUI
  の翻訳残債と合わせて一括対応予定
- (P3) Pi5 実機結合テスト — 2 ノード構成での Playwright 16 項目相当
- (P3) IPv6 サポート — 現状 `_pick_lan_ip` は IPv4 のみ返す
- (P3) 複数 Hailo デバイス対応 — 固定 alias `hailo-local` 前提。USB ドングル
  複数挿し等の場合は index suffix 設計を検討
- (P3) `BackendCatalog.remove_backend()` — 現状 `_mark_unreachable` は
  status 更新のみで catalog から削除しない

## 関連ドキュメント

- [LLM Router セットアップ](./setup.md)
- 設計仕様: `docs/superpowers/specs/2026-04-08-hailo-auto-discovery-design.md`
- 実装プラン: `docs/superpowers/plans/2026-04-08-hailo-auto-discovery.md`

## v4.66.2 — Trusted peer auth (実機認証穴の修正)

v4.66.0 の Hailo 自動発見では、yu の `/ext/hailo-genai/*` extension が
web auth chain の下にあるため、LLM Router driver (Bearer も session も
持たない) が probe/dispatch しようとすると認証 middleware の honeypot
HTML が返り、JSON parse に失敗して `unreachable` のまま固まる問題が
あった。

### 仕組み

- 新規 `TrustedPeerRegistry` が `127.0.0.1` / `::1` を init 時に seed
- `LlmRouterMdnsBridge` が peer の verify (`/api/mdns/identity` への HTTP
  GET + node_id 一致確認) に成功したら、その peer の advertised
  addresses を全て registry に追加
- `auth_chain.check_trusted_peer` が `/ext/<name>/v1/*` パスを受けたとき、
  remote_addr が registry に居れば PIN auth を bypass
- 既存の API key / session / cookie 認証経路はそのまま

### Quick lock との関係

- **loopback** (yu 自身の self-probe): quick_lock 中でも常に pass
- **peer IP**: quick_lock 中はリクエストを reject (`check_quick_lock` が
  503 を返す)。「ユーザーが意図的にロックした」状態を peer も尊重する

これにより以下が期待通り動く:

- pi2 の `hailo-local` self-probe (`http://localhost:5000/ext/hailo-genai/v1/models`)
- Windows から見た pi2 の `mdns-<id>-hailo` cross-node dispatch
  (`http://192.168.50.4:5000/ext/hailo-genai/v1/chat/completions`)

### 設定

設定ファイル変更不要。mDNS が無効化されている環境でも loopback seed
は機能するため、self-probe 修正だけは無条件に得られる。

### デバッグ

`TAGDB_DEBUG_TRUSTED_PEERS=1` 環境変数を設定して yu を起動すると、
`/api/mdns/peers` レスポンスに `trusted_ips` フィールドが追加される。
本番運用では設定しない (trust リストは「攻撃対象リスト」なので、
unauthenticated エンドポイントへの露出を avoid)。

### Security boundary

「信頼できる LAN 前提」運用ルール (v4.64.0 mDNS Phase B 時点と同じ前提)。
LAN に物理アクセスできる悪意あるノードからの保護は対象外 — その場合は
`/llm-router` WebUI の disable トグルや quick_lock で対処する。

詳細は `docs/superpowers/specs/2026-04-09-trusted-peer-auth-design.md`。

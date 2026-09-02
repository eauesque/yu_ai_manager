# mDNS バックエンドが「到達不能」のまま回復しない

LLM Router の mDNS 自動発見で追加されたバックエンドが「到達不能 (unreachable)」
のまま回復しない場合の原因・診断・対処をまとめる。

---

## 構造の概観

```
MdnsService (zeroconf layer)
  └─ on_peer_added / on_peer_updated / on_peer_removed
       └─ LlmRouterMdnsBridge
            ├─ _verify()       ← /api/mdns/identity を HTTP で確認
            ├─ _apply_peer_to_catalog()  ← BackendCatalog に登録
            ├─ _enter_cooldown() / _in_cooldown()  ← 失敗後の再試行制限
            └─ retry_pending_peers()  ← 60 秒周期 sweep（v4.91.15〜）
```

**重要な流れ**:

1. zeroconf がピアを検出 → `on_peer_added` 呼び出し
2. `_verify()` が `/api/mdns/identity` を叩き、`node_id` と `product` を検証
3. 成功 → `_apply_peer_to_catalog()` でバックエンドを catalog に追加
4. 失敗 → 60 秒 cooldown に入り、同じ `node_id` のイベントを無視
5. **v4.91.15〜**: 60 秒ごとの sweep タスクが未到達ピアを cooldown 期限切れ後に再試行

---

## 「到達不能」になる主なパターン

### パターン A — 初回 verify 失敗 → cooldown で沈黙

**症状**: LLM Router にバックエンドが表示されるが status=unreachable。  
**原因**:
- 相手ノードの起動直後にまだ HTTP サーバが上がっていなかった
- 自分のポートが変わっていてピアが古い TXT を参照していた（v4.91.14 以前の
  `--port` overrride バグ: 35a3679a で修正）

**挙動 (v4.91.14 以前)**: cooldown (60 秒) が明ければ次の `on_peer_updated`
イベントを待つが、そのイベントが発火しないと永久に回復しない。

**挙動 (v4.91.15〜)**: cooldown 期限切れ後、次の sweep tick（最大 60 秒後）
で自動再試行 → 成功すれば catalog に反映される。

---

### パターン B — zeroconf が `ServiceStateChange.Updated` を発火しない

**症状**: ピアが再起動したのに LLM Router が古いステータスのまま。  
**原因**: zeroconf のキャッシュ状態によっては TXT 変更時に `Updated` イベントが
飛ばないことがある（zeroconf ライブラリの既知の動作）。  
**対処**: v4.91.15 の sweep タスクが 60 秒以内に拾う。

---

### パターン C — 相手ノードのポートが広告値と違う

**症状**: curl では到達できるが verify timeout が続く。  
**原因**: `--port` CLI フラグを使いつつ config.json の `server.port` が
古い値のまま → mDNS TXT に間違ったポートが広告された。  
**修正**: v4.91.14 (35a3679a) で `config["server"]["port"]` を実効ポートで
上書きするよう修正済み。古い起動スクリプトが config.json を直接書き換えて
いる場合は設定ファイル側も確認すること。

---

### パターン D — trusted_peer_registry に登録されていない

**症状**: LLM Router は「ready」なのに `/ext/<name>/v1/*` へのプロキシが 403。  
**原因**: verify 成功で catalog には入ったが `_apply_peer_to_catalog()` が
呼ばれる前にプロセスが再起動した、または `service_kind != "yu"` で
registry 登録がスキップされた（bare Ollama ピアは登録しない仕様）。  
**確認**:
```bash
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool | grep -E 'node_id|trusted'
```

---

## 診断手順

### 1. ピアの現在状態を確認

```bash
# 自分が知っているピア一覧
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool

# LLM Router のバックエンド一覧（mDNS 由来は alias が "mdns-" で始まる）
curl -s http://127.0.0.1:PORT/api/llm_router/status | python3 -m json.tool
```

### 2. 相手ノードから自分の identity エンドポイントに到達できるか

相手ノード上で:
```bash
curl -v http://<自分のLAN-IP>:<PORT>/api/mdns/identity
```

期待レスポンス:
```json
{"product": "yu_ai_manager", "node_id": "...", "version": "..."}
```

失敗する場合:
- ファイアウォール / ルーティングの問題
- ポートが実効値と広告値で食い違っている（`--port` で起動しているか確認）

### 3. 自分が広告しているポートを確認

```bash
# 起動ログに "web_port" が表示される
grep -i "web_port\|mdns.*port\|effective_port" logs/app.log | tail -20

# または settings API
curl -s http://127.0.0.1:PORT/api/server/info | python3 -m json.tool | grep port
```

### 4. cooldown 状態を確認

GUI: **LLM Router** > バックエンドカード > 詳細 に `last_error` と
`last_seen_at` が表示される。エラーが "identity verification failed" なら
verify は到達できているが内容不一致（node_id / product 不整合）。
エラーが "timeout" なら HTTP 自体が届いていない。

### 5. sweep ログを確認

```bash
grep "\[mdns\] sweep" logs/app.log
```

`sweep re-verified peer <8文字>` が出ていれば sweep で回復したことを示す。

---

## 強制リカバリ（手動）

sweep を待たずに今すぐ回復させたい場合:

### 方法 1: 相手ノードを再起動

再起動すると zeroconf が `ServiceStateChange.Removed` + `Added` を発火 →
`on_peer_removed` が cooldown をクリア → `on_peer_added` で即再検証。

### 方法 2: mDNS サービス再起動 API（設定画面から）

**設定** > **LLM Router** > **mDNS 再起動** ボタン（存在する場合）。

### 方法 3: アプリ再起動

cooldown はメモリ上にしか存在しない。再起動すれば全 cooldown がリセットされ、
起動直後に全ピアを再検証する。

---

## 再発を防ぐポイント

| チェック | 確認方法 |
|---|---|
| `--port` 使用時は config.json の `server.port` も同じ値か | config.json 参照 |
| ファイアウォールで `PORT` の inbound が許可されているか | `sudo ufw status` / macOS 設定 |
| 複数 NIC 環境で正しい LAN インターフェースに bind しているか | `config.json` の `mdns.bind_address` |
| v4.91.15 以降を使用しているか（sweep タスク搭載） | `curl .../api/server/info` |

---

## 関連ファイル

| ファイル | 役割 |
|---|---|
| `core/llm_router/mdns_integration.py` | `LlmRouterMdnsBridge`・cooldown・retry_pending_peers |
| `core/web/runtime_mdns.py` | sweep タスク起動・停止 |
| `core/mdns/service.py` | zeroconf ラッパー・`list_peers()` |
| `core/web/trusted_peer_registry.py` | クロスノード `/ext/*` 認証 |

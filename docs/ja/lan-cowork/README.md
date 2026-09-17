# LAN Cowork

> 対象バージョン: v4.55.0 以降（PIN 認証は v4.92.0 以降）

## LAN Cowork とは

LAN Cowork は、ネットワーク上の複数の yu_ai_manager ノードを連携させる拡張機能です。  
各マシンが独立して動作しながら、重い処理を分担したり、フリートとして一括管理したりできます。

```
┌──────────────┐     mDNS 発見      ┌──────────────┐
│  Windows PC  │◄───────────────────►│   Mac Mini   │
│  (GPU 搭載)  │   PIN ペアリング    │  (コントロール)│
│              │◄───────────────────►│              │
│  分散推論    │                     │  Fleet 管理  │
│  (tagger等)  │                     │              │
└──────────────┘                     └──────────────┘
        ▲                                    ▲
        └────────────────────────────────────┘
                     ▼
              ┌──────────────┐
              │  Raspberry Pi│
              │ (Hailo NPU)  │
              └──────────────┘
```

---

## 機能一覧

| 機能 | 説明 |
|---|---|
| **mDNS 自動発見** | 同一 LAN 上のノードを設定なしで自動発見 |
| **PIN ペアリング** | 管理者が承認する PIN 認証でピア間トークンを発行 |
| **分散推論** | tagger・clip・yolo・whisper を複数ノードで並列処理 |
| **生成分散** | SD WebUI / ComfyUI ジョブを LAN 別ノードへ委譲 |
| **Fleet 管理** | ログ閲覧・バージョン更新を中央ノードから一括実施 |
| **ピアイベントリレー** | 別ノードのイベントを自ノードの SSE に流す |
| **LLM ルーティング** | 発見されたピアを LLM Router に自動登録 |

---

## セットアップ手順

### 1. 有効化

`config.json` の **`extensions` セクション**に追加します（最上位ではありません）:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true,
      "peer_name": "my-desktop"
    }
  }
}
```

再起動すると:
- UDP 19850 で他ノードの発見をリッスン開始
- `_yu-ai._tcp.local.` を mDNS でアドバタイズ開始

> **既定値はバックエンドによって異なります。**
> Python バックエンド併用（hybrid）では、このキーが無ければ**有効**として扱われます。
> Rust standalone（`yu-server` 単体）では、明示的に `true` にしない限り**無効**です。
> 詳細と、有効時にネットワーク上で実際に何が起きるかは
> [ネットワーク挙動](network-behavior.md) を参照してください。

> **注意**: 以前のこのページは有効化キーを最上位の `{"lan_cowork": {...}}` と案内していましたが、
> **その位置のキーはどの実装からも読まれません**。上記の `extensions` セクションが正しい位置です。

### 2. ノード同士をペアリング

ノード A から ノード B へ接続する場合：

1. **ノード A の WebUI** → `設定` → `LAN Cowork` → ノード B の URL を追加
2. ノード A が `POST /api/lan/pair/request` を送信
3. **ノード B の WebUI** → `/lan-cowork/peers` → 「承認待ち」タブで承認
4. 6桁 PIN がノード A に通知される（SSE 経由）
5. ノード A が PIN を入力 → Bearer トークン（30 日有効）を取得

> **注意**: ペアリングは一方向です。A→B と B→A を両方実施してください。

詳細は [ピア間 PIN 認証・トークンペアリング](peer-auth.md) を参照。

### 3. 動作確認

```bash
# 発見されたピア一覧（ノード A から）
curl http://localhost:5000/api/mdns/peers

# LAN Cowork で認識されているピア
curl http://localhost:5000/api/lan/peers
```

---

## 各機能のセットアップ

### 分散推論

ペアリング完了後、自動的に分散推論が利用可能になります。

- `設定` → `LAN Cowork` → 各ノードの推論タイプ（tagger/clip/yolo/whisper）を有効化
- または `/mesh-inference` ページのマトリクスで個別設定

詳細: [分散推論 セットアップ](../mesh-inference/setup.md)

### Fleet 管理

「チーフ」ノードから他ノードを管理する設定:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<ペアリング済み peer_id>"
        ]
      }
    }
  }
}
```

詳細: [Fleet 管理](../features/fleet-admin.md)

### 生成分散（SD / ComfyUI ジョブ委譲）

GPU を持つノードに生成ジョブを自動振り分けます。設定ファイルでの  
バックエンド登録または mDNS 自動発見経由で利用できます。  
ノード B で SD WebUI / ComfyUI が動いていれば、設定後すぐに利用可能です。

---

## ネットワーク要件

| ポート / プロトコル | 用途 | 必須 |
|---|---|---|
| UDP 5353 | mDNS（ノード発見） | 同一 L2 LAN 内のみ |
| UDP 19850 | LAN Cowork 発見 | 同一 L2 LAN 内のみ |
| TCP 5000 (デフォルト) | API・ペアリング・推論 | ピア間 |

- mDNS はルーター越え・VPN 越しでは動作しません（固定 IP か `.local` ホスト名を使用）
- ファイアウォールで UDP 5353 と TCP 5000 が LAN 内で開いていること

---

## ドキュメント一覧

| ドキュメント | 内容 |
|---|---|
| [ピア間 PIN 認証](peer-auth.md) | ペアリングフロー・トークン管理・セキュリティ設定 |
| [分散推論 セットアップ](../mesh-inference/setup.md) | 複数ノードで推論を並列化する手順 |
| [分散推論 マトリクス](../mesh-inference/toggle.md) | WebUI からピア単位・タイプ単位で有効化/無効化 |
| [分散推論 アーキテクチャ](../mesh-inference/overview.md) | 内部設計・ワークスティーリング・永続化 |
| [Fleet 管理](../features/fleet-admin.md) | リモートログ・バージョン更新の一括管理 |
| [mDNS ピア API](../api/mdns-peers.md) | `/api/mdns/*` エンドポイント詳細 |

---

## セキュリティについて

- mDNS は認証なし。**家庭内 LAN や信頼できるネットワーク専用**です
- 公衆 Wi-Fi や多人数 LAN では `"mdns": {"enabled": false}` で無効化してください
- ピア間通信は PIN ペアリング後の Bearer トークン（scrypt ハッシュで保存）で保護

# LLM Router セットアップ

## config.json への追加

```json
{
  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "ollama-local",
        "base_url": "http://localhost:11434/v1",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "local-fast": "ollama-local/qwen2.5:7b",
      "local-coder": "ollama-local/qwen2.5-coder:32b"
    }
  }
}
```

## Claude Code との連携

LLM Router は Anthropic 互換の `/v1/messages` エンドポイントを実装しているため、
Claude Code (Anthropic 公式 CLI) を **そのままローカル LLM 向けに使えます**。
追加プロキシ (claude-code-router 等) は不要です。

### 1. yu_ai_manager 側の alias 設定

Claude Code は内部で `claude-opus-4-*` / `claude-sonnet-4-*` / `claude-haiku-4-*`
等のモデル名を送ってきます。これらを `config.json` の `aliases` で
ローカルカテゴリ (`large` / `fast` / `vision`) または物理モデルへマップします:

```json
{
  "llm_router": {
    "enabled": true,
    "aliases": {
      "claude-opus-4-7":          "large",
      "claude-sonnet-4-6":        "fast",
      "claude-haiku-4-5":         "fast",
      "claude-3-5-haiku-20241022": "fast"
    }
  }
}
```

| Claude Code が送るモデル名 | 推奨マッピング先 | 用途 |
|---|---|---|
| `claude-opus-*` | `large` (例: qwen2.5:72b / llama3.3:70b) | メイン推論 |
| `claude-sonnet-*` | `fast` または `large` | バランス |
| `claude-haiku-*` | `fast` (例: qwen2.5:7b) | 背景の補助タスク (要約・タイトル生成等) |

`large` / `fast` / `vision` は `core/llm_core` カテゴリレジストリ由来の
仮想バックエンドで、登録済みモデルから自動選択されます (`/llm-router` WebUI で確認可)。

### 2. Claude Code 側の設定

`~/.claude/settings.json` (Windows: `%USERPROFILE%\.claude\settings.json`) に追記:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:5000/v1",
    "ANTHROPIC_AUTH_TOKEN": "dummy"
  }
}
```

- `ANTHROPIC_AUTH_TOKEN` は loopback アクセスでは検証されないが、Claude Code が
  値の存在を要求するためダミー文字列を入れる
- LAN の別マシンから繋ぐ場合は `http://<host>.local:5000/v1` 等に変更し、
  `config.json` の `auth.mode` を `api_key` にして実トークンを設定する

セッション単位で試したい場合は環境変数で:

```bash
ANTHROPIC_BASE_URL=http://localhost:5000/v1 ANTHROPIC_AUTH_TOKEN=dummy claude
```

### 3. 背景タスク用 (haiku 相当) を別モデルにしたい場合

Claude Code の背景タスクは `ANTHROPIC_SMALL_FAST_MODEL` で上書きできます:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:5000/v1",
    "ANTHROPIC_AUTH_TOKEN": "dummy",
    "ANTHROPIC_SMALL_FAST_MODEL": "fast"
  }
}
```

これでメインは alias 経由 (opus → large)、背景は明示的に `fast` カテゴリへ振り分けられます。

### 4. 動作確認

```bash
# yu_ai_manager 側で /v1/messages が応答するか
curl -s http://localhost:5000/v1/messages \
  -H "content-type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-opus-4-7","max_tokens":64,"messages":[{"role":"user","content":"ping"}]}'

# Claude Code から
claude
> /model          # 現在のモデル確認
> hello           # 応答が返ればローカル経由で動作
```

### 5. よくある詰まり

| 症状 | 原因 / 対処 |
|---|---|
| `model_not_found` エラー | Claude Code が送るモデル名が `aliases` / カテゴリのどちらにも該当していない。`/llm-router` WebUI でリクエストログのモデル名を確認し、alias を追加 |
| 応答が極端に遅い | `large` カテゴリが 70B クラスを掴んでいる。`aliases` で具体的な軽量モデルへ直接マップする |
| `401 unauthorized` | `auth.mode` が `api_key` で、Claude Code 側の `ANTHROPIC_AUTH_TOKEN` が一致していない |
| ストリームが途中で切れる | バックエンド (Ollama 等) のタイムアウトが短い。`config.json` の `backends[].timeout` を `120` 以上に |

### 6. 物理名 / 別 alias を直接指定したい

`aliases` セクションでは Claude モデル名以外も自由に追加できます:

```json
"aliases": {
  "local-fast":  "ollama-local/qwen2.5:7b",
  "local-coder": "ollama-mac/qwen2.5-coder:32b"
}
```

Claude Code 側で `/model local-coder` のように指定すれば直接そのモデルへルーティングされます。

### 7. ハイブリッド運用 (opus = 本物 Anthropic、sonnet/haiku = ローカル) の現状

「オーケストレーターは Anthropic の opus、サブエージェントだけローカル」という
分割運用は **現状の Claude Code + LLM Router では推奨しません**。理由:

- `ANTHROPIC_BASE_URL` はセッション全体に効くため、opus リクエストだけを
  Anthropic 本家へ素通しする設定は Claude Code 側で組めない
- LLM Router にアップストリーム passthrough バックエンドを追加すれば技術的には
  可能だが、**経済性が成立しない**:
  - **Max/Pro サブスクユーザー**: `ANTHROPIC_BASE_URL` を設定した時点でサブスク
    認証経路から外れ、passthrough した opus 分だけ API 単価で課金される (むしろ高くなる)
  - **API キー課金ユーザー**: passthrough しても opus のトークン単価は変わらず、
    サブエージェントをローカル化してもオーケストレーターが消費する opus
    トークンが支配的なため節約効果が薄い

**推奨方針**: コスト削減目的なら **オーケストレーターも含めて全部ローカル**
（例: `claude-opus-*` も `large` カテゴリへ alias）に倒し、ローカル側の
モデル選定 (Qwen2.5-72B / Llama 3.3-70B / DeepSeek 等) で品質を確保する。
オーケストレーター・実装エージェントを役割分担させる設計なら、70B 級でも
十分回せます。

将来的に Claude Code が `ANTHROPIC_OPUS_BASE_URL` のようなモデル別エンドポイント
分割をサポートした場合、この節は更新します。

## Continue (VSCode) との連携

`config.json`:
```json
{
  "models": [
    {
      "title": "Local Coder",
      "provider": "openai",
      "apiBase": "http://localhost:5000/v1",
      "model": "local-coder",
      "apiKey": "dummy"
    }
  ]
}
```

## ノード自動発見 — `.local` ホスト名サポート (家庭内 LAN)

家庭内 LAN で複数マシン (mac mini + Pi5 + Windows GPU 機など) を運用する
場合、`base_url` に IP アドレスではなく `.local` ホスト名を書くと **DHCP で
IP が変わってもそのまま動作** します。yu_ai_manager 側に追加実装は不要で、
`httpx` が OS の resolver (Bonjour / Avahi / mDNSResponder) を経由して
自動的に名前解決します。

```json
{
  "llm_router": {
    "enabled": true,
    "backends": [
      { "alias": "ollama-mac", "base_url": "http://mac-mini.local:11434/v1", "type": "ollama" },
      { "alias": "ollama-pi5", "base_url": "http://pi5.local:11434/v1",      "type": "ollama" },
      { "alias": "ollama-win", "base_url": "http://gpu-rig.local:11434/v1",  "type": "ollama" }
    ],
    "aliases": {
      "local-fast":  "ollama-mac/qwen2.5:7b",
      "local-coder": "ollama-pi5/qwen2.5-coder:32b",
      "local-big":   "ollama-win/llama3.3:70b"
    }
  }
}
```

サンプル: [`config.example.local-hostname.json`](../../../config.example.local-hostname.json)

### 動作要件

| OS | 必要なもの |
|---|---|
| macOS | Bonjour (標準で動作、追加インストール不要) |
| Linux | `avahi-daemon` (`sudo apt install avahi-daemon` / `sudo systemctl enable --now avahi-daemon`) |
| Windows 10/11 | mDNSResponder (Win10 1803 以降は OS 標準で `.local` 解決可能。動かない場合は Bonjour Print Services をインストール) |

### 動作確認

```bash
# 解決できることをテスト
python -c "import socket; print(socket.gethostbyname('mac-mini.local'))"
# → 192.168.x.x が返れば OK
```

### サブネット越え / 企業 LAN / VPN 越し

mDNS は L2 マルチキャストで動作するため、**ルーター越え・VPN 越し・
企業ネットワークの分離 VLAN では到達しません**。これらの環境では従来通り
IP アドレスを直接指定してください:

```json
"backends": [
  { "alias": "remote-gpu", "base_url": "http://10.20.30.40:11434/v1", "type": "ollama" },
  { "alias": "tailscale-mac", "base_url": "http://100.x.x.x:11434/v1", "type": "ollama" }
]
```

VLAN 分割環境などで mDNS reflector が必要なケースは LAN 管理者に相談して
ください。yu_ai_manager 側では mDNS reflector / プロキシは提供しません。

### 既知の制約

- **Windows の mDNS 解決は稀に遅い** (~1秒): バックエンド `timeout` を
  3 秒以上に設定推奨
- **`.local` 末尾必須**: `mac-mini` 単独では NetBIOS / DNS フォールバックに
  なるので必ず `mac-mini.local` と書く
- **Ollama 自身は標準では `_ollama._tcp.local.` を advertise しない**:
  ホスト名解決のみで、ポート (11434) は手書きが必要です。ただし
  **`yu_ai_manager` と同居している local Ollama** については v4.71.0 以降、
  `yu_ai_manager` 側が `_ollama._tcp.local.` を独自広告するため、他ノードの
  `yu_ai_manager` から `mdns-<id>-ollama` として自動発見できます。`yu` 非同居の
  pure Ollama ノードは引き続き固定 IP / `.local` / 手動 backend 設定を使ってください

## 環境変数

| 変数名 | 動作 |
|---|---|
| `TAGDB_DISABLE_LLM_ROUTER` | `1` で Router 全体を無効化 |
| `TAGDB_DISABLE_LLM_ROUTER_REFRESH` | `1` で 5 分 refresh ループを無効化 |
| `TAGDB_LLM_ROUTER_AUTH_MODE` | `none`/`loopback`/`api_key` を上書き |

## 他言語ドキュメント

CLAUDE.md の `docs/ 読み込みルール` に従い、`en/zh-tw/zh-cn/ko` バージョンを
`ja/` を元に同期する (実装後の別タスク; TODO.md 参照)。

## ノード自動発見 (Phase B — v4.64.0 以降)

同一 LAN 上の yu_ai_manager ノードは mDNS (`_yu-ai._tcp.local.`) により互いを自動発見します。`config.json` に手動でバックエンドを書かなくても、発見されたノードは `mdns-<prefix>` alias で `BackendCatalog` に自動登録されます。

### 仕組み

1. 起動時に `core/mdns/` が `_yu-ai._tcp.local.` を advertise
2. 他ノードの TXT record を購読し、必須キー (version/node_id/llm_base_url) が揃っていることを確認
3. メジャーバージョンが一致するノードに対して `http://<addr>:<web_port>/api/mdns/identity` を HTTP GET し、product/node_id/version が一致することを確認
4. 確認を通過したノードを `BackendInfo(alias="mdns-<node_id[:8]>")` として LLM Router に登録
5. 以降は既存の probe loop が定期リフレッシュ

### 前提条件

- OS の mDNS responder が動いていること (macOS: Bonjour、Linux: Avahi、Windows: mDNSResponder)
- ノードが同一 L2 サブネットに属していること (ルーター越え・VPN 越しでは Phase A の手動 config を使う)
- UDP 5353 がローカルファイアウォールで許可されていること
- **Ollama を LAN 公開すること** — Ollama はデフォルトで `127.0.0.1:11434` に bind しているため、LAN の他ノードからは到達できません。`OLLAMA_HOST=0.0.0.0:11434` を環境変数に設定してから Ollama を起動してください (macOS は `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`、Linux は systemd unit / `.bashrc`、Windows はシステム環境変数)。設定されていない場合 yu_ai_manager は localhost only と判断して `llm_base_url` を advertise しません (起動ログに警告が出ます)

### Ollama 自動検出

`config.json` の `llm_router.backends` に localhost エントリが無い場合、yu_ai_manager は起動時に以下の順で Ollama を探します:

1. `http://<LAN_IP>:11434/api/tags` — LAN から到達可能な Ollama
2. `http://localhost:11434/api/tags` — 検出されても LAN advertise はしない (上の警告を出力)

LAN IP で 200 が返れば自動的に `llm_base_url` として TXT record に載せます。設定ゼロで Ollama 同居ノードを mDNS 参加させる用途を想定しています。非デフォルトポート (11435 等) や lmstudio / llamacpp は引き続き `config.json` への明示が必要です。

### `_ollama._tcp.local.` 独自広告 (v4.71.0 以降)

`yu_ai_manager` は local Ollama が **LAN reachable** と判定された場合、
既存の `_yu-ai._tcp.local.` に加えて `_ollama._tcp.local.` も独自広告します。

これにより、別ノードの `yu_ai_manager` は同居 Ollama を bare Ollama peer として
受信し、`LLM Router` に `mdns-<node_id[:8]>-ollama` alias で自動登録できます。

条件:

- `Ollama` が `http://<LAN_IP>:11434/api/tags` で到達可能
- loopback-only (`http://localhost:11434`) の場合は広告しない

実機確認:

- Windows 側 `yu + local Ollama` を Pi 側から観測し、
  `/api/mdns/peers` に `version="0"`, `web_port=0`, `llm_provider="ollama"` の
  peer が出ることを確認
- `LLM Router` では `mdns-<id>-ollama` alias 自動登録を確認

詳細は
[ollama_mdns_phasec_validation_2026-04-11.md](/O:/yu_ai_manager/docs/development/investigations/ollama_mdns_phasec_validation_2026-04-11.md)
を参照。

### `yu` 非同居 pure Ollama ノードの扱い (方針)

`yu_ai_manager` が起動していない pure bare Ollama ノード (例: 家族の mac に
Ollama だけ入れてある、NAS 上の Ollama コンテナ等) は **自動発見の対象外** です。
`Ollama` 本体が公式に `_ollama._tcp.local.` を advertise する機能を持たないため、
検出する手段が構造的にありません。

このようなノードを LLM Router から使う場合は、以下のいずれかで **手動設定** してください:

```json
{
  "llm_router": {
    "backends": [
      { "alias": "ollama-nas",    "base_url": "http://nas.local:11434/v1",     "type": "ollama" },
      { "alias": "ollama-family", "base_url": "http://192.168.1.42:11434/v1", "type": "ollama" }
    ]
  }
}
```

- `.local` ホスト名 (上述の「ノード自動発見 — `.local` ホスト名サポート」) が使える環境ならそれを推奨
- それ以外は固定 IP を直書き

#### 自動発見を採らない理由

設計検討時 (2026-04-11) に以下 3 案を比較し、(c) 手動設定案内を選択しました:

| 案 | 内容 | 採否 |
|---|---|---|
| (a) LAN 全体 `:11434` 起動時スキャン | 起動時にサブネット内を総当たり probe | **不採用** — ネットワーク負荷が大きく、企業 LAN / 多ホスト環境で迷惑、ポートスキャンと誤認される恐れ。edge-first 哲学に反する |
| (b) 外部 Ollama 広告デーモン常駐 | 各 Ollama ホストに yu 提供の軽量 advertiser を別途常駐 | **不採用** — 追加の常駐プロセスを要求するのは `yu_ai_manager` 本体を入れるのと同等の負担。pure bare の利点が消える |
| (c) 固定 IP / `.local` / 手動 backend 設定を案内 | `config.json` に手書き | **採用** — 追加実装ゼロ、動作が明示的、ユーザーが意図せぬスキャンに巻き込まれない |

将来的に Ollama 本体が `_ollama._tcp.local.` を公式 advertise するか、公式
service discovery 機構を追加した場合は、その時点で Phase D として自動発見
レイヤーを再検討します。

### 無効化

不要なネットワーク (Docker 隔離、企業 LAN、CI 等) では無効化できます:

- `config.json` に `"mdns": {"enabled": false}` を追加
- または環境変数 `YU_AI_MDNS_DISABLED=1` を設定

### 既知の挙動

- **マルチホーム環境 (Wi-Fi + 有線)**: デフォルト (`bind_address: null`) では両インターフェースで advertise され、`PeerInfo.addresses` に複数 IP が入ります。単一インターフェースに絞りたい場合は `"bind_address": "192.168.x.y"` を指定します。
- **alias 衝突**: `config.json` の backend で alias を `mdns-xxxxxxxx` 形式にしていた場合、手動 config が優先され mDNS 発見分はスキップされます。
- **サブネット越え**: mDNS はデフォルトで L2 ブロードキャストドメイン内のみで動作します。越境運用は Phase A の `.local` ホスト名指定を使ってください。
- **セキュリティ**: mDNS 自体は認証無しです。家庭内 LAN のような信頼された環境を想定しています。公衆 Wi-Fi や多人数 LAN では無効化を推奨。`/api/mdns/identity` の検証により、偶発的な誤認ノードや互換性のない古いバージョンの混入は防がれます。

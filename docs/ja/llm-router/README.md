# LLM Router

> 対象バージョン: v4.55.0 以降

## LLM Router とは

LLM Router は yu_ai_manager に内蔵された **OpenAI 互換 LLM プロキシ**です。  
Ollama / LM Studio / llama.cpp など複数のローカル LLM バックエンドを束ねて、  
Claude Code・Continue・Open WebUI などのクライアントに **単一エンドポイント** として提供します。

```
Claude Code / Continue / Open WebUI
          │  (OpenAI 互換 API)
          ▼
    yu_ai_manager
    ┌─────────────────────────────────────────┐
    │           LLM Router                   │
    │                                         │
    │  alias: "claude-opus-4-7" ──► large    │
    │  alias: "local-coder" ──► ollama-mac/…│
    │                                         │
    │  [BackendCatalog]                       │
    │   ollama-mac  ─── 192.168.1.10:11434   │
    │   ollama-pi5  ─── 192.168.1.20:11434   │
    │   mdns-win01  ─── 自動発見(mDNS)        │
    └─────────────────────────────────────────┘
```

### できること

| 機能 | 説明 |
|---|---|
| **複数バックエンドの束ね** | Ollama インスタンスを LAN 上の何台でも登録可 |
| **エイリアスで抽象化** | `"model": "fast"` で実際のモデル名を隠蔽 |
| **mDNS 自動発見** | 同一 LAN の yu_ai_manager ノードを設定なしで自動登録 |
| **Claude Code 連携** | Anthropic 互換 `/v1/messages` を実装。追加プロキシ不要 |
| **動的 disable/enable** | WebUI からバックエンドを即時切替。再起動不要 |
| **カテゴリルーティング** | `large` / `fast` / `vision` の仮想バックエンドで最適モデルを自動選択 |

---

## アーキテクチャ

```
クライアント (Claude Code / Continue 等)
    │
    │ POST /v1/chat/completions
    │ POST /v1/messages          ← Anthropic 互換
    │ GET  /v1/models
    ▼
BackendCatalog  ─── エイリアス解決 ──► バックエンド + モデル名
    │
    ├─ 手動登録バックエンド  (config.json に書いたもの)
    └─ mDNS 自動発見バックエンド  (alias: "mdns-<prefix>")
```

**リクエストの流れ:**

1. クライアントが `"model": "claude-opus-4-7"` でリクエスト
2. Router が `aliases` テーブルで `"claude-opus-4-7"` → `"large"` に解決
3. `large` カテゴリから有効なバックエンドを選択
4. 選択したバックエンドへリクエストをプロキシ
5. ストリームレスポンスをクライアントに中継

---

## ドキュメント一覧

| ドキュメント | 内容 |
|---|---|
| [セットアップ](setup.md) | config.json の書き方、Claude Code/Continue との連携、mDNS 設定 |
| [WebUI](webui.md) | `/llm-router` ダッシュボードの操作方法 |
| [Hailo 自動発見](hailo-auto-discovery.md) | Hailo NPU 搭載ピアの自動登録 |
| [ピア到達不能の対処](mdns-peer-unreachable.md) | mDNS で発見されたピアが `unreachable` になる場合 |

---

## Gateway との違い

| | LLM Router | Gateway |
|---|---|---|
| **対象** | LLM (Ollama 等) のみ | SD WebUI・ComfyUI・Ollama をまとめて |
| **認証境界** | ローカルは bypass 可。LAN 外は api_key | scope ベースの Bearer 認証を全バックエンドに |
| **エンドポイント** | `/v1/*` (OpenAI/Anthropic 互換) | `/v1/*`, `/sd/*`, `/comfy/*` |
| **主な用途** | AI コーディングツールのバックエンド | 外部クライアントに生成ツールを安全に公開 |

両機能は独立して動作します。LLM のみ使う場合は LLM Router だけで十分です。

---

## LAN Cowork との関係

[LAN Cowork](../lan-cowork/README.md) が有効になっていると、  
同一 LAN 上のピアが mDNS で自動発見され、LLM Router に  
`mdns-<node_id[:8]>` という alias で自動登録されます。  
設定なしでマルチノード LLM 環境が構成されます。

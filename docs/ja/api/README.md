# YU AI Manager API Reference

カスタム UI やスクリプトから YU AI Manager の全機能を利用するための REST API ドキュメントです。

> **注意**: このドキュメントは主要エンドポイントのみをカバーしています。  
> 全エンドポイントの一覧は **[all-endpoints.md](all-endpoints.md)** を参照してください（`scripts/gen_api_docs.py` で自動生成・629件）。

## 共通規約

### ベース URL

```
http://<host>:<port>
```

デフォルト: `http://127.0.0.1:5000`
テスト環境: `http://127.0.0.1:5100` (`config_test.json` 使用時)

### 認証

4 種類の認証方式をサポート:

| 方式 | 用途 | ヘッダ例 |
|------|------|----------|
| PIN 認証 | ブラウザセッション | Cookie: `session=...` |
| API Key | 機械間通信 | `Authorization: Bearer sk_...` |
| Trusted Proxy | リバースプロキシ背後 | `X-Remote-User: username` |
| LAN Share トークン | ゲストアクセス | URL パス `/s/<token>/...` |

`config_test.json` (PIN なし) で起動すれば認証スキップ可能。

### CSRF 保護

全 `POST` / `PUT` / `DELETE` の `/api/` エンドポイントに `X-Requested-With` ヘッダが必須:

```
X-Requested-With: XMLHttpRequest
```

**例外**: `Authorization: Bearer` ヘッダ付きの API Key リクエストは CSRF 不要。

### レートリミット

| ティア | 対象 | レート | バースト |
|--------|------|--------|----------|
| READ | 全 GET | 無制限 | - |
| WRITE | POST/PUT/DELETE (通常) | ~120 req/min | 30 |
| HEAVY | 類似検索, ハッシュ計算, AI 分析, スキャン | ~20 req/min | 5 |
| DESTRUCTIVE | purge, hard-delete, cache clear, config write | ~12 req/min | 3 |

429 レスポンスには `Retry-After` ヘッダが付与されます。

### レスポンス形式

**成功** (新規 API):
```json
{
  "ok": true,
  "error": null,
  "data": { ... }
}
```

**エラー**:
```json
{
  "ok": false,
  "error": "エラーメッセージ",
  "code": "ERROR_CODE",
  "detail": "詳細情報 (任意)"
}
```

一部のレガシー API は `{ "success": true, "message": "..." }` 形式を返します。

### ページネーション

**オフセットベース** (デフォルト):
```
GET /api/search?offset=0&limit=50
```

**カーソルベース** (大規模データセット向け):
```
GET /api/search?cursor=<opaque_token>&limit=50
```

レスポンスに `next_cursor` フィールドが含まれます。

### バッチ操作

バッチ API は最大 500 件の操作をサポート。部分成功あり:

```json
POST /api/ratings/batch-set
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 999, "rating": 3 }
  ]
}
```

## API カテゴリ

| ドキュメント | 内容 |
|--------------|------|
| [search.md](search.md) | 検索・サジェスト・グループ |
| [files.md](files.md) | ファイル詳細・サムネイル・メディア取得 |
| [scan.md](scan.md) | スキャン制御・スキャンルート管理 |
| [events.md](events.md) | SSE イベントストリーム |
| [theming.md](theming.md) | CSS 変数・テーマカスタマイズ |
| [source.md](source.md) | ソースコード参照 (MCP 向け読み取り専用) |
| [github.md](github.md) | GitHub Integration (アカウント管理・Issue・PR・通知・Discussion・Release) |
| [scheduler.md](scheduler.md) | タスクスケジューラ (ジョブ管理・実行履歴) |
| [ratings.md](ratings.md) | レーティング (設定・一括設定・取得・統計) |
| [favorites.md](favorites.md) | お気に入り (トグル・チェック・一覧) |
| [collections.md](collections.md) | コレクション (CRUD・並び替え・一括追加/削除・CSV エクスポート) |
| [tags.md](tags.md) | タグ (一括設定・サジェスト) |
| [sns.md](sns.md) | SNS 共有 & Bluesky モニター (投稿・通知・トリアージ・自動応答) |
| [hailo-remote-tagger.md](hailo-remote-tagger.md) | Hailo Remote Tagger (設定・単一/バッチタグ付け・タグ CRUD) |
| [tagger-servers.md](tagger-servers.md) | Tagger Server Registry (分散タグ推論クラスター・サーバー管理・バッチ実行) |
| [svg.md](svg.md) | SVG ラスタライズ (SVG→PNG/WebP 変換・img2img パイプライン対応) |
| [settings.md](settings.md) | 設定管理 (スキーマ・値の取得/更新・シークレット暗号化・1Password/Bitwarden 連携) |
| [extensions.md](extensions.md) | Extension 管理 (一覧・有効化・設定・インストール・セキュリティ・マーケットプレイス・オーサリング) |
| [analysis.md](analysis.md) | AI 分析 (設定・単体/バッチ分析・トレンド分析・統計・サーバーレジストリ) |
| [system-update.md](system-update.md) | システムアップデート (バージョン確認・更新適用・統合アップデートマネージャー) |
| [tools.md](tools.md) | ツール (重複検出・ハッシュ計算・類似検索・キャッシュ管理・バックアップ・アーカイブクリーンアップ・デバッグログ) |
| [agent.md](agent.md) | Agent Safety Gateway (Kill Switch・Circuit Breaker・Budget・Approval・Scope Fence・Undo・異常検知) |
| [profiles.md](profiles.md) | プロファイル管理 (CRUD・複製・QR エクスポート/インポート) |
| [wd-tagger.md](wd-tagger.md) | WD-Tagger (Danbooru 自動タグ付け・モデル管理・VLM・XMP) |
| [ocr.md](ocr.md) | OCR (テキスト認識・翻訳・動画/PDF 対応・ベンチマーク・プロファイル) |
| [apikeys.md](apikeys.md) | API Key 管理 (作成・一覧・スコープ・失効) |
| [debug.md](debug.md) | デバッグ (メタデータ検査・SQL クエリ・モデル検証) |
| [ui.md](ui.md) | UI 管理 (一覧・切り替え・インストール・アンインストール) |
| [video-analysis.md](video-analysis.md) | 動画分析 (設定・ステータス・キーフレーム抽出) |

## クイックスタート (curl)

```bash
# 検索 (PIN なし環境)
curl "http://localhost:5100/api/search?q=landscape&limit=10"

# サムネイル取得
curl "http://localhost:5100/api/thumbnail/42" -o thumb.webp

# API Key で検索
curl -H "Authorization: Bearer sk_your_key_here" \
     "http://localhost:5100/api/search?q=portrait"

# レーティング設定
curl -X POST "http://localhost:5100/api/ratings/set" \
     -H "X-Requested-With: XMLHttpRequest" \
     -H "Content-Type: application/json" \
     -d '{"file_id": 42, "rating": 5}'
```

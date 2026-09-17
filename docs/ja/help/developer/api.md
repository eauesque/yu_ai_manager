# API 概要

YU AI Manager は REST API を提供しており、全ての WebUI 操作をプログラムから実行できます。
320 以上のエンドポイントがあり、画像管理から AI 分析まで幅広い操作に対応しています。

> **Tip**: 詳細な共通規約（認証・CSRF・レート制限・レスポンス形式）は「API リファレンス」セクションを参照してください。
>
> **重要**: endpoint を追加・変更する場合は「API セキュリティ指針」も必ず参照してください。

## 認証

4 種類の認証方式に対応しています。

| 方式 | 用途 | ヘッダ/パラメータ |
|------|------|-------------------|
| PIN 認証 | ブラウザセッション | `/_pin` でログイン → セッション cookie |
| API Key | 機械間通信・MCP | `Authorization: Bearer sk_xxxx` |
| Trusted Proxy | リバースプロキシ | `X-Remote-User` ヘッダ |
| LAN Share トークン | ゲストアクセス | `/s/<token>` パス |

### curl でのテスト例

```bash
# API Key 認証（CSRF ヘッダ不要）
curl -H "Authorization: Bearer sk_your_key" \
     http://localhost:5000/api/search?tags=1girl

# PIN 認証環境では 2 ステップ必要
# 1. CSRF トークン取得
curl -c cookies.txt http://localhost:5000/_pin
# 2. PIN 送信
curl -b cookies.txt -X POST \
     -H "X-Requested-With: XMLHttpRequest" \
     -d "pin=1234" http://localhost:5000/_pin_check
```

### CSRF 保護

全 POST/PUT/DELETE の `/api/` エンドポイントに `X-Requested-With` ヘッダが必須です。
Bearer API Key リクエストでは不要です。

## 主要エンドポイント

### 画像検索・閲覧

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/search` | タグ・日付・評価等でフィルター検索 |
| GET | `/api/search-grouped` | フォルダ/ZIP 別にグループ化検索 |
| GET | `/api/file/<id>` | 画像の詳細メタデータ取得 |
| GET | `/api/thumbnail/<id>` | サムネイル取得（WebP, ETag キャッシュ） |
| GET | `/api/original/<id>` | 元画像取得（Range リクエスト対応） |
| GET | `/api/suggest` | タグ補完候補 |

### 評価・タグ・アノテーション

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/api/ratings/batch-set` | 評価の一括設定 |
| POST | `/api/tags/batch-set` | タグの一括編集 |
| POST | `/api/annotations/batch-set` | アノテーションの一括設定 |
| GET | `/api/annotations/<id>` | アノテーション取得 |
| GET | `/api/annotations/search` | アノテーション検索 |

### コレクション

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/collections` | コレクション一覧 |
| POST | `/api/collections` | コレクション作成 |
| PUT | `/api/collections/<id>` | コレクション名変更 |
| DELETE | `/api/collections/<id>` | コレクション削除 |
| POST | `/api/collections/<id>/batch-add` | ファイル一括追加 |
| POST | `/api/collections/<id>/batch-remove` | ファイル一括削除 |

### スキャン

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/api/scan/start` | スキャン開始 |
| GET | `/api/scan/status` | スキャン進捗取得 |
| POST | `/api/scan/cancel` | スキャンキャンセル |
| POST | `/api/scan/resume` | 中断スキャン再開 |
| GET | `/api/scan-roots` | スキャンルート一覧 |
| POST | `/api/scan-roots` | スキャンルート追加 |

### AI 分析

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/api/analysis/analyze/<id>` | AI 画像分析実行 |
| GET | `/api/analysis/result/<id>` | 分析結果取得 |
| POST | `/api/analysis/batch` | バッチ分析 |
| POST | `/api/wd-tagger/tag/<id>` | WD-Tagger 推論 |
| POST | `/api/wd-tagger/batch` | WD-Tagger バッチ推論 |
| POST | `/api/analysis/batch/cancel` | AI分析バッチキャンセル |
| POST | `/api/wd-tagger/batch/cancel` | WD-Taggerバッチキャンセル |
| POST | `/api/tagger-servers/batch/cancel` | タガークラスターバッチキャンセル |
| POST | `/api/ocr/<id>` | OCR 実行 |

### 設定

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/settings/schema` | 設定スキーマ取得 |
| GET | `/api/settings/all` | 全設定値取得 |
| GET | `/api/settings/<key>` | 設定値取得 |
| PUT | `/api/settings/<key>` | 設定値更新 |

### Extension 管理

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/extensions` | Extension 一覧 |
| POST | `/api/extensions/<name>/toggle` | 有効/無効切替 |
| POST | `/api/extensions/install` | Git リポジトリからインストール |
| DELETE | `/api/extensions/<name>/uninstall` | アンインストール |

### エージェント安全機構

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/api/agent/kill` | Kill Switch 有効化 |
| POST | `/api/agent/resume` | Kill Switch 解除 |
| GET | `/api/agent/status` | 安全機構ステータス |
| GET | `/api/agent/journal` | 操作ジャーナル |
| POST | `/api/agent/undo/<journal_id>` | 操作取り消し |

## レスポンス形式

全 API は統一された JSON 形式で応答します。

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

エラー時:

```json
{
  "ok": false,
  "data": null,
  "error": "エラーメッセージ"
}
```

## レート制限

3 ティアのトークンバケット方式です。

| ティア | 対象 | 上限 | バースト |
|--------|------|------|---------|
| READ | 全 GET リクエスト | 無制限 | - |
| WRITE | POST/PUT/DELETE | ~120 req/min | 30 |
| HEAVY | 類似検索, AI 分析, スキャン | ~20 req/min | 5 |
| DESTRUCTIVE | purge, hard-delete, config 書き込み | ~12 req/min | 3 |

超過時は HTTP 429 が返ります。`Retry-After` ヘッダでリトライ待機秒数を確認できます。

## SSE (Server-Sent Events)

リアルタイムイベントは `/api/events/stream` から SSE で配信されます。
詳細は「SSE イベント」セクションを参照してください。

> **Note**: IP あたり最大 10 同時接続。アップロードサイズ上限は 100 MB です。

## 内部設計ドキュメント

API 設計の詳細な判断理由、SQLite パフォーマンス最適化、DB スキーマ設計などの開発知見は [MD Viewer](/ext/md-viewer/) で閲覧できます。

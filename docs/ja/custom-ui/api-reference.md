# API Reference — カスタム UI 開発者向けリンク集

カスタム UI 開発で参照する API ドキュメントへのリンク集と、よく使う API の早見表です。

## ドキュメント一覧

### 共通規約

- [API 共通規約](../api/README.md) — ベース URL、認証 (4 方式)、CSRF 保護、レートリミット、レスポンス形式、ページネーション

### エンドポイント別

- [検索 API](../api/search.md) — GET /api/search, サジェスト, グループ, server-info
- [ファイル API](../api/files.md) — ファイル詳細, サムネイル, オリジナル, プロンプト変換
- [スキャン API](../api/scan.md) — スキャン制御, スキャンルート管理, ハッシュバックフィル
- [イベント API](../api/events.md) — SSE リアルタイムイベント, ログストリーム

### テーマ

- [CSS 変数一覧](../api/theming.md) — テーマカスタムプロパティ (Light/Dark)

## よく使う API 早見表

### 読み取り (GET, 認証不要*)

| エンドポイント | 用途 | 主要パラメータ |
|--------------|------|---------------|
| `/api/search` | ファイル検索 | `q`, `sort`, `limit`, `cursor`, `rating_min`, `collection_id` |
| `/api/thumbnail/<id>` | サムネイル画像 (WebP) | `size` (default 300) |
| `/api/original/<id>` | オリジナルファイル | Range 対応 |
| `/api/file/<id>` | ファイル詳細 | — |
| `/api/suggest` | タグサジェスト | `q`, `limit` |
| `/api/stats/all` | 統計情報 | — |
| `/api/collections` | コレクション一覧 | — |
| `/api/server-info` | サーバー情報 | — |
| `/api/events/stream` | SSE ストリーム | `types` |

*PIN なし環境、またはセッション認証済みの場合

### 書き込み (POST, `X-Requested-With` ヘッダ必須)

| エンドポイント | 用途 | ボディ例 |
|--------------|------|---------|
| `/api/ratings/set` | レーティング設定 | `{file_id: 42, rating: 5}` |
| `/api/ratings/batch-set` | レーティング一括 | `{items: [{file_id, rating}, ...]}` |
| `/api/favorites/add` | お気に入り追加 | `{file_id: 42}` |
| `/api/favorites/remove` | お気に入り削除 | `{file_id: 42}` |
| `/api/tags/batch-set` | タグ一括操作 | `{items: [{file_id, add: [], remove: []}]}` |
| `/api/collections` | コレクション作成 | `{name: "My Collection"}` |
| `/api/collections/<id>/batch-add` | コレクションに追加 | `{file_ids: [1, 2, 3]}` |
| `/api/scan-all` | スキャン開始 | `{}` |
| `/api/convert` | プロンプト変換 | `{prompt, direction}` |

### UI 管理

| エンドポイント | メソッド | 用途 |
|--------------|---------|------|
| `/api/ui/list` | GET | UI 一覧 |
| `/api/ui/switch` | POST | UI 切り替え |
| `/api/ui/install` | POST | UI インストール (localhost のみ) |
| `/api/ui/<name>/uninstall` | DELETE | UI アンインストール (localhost のみ) |

## レスポンス形式

### 検索結果

```javascript
{
  results: [
    {
      id: 42,
      path: "/images/00042.png",
      filename: "00042.png",
      width: 1024,
      height: 1536,
      meta_type: "a1111_png",   // a1111_png, novelai_v4_png, comfy_png, unknown
      model_name: "animagine-xl-3.1",
      positive: "1girl, landscape",
      rating: 4,                 // 0-5 (0 = unrated)
      is_favorite: true,
      tags: ["landscape", "sunset"]
    }
  ],
  total: 1500,
  next_cursor: "base64token..."  // null = 最終ページ
}
```

### サムネイル

```
GET /api/thumbnail/42
→ Content-Type: image/webp
→ ETag: "abc123"
→ Cache-Control: max-age=86400
```

ブラウザが自動的にキャッシュします。`<img>` タグで直接参照可能:

```html
<img src="/api/thumbnail/42" loading="lazy" alt="thumbnail">
```

### エラーレスポンス

```javascript
{
  ok: false,
  error: "Rate limit exceeded",
  code: "RATE_LIMIT",      // 任意
  detail: "Retry after 5s"  // 任意
}
```

## CSRF ヘッダの注意

```javascript
// 共通ヘッダヘルパー
const API_HEADERS = {
  'Content-Type': 'application/json',
  'X-Requested-With': 'XMLHttpRequest',
};

// GET: ヘッダ不要
fetch('/api/search?q=test');

// POST: X-Requested-With 必須
fetch('/api/ratings/set', {
  method: 'POST',
  headers: API_HEADERS,
  body: JSON.stringify({ file_id: 42, rating: 5 }),
});
```

# UI Management API

UI (ユーザーインターフェース) テーマの一覧取得・切り替え・インストール・アンインストールに関する API。

## GET /api/ui/list

インストール済みの全 UI の一覧を取得。各 UI のマニフェスト情報、アクティブ状態、テンプレート・静的ファイルの有無を返す。

### パラメータ

なし

### レスポンス

```json
{
  "data": {
    "uis": [
      {
        "name": "default",
        "active": true,
        "manifest": {
          "name": "Default UI",
          "version": "1.0.0",
          "description": "Built-in reference UI"
        },
        "has_templates": true,
        "has_static": true
      },
      {
        "name": "custom-dark",
        "active": false,
        "manifest": {
          "name": "Custom Dark",
          "version": "0.2.0",
          "description": "Dark theme variant"
        },
        "has_templates": true,
        "has_static": true
      }
    ]
  }
}
```

| フィールド | 型 | 説明 |
|-----------|------|------|
| `name` | string | UI のディレクトリ名 |
| `active` | boolean | 現在アクティブな UI かどうか |
| `manifest` | object | `manifest.json` の内容 |
| `has_templates` | boolean | `templates/` ディレクトリが存在するか |
| `has_static` | boolean | `static/` ディレクトリが存在するか |

## POST /api/ui/switch

アクティブな UI を切り替える。変更は `config.json` に保存され、反映にはサーバーの再起動が必要。

### レート制限

WRITE

### リクエスト

```json
{
  "name": "custom-dark"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `name` | string | はい | 切り替え先の UI 名。英数字・ハイフン・アンダースコアのみ使用可 |

### レスポンス

```json
{
  "name": "custom-dark",
  "restart_required": true
}
```

### エラー

| ステータス | 条件 |
|-----------|------|
| 400 | UI 名が空、または不正な文字を含む |
| 404 | 指定した UI が存在しない |
| 400 | `manifest.json` が存在しない、または無効 |
| 500 | `config.json` の保存に失敗 |

## POST /api/ui/install

URL から UI をインストールする。**localhost からのリクエストのみ許可。**

### レート制限

WRITE

### 認証

PIN 認証またはAPI Key 認証に加え、localhost からのアクセスが必須。リモートからのリクエストは 403 で拒否される。

### リクエスト

```json
{
  "url": "https://github.com/user/my-ui/archive/refs/heads/main.zip"
}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|------|------|------|
| `url` | string | はい | UI パッケージの URL (zip アーカイブ等) |

### レスポンス

```json
{
  "name": "my-ui",
  "installed": true
}
```

### エラー

| ステータス | 条件 |
|-----------|------|
| 400 | URL が空 |
| 403 | localhost 以外からのリクエスト |

## DELETE /api/ui/<name>/uninstall

UI をアンインストールする。**localhost からのリクエストのみ許可。** デフォルト UI (`default`) は削除できない。

アンインストール対象がアクティブ UI の場合、`config.json` の UI 設定がリセットされデフォルト UI に戻る。

### レート制限

WRITE

### 認証

PIN 認証または API Key 認証に加え、localhost からのアクセスが必須。リモートからのリクエストは 403 で拒否される。

### パラメータ

| パラメータ | 型 | 説明 |
|-----------|------|------|
| `name` | string | UI 名 (パスパラメータ)。英数字・ハイフン・アンダースコアのみ |

### レスポンス

```json
{
  "name": "custom-dark",
  "uninstalled": true
}
```

### エラー

| ステータス | 条件 |
|-----------|------|
| 400 | UI 名が不正、または `default` を削除しようとした |
| 403 | localhost 以外からのリクエスト |
| 404 | 指定した UI が存在しない |

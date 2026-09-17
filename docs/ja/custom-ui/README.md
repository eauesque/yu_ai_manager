# Custom UI Development Guide

YU AI Manager のフロントエンドを完全に差し替え可能にするカスタム UI システムのガイドです。

## 目次

- [概要](#概要)
- [アーキテクチャ](#アーキテクチャ)
- [始め方](quickstart.md) — 最小構成 UI の作成手順
- [デザインガイド](design-guide.md) — CSS 設計・テーマ・レスポンシブ・コンポーネント
- [テンプレートガイド](templates.md) — Jinja2 パターン・i18n・ページ構造
- [高度な機能](advanced.md) — SSE リアルタイム更新・バッチ操作・セキュリティ
- [API リファレンス](api-reference.md) — 全 API ドキュメントへのリンク集

## 概要

YU AI Manager はバックエンド API が完全に分離されており、フロントエンドを自由に差し替えできます。
カスタム UI は `ui/<name>/` ディレクトリに配置するだけで有効化されます。

### このシステムでできること

- **フル UI 差し替え**: 検索画面・統計画面・設定画面等すべてのページを独自デザインに
- **テーマカスタマイズ**: CSS 変数の上書きだけでカラースキームを変更
- **部分的な差し替え**: 必要なページだけカスタムし、残りはデフォルト UI を使用
- **AI によるUI生成**: Claude や ChatGPT に API ドキュメントを渡して UI を自動生成

### アーキテクチャ

```
yu_ai_manager/
├── ui/
│   ├── default/              # リファレンス UI (built-in)
│   │   ├── manifest.json     # UI メタデータ (必須)
│   │   ├── templates/        # Jinja2 HTML テンプレート
│   │   │   ├── index.html    # メイン検索ページ
│   │   │   ├── stats.html    # 統計ダッシュボード
│   │   │   ├── tools.html    # ツールページ
│   │   │   ├── settings.html # 設定ページ
│   │   │   ├── story.html    # Your Story ページ
│   │   │   ├── inspect.html  # メタデータ検査
│   │   │   └── _nav.html     # 共通ナビバー (include)
│   │   └── static/           # CSS, JS, images
│   │       ├── css/          # スタイルシート
│   │       ├── dist/         # TypeScript ビルド出力
│   │       └── favicon.svg   # ファビコン
│   ├── custom/               # カスタム UI (gitignored, 自動検出)
│   │   ├── manifest.json
│   │   ├── templates/
│   │   └── static/
│   └── my-theme/             # 追加の UI (名前自由)
│       ├── manifest.json
│       └── ...
├── routes/                   # サーバーサイド API ルート
│   ├── pages.py              # ページルーティング定義
│   └── ...                   # 各種 API エンドポイント
└── docs/api/                 # API ドキュメント
```

### UI 解決順序

サーバー起動時に以下の優先順位で使用する UI を決定します:

| 優先度 | 条件 | 動作 |
|--------|------|------|
| 1 | `config.json` に `"ui": "my-theme"` を設定 | 指定された `ui/my-theme/` を使用 |
| 2 | `ui/custom/` に有効な `manifest.json` がある | `ui/custom/` を自動検出して使用 |
| 3 | 上記のいずれもない | `ui/default/` をフォールバック使用 |

### manifest.json

すべてのカスタム UI には `manifest.json` が必須です:

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "My custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `name` | Yes | UI の識別名 (ディレクトリ名と一致推奨) |
| `version` | Yes | セマンティックバージョン |
| `description` | No | UI の説明 |
| `author` | No | 作成者名 |
| `api_version` | No | 対応する API バージョン (`"1"`) |
| `type` | No | `"full"` (デフォルト) または `"theme"` |

### 静的ファイルの配信

カスタム UI の `static/` ディレクトリが Flask の `/static/` URL にマッピングされます:

```
ui/custom/static/style.css  →  /static/style.css
ui/custom/static/js/app.js  →  /static/js/app.js
ui/custom/static/img/logo.png  →  /static/img/logo.png
```

HTML からの参照:
```html
<link rel="stylesheet" href="/static/style.css">
<script src="/static/js/app.js"></script>
<img src="/static/img/logo.png">
```

### UI 管理 API

Settings ページの「UI」タブまたは API から UI の管理が可能です:

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/ui/list` | インストール済み UI 一覧 |
| POST | `/api/ui/switch` | アクティブ UI 切り替え (要再起動) |
| POST | `/api/ui/install` | URL から UI をインストール (localhost のみ) |
| DELETE | `/api/ui/<name>/uninstall` | UI をアンインストール (localhost のみ) |

### MCP ツール

MCP (Model Context Protocol) 経由でも UI を管理できます:

- `list_uis()` — インストール済み UI 一覧
- `switch_ui(name)` — アクティブ UI 切り替え
- `install_ui(url)` — URL から UI をインストール
- `uninstall_ui(name)` — UI をアンインストール

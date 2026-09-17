# プラグイン開発ガイド

YU AI Manager のプラグイン (Extension) を開発するためのガイドです。

## 最小構成

プラグインは `extensions/` ディレクトリ配下にフォルダを作成し、以下の 2 ファイルを用意するだけで動作します。

```
extensions/
  my-plugin/
    extension.json      # マニフェスト (必須)
    my_plugin.py        # エントリポイント (必須)
```

### extension.json (最小)

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My first plugin",
  "entry": "my_plugin.py",
  "config": {
    "enabled": true,
    "priority": 500
  }
}
```

### my_plugin.py (最小)

```python
"""My Plugin — 最小構成サンプル"""

from quart import Blueprint

bp = Blueprint("my_plugin", __name__)

def get_blueprint():
    """Extension ローダーが呼び出すエントリポイント。"""
    return bp
```

`get_blueprint()` を公開するだけで、Extension システムが自動的にブループリントを登録します。

## API ルート追加

プラグインから独自の API エンドポイントを追加できます。

```python
from quart import Blueprint, jsonify

bp = Blueprint("my_plugin", __name__)

@bp.route("/ext/my-plugin/api/hello")
def api_hello():
    return jsonify({"message": "Hello from my-plugin!"})

def get_blueprint():
    return bp
```

- URL プレフィックスは `/ext/<plugin-name>/` を推奨 (衝突防止)
- `extension.json` に `"blueprint_prefix": "/ext/my-plugin"` を設定すると、ナビゲーションに自動追加されます

## テンプレート (UI ページ)

プラグインは独自の HTML ページを持てます。

```
extensions/
  my-plugin/
    extension.json
    my_plugin.py
    templates/
      my_plugin/
        index.html
```

```python
from quart import Blueprint, render_template

bp = Blueprint(
    "my_plugin",
    __name__,
    template_folder="templates",
)

@bp.route("/ext/my-plugin/")
def index():
    return render_template("my_plugin/index.html")

def get_blueprint():
    return bp
```

テンプレートでは既存の `_nav.html` を extend して統一的な見た目にできます:

```html
{% extends "_nav.html" %}
{% block title %}My Plugin{% endblock %}
{% block content %}
<div class="container" style="padding:20px;">
  <h1>My Plugin</h1>
  <p>Your content here.</p>
</div>
{% endblock %}
```

## 設定スキーマ (config_schema)

ユーザーが Settings > Extensions からプラグイン設定を変更できるようにするには、`extension.json` に `config_schema` を定義します。

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "Configurable plugin",
  "entry": "my_plugin.py",
  "config": {
    "enabled": true,
    "priority": 500
  },
  "config_schema": {
    "greeting": { "type": "string", "default": "Hello" },
    "max_items": { "type": "number", "default": 10 },
    "verbose": { "type": "boolean", "default": false }
  }
}
```

Python 側で設定値を読むには:

```python
from core.extensions_core.extensions_admin import get_extension_config_value

greeting = get_extension_config_value("my-plugin", "greeting", "Hello")
```

## フック

Extension はフックポイントで処理を差し込めます。

```json
{
  "hooks": ["after_scan", "before_delete"]
}
```

フック関数は Python モジュール内に定義し、Extension Manager が自動検出します。

## ナビゲーション追加

`extension.json` に `nav` フィールドを追加すると、サイドバーにリンクが自動追加されます。

```json
{
  "nav": {
    "label": "My Plugin",
    "icon": "🔌"
  },
  "has_blueprint": true,
  "blueprint_prefix": "/ext/my-plugin"
}
```

## Git リポジトリでの公開

プラグインを Git リポジトリとして公開すると、ユーザーは Settings > Extensions > Install タブから URL を入力してインストールできます。

### リポジトリ構成

```
my-plugin/
  extension.json     # ルートに配置
  my_plugin.py
  templates/
  README.md
```

### インストールフロー

1. ユーザーが Settings > Extensions > Install に Git URL を入力
2. システムが `git clone --depth 1` でリポジトリをクローン
3. `extension.json` を検証
4. `extensions/` ディレクトリに配置
5. サーバー再起動で有効化

### マーケットプレイス登録

`config.json` の `extension_index_url` にインデックス JSON の URL を設定すると、マーケットプレイスタブからブラウズ・インストールできるようになります。

インデックス JSON の形式:

```json
[
  {
    "name": "my-plugin",
    "description": "A useful plugin",
    "author": "Your Name",
    "version": "1.0.0",
    "url": "https://github.com/user/my-plugin.git"
  }
]
```

## CSS プレフィックス規約

スタイルの衝突を防ぐため、CSS クラスにはプラグイン固有のプレフィックスを使用してください:

```css
.mp-container { ... }
.mp-card { ... }
```

## セキュリティ注意事項

- ユーザー入力を SQL に直接埋め込まないこと (`?` プレースホルダーを使用)
- ファイルパスのトラバーサル攻撃に注意
- 外部 API 呼び出し時は User-Agent を設定
- CSRF ヘッダ (`X-Requested-With`) は既存のグローバルインターセプターが自動注入します

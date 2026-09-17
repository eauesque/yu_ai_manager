# templates

Jinja テンプレートの入口。

## Entrypoints

- `index.html`
- `tools.html`
- `settings.html`
- `stats.html`
- `share.html`
- `inspect.html`
- `story.html`
- `extensions.html`

## Partial Convention

- 画面別サブディレクトリに `_content.html` / `_scripts.html` を置く
- `index/` と `tools/` は更に細分化された partial を持つ
- 追加実装時は「まず partial 化」を優先し、入口 html の肥大化を抑える

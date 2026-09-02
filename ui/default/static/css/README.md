# static/css

CSS assets grouped by feature.

## Root entry files (minimal)

- `main.css`: 全体アグリゲータ（各 feature dir を直接 `@import`）
- `search.css`: 設定ページなどの検索UI用エントリ
- `character-prompts.css`: Character prompts 用エントリ
- `dark-mode-fix-v2.css`: ダークモード補正エントリ
- `dark-mode-tags-enhanced.css`: ダークモードタグ視認性エントリ

## Feature dirs

- `base/`
- `search/`
- `modal/`
- `dock/`
- `widgets/`
- `keyboard/`
- `uxpatch/`
- `character/`
- `dark-mode/fix/`
- `dark-mode/tags/`
- `pages/`

## Rule

- root 直下は「テンプレートから直接読む入口CSS」のみに限定する。
- 実体スタイルは feature ディレクトリ側で編集する。

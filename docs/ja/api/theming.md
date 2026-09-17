# Theming — CSS Custom Properties

リファレンス UI (`ui/default/`) で使用している CSS カスタムプロパティの一覧です。
カスタム UI でこれらの変数を再定義することで、既存コンポーネントの見た目を変更できます。

ソース: `ui/default/static/css/base/base-theme.css`

## コア変数 (`:root` / `body.dark`)

| 変数 | Light | Dark | 用途 |
|------|-------|------|------|
| `--bg` | `#f5f6f8` | `#0f1115` | ページ背景 |
| `--card` | `#ffffff` | `#1b1f2a` | カード・パネル背景 |
| `--text` | `#222` | `#e7eaf0` | メインテキスト |
| `--muted` | `#666` | `#aab2c0` | サブテキスト・ヒント |
| `--border` | `#e6e6e6` | `#2b3240` | ボーダー・区切り線 |
| `--shadow` | `0 4px 14px rgba(0,0,0,0.08)` | `0 10px 26px rgba(0,0,0,0.45)` | カードシャドウ |
| `--btn-bg` | `#ffffff` | `#1b2030` | ボタン背景 |
| `--btn-text` | `#222` | `#e7eaf0` | ボタンテキスト |
| `--btn-hover` | `#f6f9ff` | `#222a3d` | ボタンホバー |
| `--tooltip-bg` | `rgba(0,0,0,0.85)` | `rgba(0,0,0,0.92)` | ツールチップ背景 |
| `--tooltip-text` | `#fff` | `#fff` | ツールチップテキスト |
| `--accent` | `#2563eb` | `#60a5fa` | アクセントカラー (リンク、ボタンハイライト) |

## ダークモード専用変数

### タグトークン

| 変数 | 値 | 用途 |
|------|-----|------|
| `--tag-bg` | `#4a4a4a` | タグ背景 |
| `--tag-text` | `#f0f0f0` | タグテキスト |
| `--tag-border` | `#666` | タグボーダー |
| `--tag-hover-bg` | `#5a5a5a` | タグホバー背景 |
| `--tag-hover-border` | `#888` | タグホバーボーダー |
| `--tag-focus-ring` | `#60a5fa` | タグフォーカスリング |

### タグカテゴリバリアント

| 変数 | 用途 |
|------|------|
| `--tag-ns-*` | 名前空間タグ (bg, border, text) |
| `--tag-wh-*` | ウェイト高タグ |
| `--tag-wl-*` | ウェイト低タグ |
| `--tag-we-*` | ウェイト強調タグ |

### ネガティブプロンプト

| 変数 | 値 | 用途 |
|------|-----|------|
| `--neg-prompt-bg` | `#2d2424` | ネガティブプロンプト背景 |
| `--neg-prompt-border` | `#fc8181` | ネガティブプロンプトボーダー |
| `--neg-heading` | `#fc8181` | ネガティブ見出し |

### アコーディオン

| 変数 | 値 | 用途 |
|------|-----|------|
| `--accordion-bg` | `#252525` | アコーディオン背景 |
| `--accordion-border` | `#3a3a3a` | アコーディオンボーダー |
| `--accordion-header-bg` | `#2a2a2a` | ヘッダー背景 |
| `--accordion-header-text` | `#e0e0e0` | ヘッダーテキスト |

## テーマクラス

| クラス | 説明 |
|--------|------|
| `body.dark` | ダークモード |
| `body.theme-retro` | レトロネオンテーマ (Konami code) |
| `body.theme-glow` | カスタムグローエフェクト |

## テーマ適用方法

カスタム UI でテーマを変更するには:

```css
/* カスタムテーマ例 */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --accent: #38bdf8;
  color-scheme: dark;
}
```

`body` 要素にクラスを追加することでテーマが適用されます。
ダークモードの `color-scheme: dark` は OS のフォームコントロールの配色に影響します。

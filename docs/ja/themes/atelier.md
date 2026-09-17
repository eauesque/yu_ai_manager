# Atelier System (γ)

yu_ai_manager のフロントエンドに導入された **Atelier System** は、エディトリアル × リファインド × ブルータリスト・ハイブリッドの visual identity デザインシステムです。

## ブランド階層

**eauesque** (プロダクトブランド) > **yu_ai_manager** (アプリ) > **Atelier System** (デザインシステム名)

Atelier System は Material / Fluent と同列のデザインシステム名で、eauesque プロダクトブランドの下層に位置付きます。

## 採用方式: opt-in 追加テーマ

既存の light / dark / theme-retro / theme-glow テーマは破壊しません。Atelier テーマは `body.theme-atelier-light` / `body.theme-atelier-dark` クラスを **追加** することで適用される opt-in 方式です。

- **新規ユーザー**: デフォルトで Atelier light / dark (システムの prefers-color-scheme に従う)
- **既存ユーザー**: 設定保持 (撤退路あり、いつでも legacy へ戻せる)

設定 → Misc → "Atelier テーマ" セレクトで切り替え。

## 3 書体ハイブリッド

| 役割 | フォント | 説明 |
|---|---|---|
| display + body | **Fraunces** Variable | opsz/wght 軸で h1=96 / h2=48 / h3=24 / body=14 / eyebrow=11 を実描画サイズに合わせて切替 |
| UI sans | **Inter** Variable | ナビ・ボタン・ラベル・eyebrow |
| data mono | **JetBrains Mono** Variable | prompt syntax (重み・LoRA・embed)、メタデータ値 |

すべて self-hosted (Latin Extended にサブセット化)。Fraunces 176K / Inter 148K / JetBrains Mono 52K。SIL Open Font License v1.1。

`scripts/build_atelier_fonts.py` で再生成可能。

## 二本立て accent

| トークン | 用途 | 値 (light / dark) |
|---|---|---|
| `--accent-warm` | 装飾・雰囲気・お気に入り | `#c9a063` / `#d4a96e` |
| `--accent-tool` | アクション・focus outline・active 状態 | `#2f5c8a` / `#5a8fc5` |

意味的に分離することで「装飾」と「操作」が一目で判別可能になります。

## --canvas (画像エリア専用 neutral grey)

AI 生成画像の色知覚を歪めないよう、画像が表示されるエリア (モーダル画像エリア・サムネイルグリッド) は warm chrome から分離した **neutral grey** トークンを使用：

- `--canvas`: `#d4d4d2` (light) / `#1a1a1a` (dark)
- `--canvas-raised`: `#c8c8c6` (light) / `#222222` (dark)

UI chrome 部分 (`--bg`, `--surface`, `--surface-raised`) は暖色系 (warm tan) を保ちます。

## WCAG コントラスト検証

8 ペア × light/dark = 16 ケースを `tests/test_atelier_wcag.py` で自動検証。本文 4.5:1、付随 (focus outline・eyebrow) 3:1 を保証。

```
uv run pytest tests/test_atelier_wcag.py
```

## モーダル設計

- 画像エリア: `--canvas`
- 情報パネル: `--surface-raised` + Fraunces roman (italic 不使用)
- prompt body: Fraunces roman、syntax `(...:1.2)` `<lora:...>` は inline JetBrains Mono
- toolbar (v4.126.2 円形ピル): glass + accent-tool active
- close / nav arrow / fav-btn: glass + accent-tool focus outline
- お気に入り active: warm accent (装飾的、tool blue とは分離)

## ヘッダーロゴ

2 段構成:
- 1 段目: `yu` (Fraunces 22pt)
- 2 段目: `eauesque` (JetBrains Mono 9pt 署名)

ブランド階層を視覚化するための editorial signature。既存 nav-brand を維持しつつ atelier 時のみ表示。

## ファイル構成

```
ui/default/static/css/atelier/
  atelier-tokens.css       # @font-face + body.theme-atelier-* + tokens
  atelier-components.css   # h1-h3, p, eyebrow, glass btn, prompt-syntax
  atelier-index.css        # 2 段ロゴ + サイドバー + grid + pill 検索
  atelier-modal.css        # モーダル全体 (canvas + glass + accent-tool)

ui/default/static/fonts/atelier/
  Fraunces-VariableFont.subset.woff2     # 176K
  Inter-VariableFont.subset.woff2        # 148K
  JetBrainsMono-VariableFont.subset.woff2 # 52K
  LICENSE.md                              # OFL v1.1
```

## アクセシビリティ

- `prefers-reduced-motion: reduce` で transform/animation を抑制 (opacity 遷移は維持)
- focus-visible はすべて `--accent-tool` 2px outline + 2px offset (WCAG 2.5.5 + 1.4.11)
- WCAG AA (本文 4.5:1, 付随 3:1) を 16 ペア自動検証

## 撤退路

問題が発生した場合は 設定 → "Atelier テーマ" → "Off" で legacy light/dark に即時戻せます。テーマ管理 (preset-*) も影響を受けません。

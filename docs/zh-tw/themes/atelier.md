# Atelier System (γ)

yu_ai_manager 前端引入的 **Atelier System** 是一套編輯設計 × 精緻 × 粗野主義混合的 visual identity 設計系統。

## 品牌階層

**eauesque** (產品品牌) > **yu_ai_manager** (應用程式) > **Atelier System** (設計系統名稱)

Atelier System 與 Material / Fluent 同列，位於 eauesque 產品品牌之下。

## 採用方式: opt-in 附加主題

既有 light / dark / theme-retro / theme-glow 主題不受影響。Atelier 採用 **附加** `body.theme-atelier-light` / `body.theme-atelier-dark` 類別的方式啟用 (opt-in)。

- **新使用者**: 預設為 Atelier 明亮 / 暗色 (依系統 `prefers-color-scheme`)
- **既有使用者**: 設定保留 (撤退路徑保留，可隨時返回 legacy)

切換: 設定 → Misc → "Atelier 主題"。

## 3 字型混合

| 用途 | 字型 | 說明 |
|---|---|---|
| display + body | **Fraunces** Variable | opsz/wght 軸控制 h1=96 / h2=48 / h3=24 / body=14 / eyebrow=11，光學尺寸對應實際渲染大小 |
| UI sans | **Inter** Variable | 導覽、按鈕、標籤、eyebrow |
| data mono | **JetBrains Mono** Variable | prompt 語法 (權重・LoRA・embed)、metadata 值 |

全部 self-hosted (Latin Extended 子集化)。Fraunces 176K / Inter 148K / JetBrains Mono 52K。SIL Open Font License v1.1。

可透過 `scripts/build_atelier_fonts.py` 重新生成。

## 雙軌 accent

| token | 用途 | 值 (light / dark) |
|---|---|---|
| `--accent-warm` | 裝飾、氛圍、收藏 | `#c9a063` / `#d4a96e` |
| `--accent-tool` | 操作、focus outline、active 狀態 | `#2f5c8a` / `#5a8fc5` |

語意分離後，「裝飾」與「操作」一目了然。

## --canvas (圖像區域專用 neutral grey)

為避免影響 AI 生成圖像的色彩感知，圖像顯示區 (modal 圖像區、縮圖網格) 使用與暖色 chrome 分離的 **中性灰** token：

- `--canvas`: `#d4d4d2` (light) / `#1a1a1a` (dark)
- `--canvas-raised`: `#c8c8c6` (light) / `#222222` (dark)

UI chrome (`--bg`, `--surface`, `--surface-raised`) 維持暖色系。

## WCAG 對比驗證

8 對 × light/dark = 16 案例由 `tests/test_atelier_wcag.py` 自動驗證。本文 4.5:1，附屬 (focus outline・eyebrow) 3:1。

```
uv run pytest tests/test_atelier_wcag.py
```

## Modal 設計

- 圖像區: `--canvas`
- 資訊面板: `--surface-raised` + Fraunces roman (不使用斜體)
- prompt 本文: Fraunces roman；syntax `(...:1.2)` `<lora:...>` 切換為 inline JetBrains Mono
- toolbar (v4.126.2 圓形 pill): glass + accent-tool active
- close / nav arrow / fav-btn: glass + accent-tool focus outline
- 收藏 active: warm accent (裝飾性，與 tool blue 分離)

## Header Logo

2 行構成:
- 第 1 行: `yu` (Fraunces 22pt)
- 第 2 行: `eauesque` (JetBrains Mono 9pt 簽名)

editorial signature，視覺化品牌階層。非 atelier 主題保留 legacy nav-brand。

## 檔案構成

```
ui/default/static/css/atelier/
  atelier-tokens.css       # @font-face + body.theme-atelier-* + tokens
  atelier-components.css   # h1-h3, p, eyebrow, glass btn, prompt-syntax
  atelier-index.css        # logo + sidebar + grid + pill 搜尋
  atelier-modal.css        # 完整 modal (canvas + glass + accent-tool)

ui/default/static/fonts/atelier/
  Fraunces-VariableFont.subset.woff2     # 176K
  Inter-VariableFont.subset.woff2        # 148K
  JetBrainsMono-VariableFont.subset.woff2 # 52K
  LICENSE.md                              # OFL v1.1
```

## 無障礙

- `prefers-reduced-motion: reduce` 抑制 transform/animation (保留 opacity 過渡)
- `:focus-visible` 全部使用 `--accent-tool` 2px outline + 2px offset (WCAG 2.5.5 + 1.4.11)
- WCAG AA (本文 4.5:1, 附屬 3:1) 已於 16 對驗證

## 撤退路徑

如出現問題，可由 設定 → "Atelier 主題" → "關閉" 立即回到 legacy light/dark。custom theme (preset-*) 不受影響。

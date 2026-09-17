# Atelier System (γ)

yu_ai_manager 前端引入的 **Atelier System** 是一套编辑设计 × 精致 × 粗野主义混合的 visual identity 设计系统。

## 品牌层级

**eauesque** (产品品牌) > **yu_ai_manager** (应用) > **Atelier System** (设计系统名称)

Atelier System 与 Material / Fluent 同级，位于 eauesque 产品品牌之下。

## 采用方式: opt-in 附加主题

既有 light / dark / theme-retro / theme-glow 主题不受影响。Atelier 采用 **附加** `body.theme-atelier-light` / `body.theme-atelier-dark` 类的方式启用 (opt-in)。

- **新用户**: 默认为 Atelier 明亮 / 暗色 (依系统 `prefers-color-scheme`)
- **既有用户**: 设置保留 (撤退路径保留，可随时返回 legacy)

切换: 设置 → Misc → "Atelier 主题"。

## 3 字体混合

| 用途 | 字体 | 说明 |
|---|---|---|
| display + body | **Fraunces** Variable | opsz/wght 轴控制 h1=96 / h2=48 / h3=24 / body=14 / eyebrow=11，光学尺寸对应实际渲染大小 |
| UI sans | **Inter** Variable | 导航、按钮、标签、eyebrow |
| data mono | **JetBrains Mono** Variable | prompt 语法 (权重・LoRA・embed)、metadata 值 |

全部 self-hosted (Latin Extended 子集化)。Fraunces 176K / Inter 148K / JetBrains Mono 52K。SIL Open Font License v1.1。

可通过 `scripts/build_atelier_fonts.py` 重新生成。

## 双轨 accent

| token | 用途 | 值 (light / dark) |
|---|---|---|
| `--accent-warm` | 装饰、氛围、收藏 | `#c9a063` / `#d4a96e` |
| `--accent-tool` | 操作、focus outline、active 状态 | `#2f5c8a` / `#5a8fc5` |

语义分离后，"装饰"与"操作"一目了然。

## --canvas (图像区域专用 neutral grey)

为避免影响 AI 生成图像的色彩感知，图像显示区 (modal 图像区、缩略图网格) 使用与暖色 chrome 分离的 **中性灰** token：

- `--canvas`: `#d4d4d2` (light) / `#1a1a1a` (dark)
- `--canvas-raised`: `#c8c8c6` (light) / `#222222` (dark)

UI chrome (`--bg`, `--surface`, `--surface-raised`) 维持暖色系。

## WCAG 对比验证

8 对 × light/dark = 16 案例由 `tests/test_atelier_wcag.py` 自动验证。本文 4.5:1，附属 (focus outline・eyebrow) 3:1。

```
uv run pytest tests/test_atelier_wcag.py
```

## Modal 设计

- 图像区: `--canvas`
- 信息面板: `--surface-raised` + Fraunces roman (不使用斜体)
- prompt 正文: Fraunces roman；syntax `(...:1.2)` `<lora:...>` 切换为 inline JetBrains Mono
- toolbar (v4.126.2 圆形 pill): glass + accent-tool active
- close / nav arrow / fav-btn: glass + accent-tool focus outline
- 收藏 active: warm accent (装饰性，与 tool blue 分离)

## Header Logo

2 行构成:
- 第 1 行: `yu` (Fraunces 22pt)
- 第 2 行: `eauesque` (JetBrains Mono 9pt 签名)

editorial signature，视觉化品牌层级。非 atelier 主题保留 legacy nav-brand。

## 文件构成

```
ui/default/static/css/atelier/
  atelier-tokens.css       # @font-face + body.theme-atelier-* + tokens
  atelier-components.css   # h1-h3, p, eyebrow, glass btn, prompt-syntax
  atelier-index.css        # logo + sidebar + grid + pill 搜索
  atelier-modal.css        # 完整 modal (canvas + glass + accent-tool)

ui/default/static/fonts/atelier/
  Fraunces-VariableFont.subset.woff2     # 176K
  Inter-VariableFont.subset.woff2        # 148K
  JetBrainsMono-VariableFont.subset.woff2 # 52K
  LICENSE.md                              # OFL v1.1
```

## 无障碍

- `prefers-reduced-motion: reduce` 抑制 transform/animation (保留 opacity 过渡)
- `:focus-visible` 全部使用 `--accent-tool` 2px outline + 2px offset (WCAG 2.5.5 + 1.4.11)
- WCAG AA (本文 4.5:1, 附属 3:1) 已于 16 对验证

## 撤退路径

如出现问题，可由 设置 → "Atelier 主题" → "关闭" 立即回到 legacy light/dark。custom theme (preset-*) 不受影响。

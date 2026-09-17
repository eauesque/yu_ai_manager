# Atelier System (γ)

**Atelier System** is the visual identity introduced to yu_ai_manager — an Editorial × Refined × Brutalist hybrid design language.

## Brand Hierarchy

**eauesque** (product brand) > **yu_ai_manager** (app) > **Atelier System** (design system name)

Atelier System sits at the same tier as Material / Fluent, layered under the eauesque product brand.

## Adoption Model: Opt-in Additive Theme

Existing themes (light / dark / theme-retro / theme-glow) are untouched. Atelier applies by **adding** `body.theme-atelier-light` or `body.theme-atelier-dark` — no destructive replacement.

- **New users**: default to Atelier light / dark (follows system `prefers-color-scheme`)
- **Returning users**: settings preserved; you can flip back to legacy at any time

Toggle via Settings → Misc → "Atelier Theme".

## Three-Font Hybrid

| Role | Font | Notes |
|---|---|---|
| Display + body | **Fraunces** Variable | opsz/wght axes drive h1=96 / h2=48 / h3=24 / body=14 / eyebrow=11 with optical-size matching the rendered size |
| UI sans | **Inter** Variable | Navigation, buttons, labels, eyebrow |
| Data mono | **JetBrains Mono** Variable | Prompt syntax (weights, LoRA, embeds), metadata values |

All self-hosted (Latin Extended subset). Fraunces 176K / Inter 148K / JetBrains Mono 52K. SIL Open Font License v1.1.

Regenerate via `scripts/build_atelier_fonts.py`.

## Two-Tier Accents

| Token | Purpose | Light / Dark |
|---|---|---|
| `--accent-warm` | Decorative, atmosphere, favorites | `#c9a063` / `#d4a96e` |
| `--accent-tool` | Action, focus outline, active state | `#2f5c8a` / `#5a8fc5` |

Splitting decoration from action makes UI affordances unambiguous at a glance.

## --canvas (image-area neutral grey)

AI image regions (modal image area, thumbnail grid) live on a **neutral grey canvas**, separated from warm UI chrome so image colour perception is not biased:

- `--canvas`: `#d4d4d2` (light) / `#1a1a1a` (dark)
- `--canvas-raised`: `#c8c8c6` (light) / `#222222` (dark)

Chrome (`--bg`, `--surface`, `--surface-raised`) keeps the warm-tan family.

## WCAG Contrast Verification

8 pairs × light/dark = 16 cases, asserted by `tests/test_atelier_wcag.py`. Body text 4.5:1, incidental (focus outline / eyebrow) 3:1.

```
uv run pytest tests/test_atelier_wcag.py
```

## Modal

- Image area: `--canvas`
- Info panel: `--surface-raised` + Fraunces roman (no italic)
- Prompt body: Fraunces roman; `(...:1.2)` and `<lora:...>` flip to inline JetBrains Mono
- Toolbar (v4.126.2 circular pills): glass + accent-tool active
- Close / nav arrow / fav button: glass + accent-tool focus outline
- Favorite active: warm accent (decorative, kept separate from tool blue)

## Header Logo

Two-line construction:
- Line 1: `yu` (Fraunces 22pt)
- Line 2: `eauesque` (JetBrains Mono 9pt signature)

An editorial signature that visualises the brand hierarchy. Legacy nav-brand stays in place for non-atelier themes.

## Files

```
ui/default/static/css/atelier/
  atelier-tokens.css       # @font-face + body.theme-atelier-* + tokens
  atelier-components.css   # h1-h3, p, eyebrow, glass btn, prompt-syntax
  atelier-index.css        # logo + sidebar + grid + pill search
  atelier-modal.css        # full modal (canvas + glass + accent-tool)

ui/default/static/fonts/atelier/
  Fraunces-VariableFont.subset.woff2     # 176K
  Inter-VariableFont.subset.woff2        # 148K
  JetBrainsMono-VariableFont.subset.woff2 # 52K
  LICENSE.md                              # OFL v1.1
```

## Accessibility

- `prefers-reduced-motion: reduce` cancels transform/animation (opacity transitions kept)
- `:focus-visible` everywhere uses `--accent-tool` 2px outline + 2px offset (WCAG 2.5.5 + 1.4.11)
- WCAG AA (4.5:1 body, 3:1 incidental) verified across 16 pairs

## Rollback Path

If something goes wrong, Settings → "Atelier Theme" → "Off" instantly restores legacy light/dark. Custom themes (preset-*) are unaffected.

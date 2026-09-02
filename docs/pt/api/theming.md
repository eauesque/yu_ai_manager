# Tema — Propriedades CSS Personalizadas

Esta é uma lista de propriedades CSS personalizadas usadas na UI de referência (`ui/default/`).
Uma UI personalizada pode sobrescrever a aparência dos componentes existentes redefinindo essas variáveis.

Fonte: `ui/default/static/css/base/base-theme.css`

## Variáveis Principais (`:root` / `body.dark`)

| Variável | Claro | Escuro | Propósito |
|----------|-------|------|---------|
| `--bg` | `#f5f6f8` | `#0f1115` | Background da página |
| `--card` | `#ffffff` | `#1b1f2a` | Background de card/painel |
| `--text` | `#222` | `#e7eaf0` | Texto principal |
| `--muted` | `#666` | `#aab2c0` | Subtext/dicas |
| `--border` | `#e6e6e6` | `#2b3240` | Bordas/divisores |
| `--shadow` | `0 4px 14px rgba(0,0,0,0.08)` | `0 10px 26px rgba(0,0,0,0.45)` | Sombra de card |
| `--btn-bg` | `#ffffff` | `#1b2030` | Background de botão |
| `--btn-text` | `#222` | `#e7eaf0` | Texto de botão |
| `--btn-hover` | `#f6f9ff` | `#222a3d` | Hover de botão |
| `--tooltip-bg` | `rgba(0,0,0,0.85)` | `rgba(0,0,0,0.92)` | Background de tooltip |
| `--tooltip-text` | `#fff` | `#fff` | Texto de tooltip |
| `--accent` | `#2563eb` | `#60a5fa` | Cor de acento (links, destaques de botão) |

## Variáveis de Modo Escuro

### Tokens de Tag

| Variável | Valor | Propósito |
|----------|-------|---------|
| `--tag-bg` | `#4a4a4a` | Background de tag |
| `--tag-text` | `#f0f0f0` | Texto de tag |
| `--tag-border` | `#666` | Borda de tag |
| `--tag-hover-bg` | `#5a5a5a` | Background de hover de tag |
| `--tag-hover-border` | `#888` | Borda de hover de tag |
| `--tag-focus-ring` | `#60a5fa` | Ring de foco de tag |

### Variantes de Categoria de Tag

| Variável | Propósito |
|----------|---------|
| `--tag-ns-*` | Tags de namespace (bg, border, text) |
| `--tag-wh-*` | Tags de alta ponderação |
| `--tag-wl-*` | Tags de baixa ponderação |
| `--tag-we-*` | Tags de ponderação enfatizada |

### Prompt Negativo

| Variável | Valor | Propósito |
|----------|-------|---------|
| `--neg-prompt-bg` | `#2d2424` | Background de prompt negativo |
| `--neg-prompt-border` | `#fc8181` | Borda de prompt negativo |
| `--neg-heading` | `#fc8181` | Título negativo |

### Accordion

| Variável | Valor | Propósito |
|----------|-------|---------|
| `--accordion-bg` | `#252525` | Background do accordion |
| `--accordion-border` | `#3a3a3a` | Borda do accordion |
| `--accordion-header-bg` | `#2a2a2a` | Background do header |
| `--accordion-header-text` | `#e0e0e0` | Texto do header |

## Classes de Tema

| Classe | Descrição |
|-------|-------------|
| `body.dark` | Modo escuro |
| `body.theme-retro` | Tema retrô neon (código Konami) |
| `body.theme-glow` | Efeito glow personalizado |

## Aplicando Temas

Para mudar o tema em uma UI personalizada:

```css
/* Exemplo de tema personalizado */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --accent: #38bdf8;
  color-scheme: dark;
}
```

O tema entra em efeito adicionando uma classe ao elemento `body`.
A propriedade `color-scheme: dark` no modo escuro afeta as cores de controle de formulário do SO.

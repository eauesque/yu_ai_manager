# Temas — Propiedades CSS Personalizadas

Esta es una lista de propiedades CSS personalizadas utilizadas en la UI de referencia (`ui/default/`).
Una UI personalizada puede anular la apariencia de componentes existentes redefiniendo estas variables.

Fuente: `ui/default/static/css/base/base-theme.css`

## Variables Principales (`:root` / `body.dark`)

| Variable | Claro | Oscuro | Propósito |
|----------|-------|------|---------|
| `--bg` | `#f5f6f8` | `#0f1115` | Fondo de página |
| `--card` | `#ffffff` | `#1b1f2a` | Fondo de tarjeta/panel |
| `--text` | `#222` | `#e7eaf0` | Texto principal |
| `--muted` | `#666` | `#aab2c0` | Subtexto/sugerencias |
| `--border` | `#e6e6e6` | `#2b3240` | Bordes/divisores |
| `--shadow` | `0 4px 14px rgba(0,0,0,0.08)` | `0 10px 26px rgba(0,0,0,0.45)` | Sombra de tarjeta |
| `--btn-bg` | `#ffffff` | `#1b2030` | Fondo de botón |
| `--btn-text` | `#222` | `#e7eaf0` | Texto de botón |
| `--btn-hover` | `#f6f9ff` | `#222a3d` | Hover de botón |
| `--tooltip-bg` | `rgba(0,0,0,0.85)` | `rgba(0,0,0,0.92)` | Fondo de tooltip |
| `--tooltip-text` | `#fff` | `#fff` | Texto de tooltip |
| `--accent` | `#2563eb` | `#60a5fa` | Color de énfasis (enlaces, destacados de botón) |

## Variables de Modo Oscuro

### Tokens de Etiqueta

| Variable | Valor | Propósito |
|----------|-------|---------|
| `--tag-bg` | `#4a4a4a` | Fondo de etiqueta |
| `--tag-text` | `#f0f0f0` | Texto de etiqueta |
| `--tag-border` | `#666` | Borde de etiqueta |
| `--tag-hover-bg` | `#5a5a5a` | Fondo hover de etiqueta |
| `--tag-hover-border` | `#888` | Borde hover de etiqueta |
| `--tag-focus-ring` | `#60a5fa` | Anillo de enfoque de etiqueta |

### Variantes de Categoría de Etiqueta

| Variable | Propósito |
|----------|---------|
| `--tag-ns-*` | Etiquetas de namespace (bg, border, text) |
| `--tag-wh-*` | Etiquetas de peso alto |
| `--tag-wl-*` | Etiquetas de peso bajo |
| `--tag-we-*` | Etiquetas de peso enfatizado |

### Prompt Negativo

| Variable | Valor | Propósito |
|----------|-------|---------|
| `--neg-prompt-bg` | `#2d2424` | Fondo de prompt negativo |
| `--neg-prompt-border` | `#fc8181` | Borde de prompt negativo |
| `--neg-heading` | `#fc8181` | Encabezado negativo |

### Acordeón

| Variable | Valor | Propósito |
|----------|-------|---------|
| `--accordion-bg` | `#252525` | Fondo de acordeón |
| `--accordion-border` | `#3a3a3a` | Borde de acordeón |
| `--accordion-header-bg` | `#2a2a2a` | Fondo de encabezado |
| `--accordion-header-text` | `#e0e0e0` | Texto de encabezado |

## Clases de Tema

| Clase | Descripción |
|-------|-------------|
| `body.dark` | Modo oscuro |
| `body.theme-retro` | Tema neón retro (código Konami) |
| `body.theme-glow` | Efecto de brillo personalizado |

## Aplicar Temas

Para cambiar el tema en una UI personalizada:

```css
/* Ejemplo de tema personalizado */
body.theme-ocean {
  --bg: #0a1628;
  --card: #132744;
  --text: #c8daf0;
  --accent: #38bdf8;
  color-scheme: dark;
}
```

El tema entra en vigor al agregar una clase al elemento `body`.
La propiedad `color-scheme: dark` en modo oscuro afecta los colores de control de formulario del sistema operativo.

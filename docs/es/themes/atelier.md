# Sistema Atelier (γ)

**Atelier System** es la identidad visual introducida en yu_ai_manager — un lenguaje de diseño híbrido Editorial × Refined × Brutalist.

## Jerarquía de marca

**eauesque** (marca de producto) > **yu_ai_manager** (aplicación) > **Atelier System** (nombre del sistema de diseño)

Atelier System está en el mismo nivel que Material / Fluent, organizado bajo la marca de producto eauesque.

## Modelo de adopción: tema aditivo opt-in

Los temas existentes (light / dark / theme-retro / theme-glow) no se modifican. Atelier se aplica **añadiendo** `body.theme-atelier-light` o `body.theme-atelier-dark` — sin reemplazo destructivo.

- **Nuevos usuarios**: predeterminado a Atelier light / dark (sigue `prefers-color-scheme` del sistema)
- **Usuarios que regresan**: configuración preservada; puede cambiar a legacy en cualquier momento

Alternar mediante Configuración → Misc → "Atelier Theme".

## Híbrido de tres fuentes

| Rol | Fuente | Notas |
|---|---|---|
| Display + body | **Fraunces** Variable | ejes opsz/wght impulsan h1=96 / h2=48 / h3=24 / body=14 / eyebrow=11 con coincidencia de tamaño óptico |
| UI sans | **Inter** Variable | Navegación, botones, etiquetas, eyebrow |
| Data mono | **JetBrains Mono** Variable | Sintaxis de prompt (pesos, LoRA, embeds), valores de metadatos |

Todos alojados localmente (subconjunto Latin Extended). Fraunces 176K / Inter 148K / JetBrains Mono 52K. Licencia SIL Open Font v1.1.

Regenerar mediante `scripts/build_atelier_fonts.py`.

## Acentos de dos niveles

| Token | Propósito | Light / Dark |
|---|---|---|
| `--accent-warm` | Decorativo, atmósfera, favoritos | `#c9a063` / `#d4a96e` |
| `--accent-tool` | Acción, contorno de enfoque, estado activo | `#2f5c8a` / `#5a8fc5` |

Separar decoración de acción hace que los affordances de UI sean inequívocos de un vistazo.

## --canvas (gris neutro del área de imagen)

Las regiones de imagen de IA (área de imagen modal, cuadrícula de miniaturas) viven en un **lienzo gris neutro**, separado del chrome de UI cálido para que la percepción del color de la imagen no esté sesgada:

- `--canvas`: `#d4d4d2` (light) / `#1a1a1a` (dark)
- `--canvas-raised`: `#c8c8c6` (light) / `#222222` (dark)

Chrome (`--bg`, `--surface`, `--surface-raised`) mantiene la familia cálida-beige.

## Verificación de contraste WCAG

8 pares × light/dark = 16 casos, afirmados por `tests/test_atelier_wcag.py`. Texto de cuerpo 4.5:1, incidental (contorno de enfoque / eyebrow) 3:1.

```
uv run pytest tests/test_atelier_wcag.py
```

## Modal

- Área de imagen: `--canvas`
- Panel de información: `--surface-raised` + Fraunces roman (sin cursiva)
- Cuerpo de prompt: Fraunces roman; `(...:1.2)` y `<lora:...>` cambian a JetBrains Mono en línea
- Barra de herramientas (v4.126.2 píldoras circulares): glass + accent-tool activo
- Cerrar / flecha de navegación / botón fav: glass + contorno de enfoque accent-tool
- Favorito activo: acento cálido (decorativo, mantiene separado del azul de herramientas)

## Logo de encabezado

Construcción de dos líneas:
- Línea 1: `yu` (Fraunces 22pt)
- Línea 2: `eauesque` (firma JetBrains Mono 9pt)

Una firma editorial que visualiza la jerarquía de marca. El nav-brand heredado permanece en su lugar para temas no-atelier.

## Archivos

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

## Accesibilidad

- `prefers-reduced-motion: reduce` cancela transform/animation (transiciones de opacidad mantienen)
- `:focus-visible` en todas partes usa `--accent-tool` contorno 2px + desplazamiento 2px (WCAG 2.5.5 + 1.4.11)
- WCAG AA (4.5:1 cuerpo, 3:1 incidental) verificado en 16 pares

## Ruta de reversión

Si algo sale mal, Configuración → "Atelier Theme" → "Off" restaura instantáneamente light/dark legacy. Los temas personalizados (preset-*) no se ven afectados.

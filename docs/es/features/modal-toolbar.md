# Barra de herramientas modal

La barra de herramientas unificada en la parte inferior del modal de detalles proporciona acceso a todos los controles principales durante la visualización de imágenes/videos.

## Estructura

### Barra primaria (siempre visible)

**Modo de imagen fija:**
- ☆ Favorito
- ⓘ Alternar panel de información
- ‹ › Anterior / Siguiente
- Zoom (− / 100% / +)
- Modo de ajuste (fit / fit-w / fit-h / fit-custom + altura / original)
- Spread 2P / dirección ↔ (cuando sea aplicable)
- ⛶ Inmersivo / ⤢ Pantalla completa
- 📁 Colección
- Bridge Enviar (Enviar prompt ▾ / Enviar imagen ▾)

**Modo video/audio (diseño de 2 niveles):**
- Superior: visualización de tiempo + barra de búsqueda (límite máximo de 720px de ancho)
- Inferior: ☆ Fav / ⓘ Info / ‹ › / ▶ Reproducir ⏪ ⏩ / ♪ Silencio + volumen / ⛶ ⤢ / 📁

### Menú de desbordamiento (botón …)

Consolida operaciones de baja frecuencia en una lista vertical:
- Reproducción automática + intervalo
- Repetir / velocidad / reanudar (para video)
- FPB / cuadrícula de caracteres (para imágenes fijas)
- ZIP / vista de contenedor
- Guía de teclado ?
- Contraer barra de herramientas «

## Atajos de teclado

| Tecla | Acción |
|---|---|
| `T` | Alternar visibilidad de la barra de herramientas |
| `V` | Modo inmersivo |
| `F` | Pantalla completa |
| `I` | Panel de información |
| `H` | Guía de teclado |
| `P` | Reproducción automática |
| `Space` / `K` | Reproducir / pausar (video) |
| `J` / `0` | Retroceder (video) |
| `L` | Avance rápido (video) |
| `M` | Silencio (video) |
| `R` | Repetir (video) |
| `←` / `→` | Imagen anterior / siguiente |
| `ESC` | Cerrar menú de desbordamiento → modal en orden |

## Contraer y restaurar

Métodos para contraer la barra de herramientas:
- En el menú de desbordamiento (…), seleccione "Contraer barra de herramientas"
- Presione la tecla `T`

Métodos para restaurar:
- Haga clic en el controlador de borde en el centro inferior de la pantalla
- Presione la tecla `T` nuevamente

La posición del controlador de borde se ajusta automáticamente según la presencia de la tira de película durante el estado contraído.

## Accesibilidad

- Toda la barra de herramientas tiene `role="toolbar"`
- El botón de desbordamiento utiliza `aria-haspopup="menu"` / `aria-expanded` se actualiza dinámicamente
- Los elementos del menú de desbordamiento tienen `role="menuitem"`
- El controlador de borde es un `<button>` estándar operable con Enter / Espacio
- Para satisfacer WCAG 2.5.5 (Tamaño de destino), el controlador visualmente 8px tiene un área de impacto invisible de 24px de alto extendida a través de `::before`

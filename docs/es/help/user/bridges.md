# Integración Bridge

Con la función Bridge puedes enviar prompts directamente desde YU AI Manager a diversas herramientas de generación de imágenes de IA.

## Bridges compatibles

### SD WebUI Bridge
Integración con Stable Diffusion WebUI (Automatic1111 / Forge).
- Envío y recepción de prompts
- Transferencia de parámetros de generación

### NAI Bridge
Integración con NovelAI.
- Conversión automática de sintaxis de prompts (SD ↔ NAI)
- Inserción automática de etiquetas de calidad

#### Vibe Transfer (poción de NovelAI) y caché de encode-vibe

Los modelos NAI V4+ requieren codificar las imágenes de referencia mediante `/ai/encode-vibe`
(**2 Anlas por llamada**) antes de usarlas en solicitudes de generación.

Para evitar desperdiciar Anlas al generar repetidamente con la misma imagen, los resultados
de codificación se almacenan en caché localmente en:

```
data/nai_vibe_cache/<sha256>__<model>__<info_extracted>.bin
```

- **Clave**: SHA256 de la imagen raw + nombre del modelo + información extraída (pasos de 0.01)
- **Tamaño máximo**: 500 MB por defecto. Cambiable en Settings > NAI Bridge > "Vibe encode cache (MB)" (0 = desactivado)
- **Desalojo LRU**: Los archivos más antiguos se eliminan en un hilo en segundo plano al superar el límite

### ComfyUI Bridge
Integración con ComfyUI.
- Inserción de prompts en flujos de trabajo
- Personalización del formato de salida

## Generación por lotes

Los tres Bridges admiten la generación por lotes en la ruta de generación principal (semántica compatible con A1111).

### Batch count / Batch size

- **Batch count** — Número de ejecuciones de generación secuenciales (eje temporal). El cliente llama a la API una vez por iteración.
- **Batch size** — Número de imágenes generadas en paralelo por llamada a la API (eje VRAM). No se muestra en NAI Bridge.
- Total de imágenes = Batch count × Batch size

Con un seed fijo, el seed se incrementa como `base + i` en cada iteración del loop (mismo comportamiento que A1111). Con `-1` (aleatorio), se usa un seed aleatorio nuevo cada vez.

### Botones de detención

| Bridge | Ejecución única (count=1) | Loop (count>1) |
|---|---|---|
| NAI | Sin botón de detención | Solo «Detener tras el actual» |
| SD WebUI | «Detener» (API cancel del servidor) | «Detener tras el actual» + «Detener» |
| ComfyUI | «Detener» (API cancel del servidor) | «Detener tras el actual» + «Detener» |

- **Detener (inmediato)** — Interrumpe la llamada a la API en curso y detiene el loop. En SD WebUI / ComfyUI también se llama a la API cancel del servidor.
- **Detener tras el actual** — Deja que la imagen actual termine de generarse y omite la siguiente iteración.

NAI Bridge no muestra botón de detención para la generación de imagen única porque la API de NAI consume Anlas (créditos) en el momento en que acepta el fetch. Cortar la conexión HTTP no detiene la generación del servidor ni reembolsa el coste, por lo que un botón de detención solo generaría confusión.

### Nota sobre VRAM

Aumentar Batch size incrementa el consumo de VRAM en la GPU del servidor proporcionalmente al número de imágenes. Con SDXL y Batch size 4 o más pueden producirse errores OOM; empieza con 1 y aumenta gradualmente.

## Presets de calidad

Con el botón "QP" en la barra de herramientas de cada Bridge, puedes insertar etiquetas de mejora de calidad con un solo clic.

Presets integrados:
- SD High Quality
- SD Realistic
- NAI Quality
- NAI Artistic
- Minimal

También se pueden crear presets personalizados.

## Presets de resolución

En los Bridges SD WebUI y ComfyUI, hay un menú desplegable "Resolution Preset" y un botón ⇄ Swap encima de los campos Width/Height. Permite ingresar resoluciones representativas con un solo clic.

- **SD 1.5** — 5 tipos con base en 512 para modelos de la serie SD1.5
- **SDXL Trained** — 9 tipos de los buckets de entrenamiento oficial de SDXL (calidad prioritaria)
- **SDXL Cheat Sheet** — 12 tipos que aproximan las proporciones de aspecto de cine y fotografía en múltiplos de 8 (composición prioritaria, fuente: [Civitai](https://civitai.com/articles/2246/sdxl-image-size-cheat-sheet))

Al seleccionar `Custom` se mantienen los valores W/H existentes. Editar W/H manualmente después de aplicar un preset lo devuelve automáticamente a `Custom`. El botón ⇄ intercambia Width y Height.

Las resoluciones de Cheat Sheet salen de los buckets oficiales, por lo que dependiendo del modelo puede haber cierta degradación de la composición.

> Solo se aplica en el modo Simple del ComfyUI Bridge. No afecta los valores de los nodos en el modo Raw JSON Workflow.

## Transferencia entre Bridges

Los prompts se pueden transferir directamente entre Bridges. La sintaxis se convierte automáticamente al transferir entre SD ↔ NAI.
